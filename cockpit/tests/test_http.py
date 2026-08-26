"""test_http.py — HTTP-layer contract tests via fastapi.testclient.TestClient.

Every other cockpit test calls route handlers directly as plain Python
functions (see test_workflow.py's module docstring); until this file there
was not one test exercising the real ASGI pipeline — routing, the HTTP
Basic-auth middleware (main.py's `_basic_auth_middleware`, ~line 352) and
the `_require_auth` dependency (~line 386), status codes, response shapes,
static files and the SSE endpoint were entirely uncovered. This file is
about the HTTP *contract*: does the route exist at the right method, is it
guarded by auth, does it return the right status and the fields callers
rely on. Business-logic depth (PDR math, sweep progression, gateway-move
guard details, migration, …) is deliberately NOT retested here — that is
test_workflow.py / test_db.py / test_scheduler.py / test_migration.py /
test_run_stats_golden.py.

Isolation. `app.main._lifespan()` connects to ChirpStack over gRPC and to
the MQTT broker on startup — neither is available in a test run, and this
suite must never touch a real network or `cockpit-data/`. The `client`
fixture below replaces `app.router.lifespan_context` (the actual attribute
Starlette's ASGI machinery calls — see `starlette.routing.Router.__init__`/
`.lifespan`) with a minimal stand-in that only opens a temp-file SQLite DB
(`app.main._db`) and upserts the gateway node, leaving `_grpc_channel`/
`_ingest`/`_sweep_task` at None/unset — exactly the "ChirpStack gRPC not
reachable" degraded mode main.py already documents and handles (`_grpc()`
raises HTTP 503; see e.g. `list_devices`, `enqueue_downlink`, `set_phase`).
It also swaps `app.main.campaign` for a fresh `CampaignState` rooted at
`tmp_path` — the module-level `campaign` singleton is otherwise constructed
once at import time with whatever `config.DATA_DIR` was at *that* point
(not per-test), and `campaign.start_recording()` (Panel 2) writes a CSV
straight into it; without this swap a recording test would write outside
tmp_path.

SSE (`GET /api/events`) is the one endpoint NOT run through TestClient's
`.get()`/`.stream()`: its generator loops forever (a 30 s keep-alive ping,
no client-disconnect check), and both Starlette's TestClient (a blocking
anyio-portal call awaiting the whole ASGI coroutine — see
`starlette.testclient._TestClientTransport.handle_request`) and
`httpx.ASGITransport` (`await self.app(scope, receive, send)`) fully await
that coroutine before returning a response — neither supports a stream
that never terminates, so `client.get("/api/events")` hangs indefinitely.
The auth-failure path is unaffected (the middleware short-circuits before
the generator ever starts) and is covered by the parametrized 401 test
below like every other route. The success path calls the route handler
directly — same pattern test_workflow.py already established — and drives
its `body_iterator` with a bounded timeout, which is fast and finite.
"""
import asyncio
import io
import os
from contextlib import asynccontextmanager

import pytest
from fastapi.security import HTTPBasicCredentials
from fastapi.testclient import TestClient
from PIL import Image

from app import config, main
from app.db import Database
from app.state import CampaignState

AUTH = (config.COCKPIT_USER, config.COCKPIT_PASSWORD)
WRONG_AUTH = (config.COCKPIT_USER, "not-the-password")
WWW_AUTHENTICATE = 'Basic realm="Feldtest-Cockpit"'

# A representative GET from every method the auth middleware guards (every
# path except /healthz) — routing/method/status is exercised per-route
# further down; this list only proves the auth gate itself is uniform.
_PROTECTED_GET_PATHS = [
    "/",
    "/favicon.ico",
    "/static/app.js",
    "/static/style.css",
    "/api/state",
    "/api/nodes",
    "/api/runs",
    "/api/devices",
    "/api/events",
    "/api/events/log",
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient wired to a fresh temp-file DB and an isolated
    CampaignState — see module docstring. Never touches cockpit-data/ or a
    real network (ChirpStack gRPC / MQTT stay disconnected)."""
    db_path = str(tmp_path / "cockpit.db")
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "PHOTOS_DIR", str(tmp_path / "photos"))
    monkeypatch.setattr(config, "FLOORPLANS_DIR", str(tmp_path / "floorplans"))
    monkeypatch.setattr(main, "_grpc_channel", None)
    monkeypatch.setattr(main, "_grpc_token", None)
    monkeypatch.setattr(main, "_tenant_id", None)
    monkeypatch.setattr(main, "_app_id", None)
    monkeypatch.setattr(main, "_ingest", None)
    monkeypatch.setattr(main, "campaign", CampaignState(data_dir=str(tmp_path)))

    @asynccontextmanager
    async def _test_lifespan(app):
        main.campaign.set_loop(asyncio.get_running_loop())
        db = Database(db_path)
        db.init_schema()
        main.campaign.set_db(db)
        gw_id, _ = db.upsert_node("gateway", config.GATEWAY_NAME, config.GATEWAY_EUI)
        monkeypatch.setattr(main, "_db", db)
        monkeypatch.setattr(main, "_gateway_node_id", gw_id)
        try:
            yield
        finally:
            db.close()

    monkeypatch.setattr(main.app.router, "lifespan_context", _test_lifespan)
    with TestClient(main.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Fixture helpers — set up just enough workflow state for one contract test,
# via the same HTTP routes under test (not db.py directly) wherever a route
# exists for it, so a broken route would show up here too.
# ---------------------------------------------------------------------------


def _place_gateway(client, floor: str = "EG", room: str = "Flur") -> int:
    r = client.post("/api/gateway/move", json={"floor": floor, "room": room}, auth=AUTH)
    assert r.status_code == 200
    return r.json()["placement_id"]


def _add_device_node(name: str = "thermostat-test", eui: str = "aaaa000000000099") -> int:
    node_id, _ = main._db.upsert_node("device", name, eui)
    return node_id


def _place_device(client, node_id: int, floor: str = "3", room: str = "301") -> int:
    r = client.post(
        "/api/placement",
        json={"node_id": node_id, "floor": floor, "room": room},
        auth=AUTH,
    )
    assert r.status_code == 200
    return r.json()["placement_id"]


def _make_jpeg_bytes(size: tuple[int, int] = (800, 600), orientation: int | None = None) -> bytes:
    """A real, decodable JPEG for thumbnail tests — the plain
    `b"\\xff\\xd8\\xff"` fixture the upload tests above use is enough to
    exercise store/serve-as-is, but PIL must actually be able to open it to
    generate a preview. `orientation` sets the EXIF Orientation tag (6 is
    the "rotated 90 CW, phone held sideways" case the real field photos
    under cockpit-data/photos/ carry)."""
    im = Image.new("RGB", size, color=(120, 40, 200))
    buf = io.BytesIO()
    if orientation is not None:
        exif = im.getexif()
        exif[0x0112] = orientation
        im.save(buf, format="JPEG", exif=exif)
    else:
        im.save(buf, format="JPEG")
    return buf.getvalue()


def _upload_photo(client, placement_id: int, content: bytes, filename: str = "x.jpg") -> int:
    r = client.post(
        f"/api/photo/{placement_id}",
        files={"file": (filename, content, "image/jpeg")},
        auth=AUTH,
    )
    assert r.status_code == 200
    return r.json()["photo_id"]


def _start_run(client, node_id: int) -> dict:
    r = client.post("/api/run/start", json={"device_node_id": node_id}, auth=AUTH)
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------------------
# Auth — the browser-dialog mechanism (main.py:352-378), previously
# entirely untested. /healthz is the one deliberate exception.
# ---------------------------------------------------------------------------


def test_healthz_without_credentials_returns_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_ignores_bad_credentials_too(client):
    """/healthz is unconditionally unauthenticated — see the middleware's
    explicit exemption, not a side effect of accepting any credentials."""
    r = client.get("/healthz", auth=WRONG_AUTH)
    assert r.status_code == 200


@pytest.mark.parametrize("path", _PROTECTED_GET_PATHS)
def test_protected_route_without_credentials_returns_401_with_challenge(client, path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == WWW_AUTHENTICATE


def test_protected_route_with_wrong_credentials_returns_401(client):
    r = client.get("/api/state", auth=WRONG_AUTH)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == WWW_AUTHENTICATE


def test_protected_route_with_wrong_username_returns_401(client):
    r = client.get("/api/state", auth=("not-" + AUTH[0], AUTH[1]))
    assert r.status_code == 401


def test_protected_route_with_correct_credentials_is_not_401(client):
    r = client.get("/api/state", auth=AUTH)
    assert r.status_code != 401


# ---------------------------------------------------------------------------
# Root + static assets
# ---------------------------------------------------------------------------


def test_root_serves_index_html(client):
    r = client.get("/", auth=AUTH)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<html" in r.text.lower()


def test_static_app_js_is_reachable(client):
    r = client.get("/static/app.js", auth=AUTH)
    assert r.status_code == 200


def test_static_style_css_is_reachable(client):
    r = client.get("/static/style.css", auth=AUTH)
    assert r.status_code == 200


def test_favicon_ico_is_reachable(client):
    """The well-known path browsers request regardless of <link rel="icon">
    markup — must not 404 (see scripts/ui_smoke.py, which used to carve
    /favicon.ico out of its error count for exactly that reason)."""
    r = client.get("/favicon.ico", auth=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/x-icon"


# ---------------------------------------------------------------------------
# Panel 1 — device registration (ChirpStack-backed; 503 with no gRPC)
# ---------------------------------------------------------------------------


def test_list_devices_503_without_chirpstack(client):
    r = client.get("/api/devices", auth=AUTH)
    assert r.status_code == 503


def test_register_device_503_without_chirpstack(client):
    r = client.post(
        "/api/devices",
        json={"name": "d1", "dev_eui": "aaaa000000000001", "app_key": "0" * 32},
        auth=AUTH,
    )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Panel 2 — measurement point + CSV
# ---------------------------------------------------------------------------


def test_set_point_200(client):
    r = client.post(
        "/api/point", json={"pos_id": "P1", "floor": "3", "room": "301"}, auth=AUTH
    )
    assert r.status_code == 200
    body = r.json()
    assert body["pos_id"] == "P1"
    assert body["status"] == "set"


def test_recording_toggle_on_then_off(client, tmp_path):
    r = client.post("/api/recording", json={"on": True}, auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["recording"] is True
    assert body["csv_path"].startswith(str(tmp_path))  # never outside tmp_path

    r2 = client.post("/api/recording", json={"on": False}, auth=AUTH)
    assert r2.status_code == 200
    assert r2.json()["recording"] is False


def test_download_csv_404_when_nothing_recorded_yet(client):
    r = client.get("/api/csv", auth=AUTH)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Panel 3 — dashboard snapshot
# ---------------------------------------------------------------------------


def test_get_state_200_shape(client):
    r = client.get("/api/state", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    for key in (
        "recording", "csv_path", "antenna", "phase", "point", "devices",
        "pos_counts", "coex_active", "coex_own_frames", "coex_foreign_frames",
    ):
        assert key in body


# ---------------------------------------------------------------------------
# Panel 4 — downlink loopback (ChirpStack-backed)
# ---------------------------------------------------------------------------


def test_enqueue_downlink_503_without_chirpstack(client):
    r = client.post(
        "/api/downlink",
        json={"dev_eui": "aaaa000000000001", "f_port": 1, "data_hex": "00"},
        auth=AUTH,
    )
    assert r.status_code == 503


def test_enqueue_downlink_422_on_invalid_f_port(client):
    r = client.post(
        "/api/downlink",
        json={"dev_eui": "aaaa000000000001", "f_port": 999, "data_hex": "00"},
        auth=AUTH,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Panel 5 — coexistence scan / RF environment
# ---------------------------------------------------------------------------


def test_toggle_coex_is_a_noop_200(client):
    r = client.post("/api/coex", json={"on": True}, auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"coex": True}


def test_rf_environment_200_shape(client):
    r = client.get("/api/rf-environment", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    for key in ("own_frames", "foreign_frames", "foreign_devices", "sf_distribution"):
        assert key in body


def test_rf_environment_csv_200_content_type(client):
    r = client.get("/api/rf-environment/csv", auth=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")


# ---------------------------------------------------------------------------
# Panel 6 — antenna toggle
# ---------------------------------------------------------------------------


def test_set_antenna_valid_type_200(client):
    r = client.post("/api/antenna", json={"type": "12dbi"}, auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"antenna": "12dbi"}


def test_set_antenna_invalid_type_422(client):
    r = client.post("/api/antenna", json={"type": "9dbi"}, auth=AUTH)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Panel 0 — phase / fixed-SF switch (ChirpStack-backed)
# ---------------------------------------------------------------------------


def test_set_phase_503_without_chirpstack(client):
    r = client.post("/api/phase", json={"phase": "sf9"}, auth=AUTH)
    assert r.status_code == 503


def test_set_phase_invalid_value_422(client):
    """Pydantic's field_validator rejects this before _grpc() is even
    reached — a genuine validation error, not a degraded-gRPC 503."""
    r = client.post("/api/phase", json={"phase": "sf7"}, auth=AUTH)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# F-0006 Feldmess-Workflow — nodes, placements, photos
# ---------------------------------------------------------------------------


def test_list_nodes_200_shape(client):
    r = client.get("/api/nodes", auth=AUTH)
    assert r.status_code == 200
    nodes = r.json()["nodes"]
    assert len(nodes) == 1  # the gateway, upserted by the test lifespan
    gw = nodes[0]
    for key in ("id", "kind", "name", "eui", "placement"):
        assert key in gw
    assert gw["kind"] == "gateway"
    assert gw["placement"] is None  # not placed yet


def test_create_placement_unknown_node_404(client):
    r = client.post("/api/placement", json={"node_id": 9999}, auth=AUTH)
    assert r.status_code == 404


def test_create_placement_200(client):
    node_id = _add_device_node()
    r = client.post(
        "/api/placement",
        json={"node_id": node_id, "floor": "3", "room": "301"},
        auth=AUTH,
    )
    assert r.status_code == 200
    assert "placement_id" in r.json()


def test_upload_photo_unknown_placement_404(client):
    r = client.post(
        "/api/photo/9999",
        files={"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")},
        auth=AUTH,
    )
    assert r.status_code == 404


def test_upload_photo_then_get_photo_200(client):
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    r = client.post(
        f"/api/photo/{placement_id}",
        files={"file": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")},
        auth=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert "photo_id" in body
    assert body["count"] == 1

    r2 = client.get(f"/api/photo/{body['photo_id']}", auth=AUTH)
    assert r2.status_code == 200


def test_get_photo_404_when_unknown(client):
    r = client.get("/api/photo/9999", auth=AUTH)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/photo/{id}/thumb — server-side preview (generate once, cache,
# never a 500 even for a broken/missing original). The full-size original
# stays reachable, unchanged, at /api/photo/{id} above — that is what the
# lightbox opens.
# ---------------------------------------------------------------------------


def test_get_photo_thumbnail_generates_and_shrinks(client):
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    original = _make_jpeg_bytes((800, 600))
    photo_id = _upload_photo(client, placement_id, original)

    r = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert len(r.content) < len(original)

    with Image.open(io.BytesIO(r.content)) as thumb:
        assert max(thumb.size) <= main.PHOTO_THUMBNAIL_MAX_EDGE


def test_get_photo_thumbnail_sets_long_lived_cache_header(client):
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    photo_id = _upload_photo(client, placement_id, _make_jpeg_bytes())

    r = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]


def test_get_photo_thumbnail_applies_exif_orientation(client):
    """Orientation 6 means "rotate 90 deg CW to display upright" — the exact
    tag the real field photos under cockpit-data/photos/ carry. An 800x600
    (landscape) source with that tag must render upright, i.e. as a
    600x800-shaped (portrait) preview, not a sideways 800x600 one."""
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    photo_id = _upload_photo(client, placement_id, _make_jpeg_bytes((800, 600), orientation=6))

    r = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    assert r.status_code == 200
    with Image.open(io.BytesIO(r.content)) as thumb:
        assert thumb.height > thumb.width  # portrait, not landscape
        assert thumb.size == (225, 300)  # 800:600 == 4:3, bounded to a 300 px long edge


def test_get_photo_thumbnail_reuses_cached_file_on_second_request(client, monkeypatch):
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    photo_id = _upload_photo(client, placement_id, _make_jpeg_bytes())

    calls = []
    real_write = main._write_thumbnail

    def _spy(original_path, thumb_path):
        calls.append((original_path, thumb_path))
        return real_write(original_path, thumb_path)

    monkeypatch.setattr(main, "_write_thumbnail", _spy)

    r1 = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    r2 = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.content == r2.content
    assert len(calls) == 1  # second request served the cached file, not regenerated


def test_get_photo_thumbnail_404_when_photo_unknown(client):
    r = client.get("/api/photo/9999/thumb", auth=AUTH)
    assert r.status_code == 404


def test_get_photo_thumbnail_404_when_original_file_missing(client):
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    photo_id = _upload_photo(client, placement_id, _make_jpeg_bytes())
    path = os.path.join(config.PHOTOS_DIR, str(placement_id), "1.jpg")
    os.remove(path)

    r = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    assert r.status_code == 404


def test_get_photo_thumbnail_no_500_on_corrupt_original(client):
    """Real case on record: an original that is not a decodable image at
    all. The endpoint must degrade to a clean JSON error, not a 500/traceback
    — the upload endpoint itself never validates image content, so a
    corrupt file reaching disk is a real scenario, not a hypothetical."""
    node_id = _add_device_node()
    placement_id = _place_device(client, node_id)
    photo_id = _upload_photo(client, placement_id, b"this is not a jpeg at all")

    r = client.get(f"/api/photo/{photo_id}/thumb", auth=AUTH)
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/json"
    assert "detail" in r.json()


# ---------------------------------------------------------------------------
# F-0008 Map / Placement Editor — floorplan + markers
# ---------------------------------------------------------------------------


def test_get_current_floorplan_when_none_uploaded(client):
    r = client.get("/api/floorplan", auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"floorplan": None, "markers": []}


def test_upload_floorplan_200(client):
    r = client.post(
        "/api/floorplan",
        files={"file": ("map.jpg", b"\xff\xd8\xff", "image/jpeg")},
        data={"name": "Test-Gebäude"},
        auth=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert "id" in body
    assert body["name"] == "Test-Gebäude"

    r2 = client.get("/api/floorplan", auth=AUTH)
    assert r2.status_code == 200
    assert r2.json()["floorplan"]["id"] == body["id"]


def test_get_floorplan_image_404_when_unknown(client):
    r = client.get("/api/floorplan/9999/image", auth=AUTH)
    assert r.status_code == 404


def test_upsert_marker_404_without_a_floorplan(client):
    node_id = _add_device_node()
    r = client.put(
        "/api/marker", json={"node_id": node_id, "x": 0.5, "y": 0.5}, auth=AUTH
    )
    assert r.status_code == 404


def test_remove_marker_404_unknown_node(client):
    r = client.delete("/api/marker/9999", auth=AUTH)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# F-0006 Feldmess-Workflow — run start/stop/relocate, gateway move
# ---------------------------------------------------------------------------


def test_run_start_409_without_any_placement(client):
    """The required error case from the spec: starting a run before either
    the device or the gateway has been placed must 409, not start blind."""
    node_id = _add_device_node()
    r = client.post("/api/run/start", json={"device_node_id": node_id}, auth=AUTH)
    assert r.status_code == 409


def test_run_start_409_with_device_placed_but_not_gateway(client):
    node_id = _add_device_node()
    _place_device(client, node_id)
    r = client.post("/api/run/start", json={"device_node_id": node_id}, auth=AUTH)
    assert r.status_code == 409


def test_run_start_404_unknown_device(client):
    _place_gateway(client)
    r = client.post("/api/run/start", json={"device_node_id": 9999}, auth=AUTH)
    assert r.status_code == 404


def test_run_start_200_with_both_placements(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    run = _start_run(client, node_id)
    for key in ("id", "status", "packets", "started_at", "progress", "done"):
        assert key in run
    assert run["status"] == "running"


def test_run_stop_404_when_no_active_run(client):
    node_id = _add_device_node()
    r = client.post("/api/run/stop", json={"device_node_id": node_id}, auth=AUTH)
    assert r.status_code == 404


def test_run_stop_200(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    run = _start_run(client, node_id)
    r = client.post("/api/run/stop", json={"device_node_id": node_id}, auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run["id"]
    assert body["status"] == "done"


def test_relocate_409_without_gateway_placement(client):
    node_id = _add_device_node()
    r = client.post(
        "/api/relocate",
        json={"device_node_id": node_id, "floor": "3", "room": "302"},
        auth=AUTH,
    )
    assert r.status_code == 409


def test_relocate_200(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    r = client.post(
        "/api/relocate",
        json={"device_node_id": node_id, "floor": "3", "room": "302"},
        auth=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert "placement_id" in body
    assert "run_id" in body


def test_relocate_404_unknown_device(client):
    _place_gateway(client)
    r = client.post("/api/relocate", json={"device_node_id": 9999}, auth=AUTH)
    assert r.status_code == 404


def test_gateway_move_200_with_no_open_runs(client):
    r = client.post(
        "/api/gateway/move", json={"floor": "EG", "room": "Flur"}, auth=AUTH
    )
    assert r.status_code == 200
    assert "placement_id" in r.json()


def test_gateway_move_409_with_an_open_run(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    _start_run(client, node_id)
    r = client.post(
        "/api/gateway/move", json={"floor": "EG", "room": "Flur 2"}, auth=AUTH
    )
    assert r.status_code == 409
    assert "open_runs" in r.json()["detail"]


def test_gateway_move_force_200_aborts_open_runs(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    _start_run(client, node_id)
    r = client.post(
        "/api/gateway/move/force", json={"floor": "EG", "room": "Flur 2"}, auth=AUTH
    )
    assert r.status_code == 200
    assert "placement_id" in r.json()


# ---------------------------------------------------------------------------
# F-0007 History — run list/detail/csv/series/stats
# ---------------------------------------------------------------------------


def test_list_runs_200_empty(client):
    r = client.get("/api/runs", auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"runs": []}


def test_list_runs_200_with_one_run(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    run = _start_run(client, node_id)

    r = client.get("/api/runs", auth=AUTH)
    assert r.status_code == 200
    runs = r.json()["runs"]
    assert len(runs) == 1
    entry = runs[0]
    for key in ("id", "run_id", "status", "device", "floor", "room", "overall"):
        assert key in entry
    assert entry["id"] == run["id"]


def test_run_detail_404_unknown(client):
    r = client.get("/api/run/9999/detail", auth=AUTH)
    assert r.status_code == 404


def test_run_detail_200(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    run = _start_run(client, node_id)

    r = client.get(f"/api/run/{run['id']}/detail", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    for key in ("run", "device", "gateway", "device_placement", "gateway_placement"):
        assert key in body


def test_run_csv_404_unknown(client):
    r = client.get("/api/run/9999/csv", auth=AUTH)
    assert r.status_code == 404


def test_run_series_404_unknown_run(client):
    r = client.get("/api/run/9999/series", auth=AUTH)
    assert r.status_code == 404


def test_run_series_200_no_packets_yet(client):
    """A run with no packets is NOT an error — 200 with points: []."""
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    run = _start_run(client, node_id)

    r = client.get(f"/api/run/{run['id']}/series", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["points"] == []
    assert body["total"] == 0


def test_run_stats_404_unknown(client):
    r = client.get("/api/run/9999/stats", auth=AUTH)
    assert r.status_code == 404


def test_run_stats_200_phase_a_run(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    run = _start_run(client, node_id)

    r = client.get(f"/api/run/{run['id']}/stats", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == run["id"]
    assert body["sf_stats"] == []  # Phase A fixed run — no SF segments
    assert "overall" in body


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" — device config visibility
# ---------------------------------------------------------------------------


def test_config_status_404_unknown_device(client):
    r = client.get("/api/device/9999/config-status", auth=AUTH)
    assert r.status_code == 404


def test_config_status_200_degrades_without_chirpstack(client):
    node_id = _add_device_node()
    r = client.get(f"/api/device/{node_id}/config-status", auth=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["queued"] == []  # best-effort empty queue, no gRPC
    for key in ("last_uplink_at", "interval_seconds", "last_downlink_at"):
        assert key in body


def test_set_interval_404_unknown_device(client):
    r = client.post(
        "/api/device/9999/set-interval", json={"minutes": 5}, auth=AUTH
    )
    assert r.status_code == 404


def test_set_interval_503_without_chirpstack(client):
    node_id = _add_device_node()
    r = client.post(
        f"/api/device/{node_id}/set-interval", json={"minutes": 5}, auth=AUTH
    )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Cockpit-redesign Stage 1 — GET /api/events/log (spec §4/§14/§16). Distinct
# from GET /api/events, the live SSE stream tested further below.
# ---------------------------------------------------------------------------


def test_events_log_200_empty_shape(client):
    r = client.get("/api/events/log", auth=AUTH)
    assert r.status_code == 200
    assert r.json() == {"events": [], "next_cursor": None, "has_more": False}


def test_events_log_run_start_and_stop_are_visible_with_device_name(client):
    """§4's whole point, end to end through the real HTTP routes: a run's
    lifecycle is durably visible in the log, with enough context (device
    name) to read without a second request."""
    _place_gateway(client)
    node_id = _add_device_node(name="thermostat-katia")
    _place_device(client, node_id)
    run = _start_run(client, node_id)
    client.post("/api/run/stop", json={"device_node_id": node_id}, auth=AUTH)

    r = client.get("/api/events/log", auth=AUTH)
    assert r.status_code == 200
    # _place_gateway (above) also writes its own gateway_moved event —
    # filter to this device's run lifecycle specifically.
    run_events = [e for e in r.json()["events"] if e["node_id"] == node_id]
    types = [e["type"] for e in run_events]
    assert types == ["run_stopped", "run_started"]  # newest first
    for event in run_events:
        assert event["node_name"] == "thermostat-katia"
        assert event["run_id"] == run["id"]
        assert event["source"] == "live"


def test_events_log_keyset_pagination(client):
    node_id = _add_device_node()
    for i in range(3):
        main._db.record_event("join", node_id=node_id, payload={"i": i})

    page1 = client.get("/api/events/log", params={"limit": 2}, auth=AUTH).json()
    assert len(page1["events"]) == 2
    assert page1["has_more"] is True

    page2 = client.get(
        "/api/events/log", params={"limit": 2, "cursor": page1["next_cursor"]}, auth=AUTH
    ).json()
    assert len(page2["events"]) == 1
    assert page2["has_more"] is False
    assert page2["next_cursor"] is None

    seen_ids = {e["id"] for e in page1["events"]} | {e["id"] for e in page2["events"]}
    assert len(seen_ids) == 3  # no overlap, none skipped


def test_events_log_filters_by_type(client):
    node_id = _add_device_node()
    main._db.record_event("join", node_id=node_id)
    main._db.record_event("gateway_moved")

    r = client.get("/api/events/log", params={"type": "join"}, auth=AUTH)
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["type"] == "join"


def test_events_log_filters_by_node_id(client):
    n1 = _add_device_node(name="d1", eui="aaaa000000000010")
    n2 = _add_device_node(name="d2", eui="aaaa000000000011")
    main._db.record_event("join", node_id=n1)
    main._db.record_event("join", node_id=n2)

    r = client.get("/api/events/log", params={"node_id": n1}, auth=AUTH)
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["node_id"] == n1


def test_relocate_writes_a_relocated_event(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    client.post(
        "/api/relocate",
        json={"device_node_id": node_id, "floor": "3", "room": "302"},
        auth=AUTH,
    )

    r = client.get("/api/events/log", params={"type": "relocated"}, auth=AUTH)
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["node_id"] == node_id
    assert events[0]["payload"] == {"floor": "3", "room": "302"}


def test_gateway_move_writes_a_gateway_moved_event(client):
    _place_gateway(client, floor="EG", room="Flur 2")

    r = client.get("/api/events/log", params={"type": "gateway_moved"}, auth=AUTH)
    events = r.json()["events"]
    assert len(events) == 1
    assert events[0]["payload"] == {"floor": "EG", "room": "Flur 2"}


def test_gateway_move_force_aborts_open_run_and_writes_both_events(client):
    _place_gateway(client)
    node_id = _add_device_node()
    _place_device(client, node_id)
    _start_run(client, node_id)

    client.post(
        "/api/gateway/move/force", json={"floor": "EG", "room": "Flur 2"}, auth=AUTH
    )

    r = client.get("/api/events/log", auth=AUTH)
    types = {e["type"] for e in r.json()["events"]}
    assert "gateway_moved" in types
    assert "run_stopped" in types


# ---------------------------------------------------------------------------
# SSE — GET /api/events (see module docstring for why the success path
# bypasses TestClient)
# ---------------------------------------------------------------------------


def test_sse_opens_and_streams_with_correct_content_type(client):
    creds = HTTPBasicCredentials(username=AUTH[0], password=AUTH[1])
    response = asyncio.run(main.sse_events(credentials=creds))
    assert response.status_code == 200
    assert response.media_type == "text/event-stream"

    async def _pull_one_event():
        agen = response.body_iterator
        main.campaign.broadcast_event({"type": "nodes"})
        chunk = await asyncio.wait_for(agen.__anext__(), timeout=2)
        await agen.aclose()  # triggers the generator's finally: unsubscribe
        return chunk

    chunk = asyncio.run(_pull_one_event())
    assert chunk == 'data: {"type": "nodes"}\n\n'
