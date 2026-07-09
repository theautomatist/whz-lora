"""test_workflow.py — unit tests for the F-0006 Feldmess-Workflow endpoint
logic in main.py (_resolve_run_placements, start_run, stop_run, relocate,
gateway_move, gateway_move/force), the Phase B SF-sweep glue
(_resolve_schedule, _process_run_sweep, _sf_sweep_tick), and F-0006
"Trust & Sichtbarkeit" (POST /api/coex no-op, GET .../config-status, POST
.../set-interval).

FastAPI's @app.get/@app.post decorators return the undecorated function, so
these route handlers can be called directly as plain Python functions —
no TestClient/httpx/live server needed (mirrors test_phase.py, which calls
_apply_phase_to_devices the same way). ChirpStack is mocked via monkeypatch
where Phase B code paths touch it (profile switch / interval downlink);
MQTT is never touched by this module.
"""
import asyncio
import csv
import datetime
import json
import os
import tempfile

import grpc
import pytest
from fastapi import HTTPException

from app import config, main
from app.db import CSV_COLUMNS, Database
from app.state import CampaignState


@pytest.fixture
def workflow(monkeypatch):
    """Fresh temp DB + provisioned gateway node, wired into app.main globals."""
    d = Database(os.path.join(tempfile.mkdtemp(), "test.db"))
    d.init_schema()
    gw_id, _ = d.upsert_node("gateway", config.GATEWAY_NAME, config.GATEWAY_EUI)
    monkeypatch.setattr(main, "_db", d)
    monkeypatch.setattr(main, "_gateway_node_id", gw_id)
    return d, gw_id


@pytest.fixture
def fresh_campaign(monkeypatch):
    """A CampaignState isolated from the shared main.campaign singleton, so
    F-0006 "Trust & Sichtbarkeit" tests don't leak device metrics into (or
    read stale state from) unrelated tests."""
    c = CampaignState(data_dir=tempfile.mkdtemp())
    monkeypatch.setattr(main, "campaign", c)
    return c


def _run(coro):
    """Run an async route handler to completion."""
    return asyncio.run(coro)


def _rpc_error(msg: str) -> grpc.RpcError:
    """Create a concrete grpc.RpcError subclass with .details() returning *msg*."""

    class _Err(grpc.RpcError):
        def details(self):  # noqa: D102
            return msg

        def code(self):
            return grpc.StatusCode.UNAVAILABLE

    return _Err()


# ---------------------------------------------------------------------------
# _resolve_run_placements — pure helper
# ---------------------------------------------------------------------------


def test_resolve_run_placements_both_missing(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    dp, gp, missing = main._resolve_run_placements(d, node_id, gw_id)
    assert dp is None
    assert gp is None
    assert "device has no active placement" in missing
    assert "gateway has no active placement" in missing


def test_resolve_run_placements_device_missing(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    dp, gp, missing = main._resolve_run_placements(d, node_id, gw_id)
    assert dp is None
    assert gp is not None
    assert missing == ["device has no active placement"]


def test_resolve_run_placements_both_present(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    dp, gp, missing = main._resolve_run_placements(d, node_id, gw_id)
    assert dp is not None
    assert gp is not None
    assert missing == []


def test_resolve_run_placements_no_gateway_node(workflow):
    d, _ = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    dp, gp, missing = main._resolve_run_placements(d, node_id, None)
    assert dp is not None
    assert gp is None
    assert missing == ["gateway has no active placement"]


# ---------------------------------------------------------------------------
# POST /api/run/start — requires active placements
# ---------------------------------------------------------------------------


def test_start_run_requires_active_placements(workflow):
    """No placements at all → 409 naming both missing pieces."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")

    with pytest.raises(HTTPException) as exc:
        main.start_run(main.RunStartRequest(device_node_id=node_id))
    assert exc.value.status_code == 409
    assert "device has no active placement" in exc.value.detail
    assert "gateway has no active placement" in exc.value.detail
    assert d.get_active_run(node_id) is None


def test_start_run_requires_gateway_placement_specifically(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")

    with pytest.raises(HTTPException) as exc:
        main.start_run(main.RunStartRequest(device_node_id=node_id))
    assert exc.value.status_code == 409
    assert exc.value.detail == "gateway has no active placement"


def test_start_run_succeeds_with_both_placements(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")

    run = main.start_run(main.RunStartRequest(device_node_id=node_id))
    assert run["status"] == "running"
    assert d.get_active_run(node_id)["id"] == run["id"]


def test_start_run_rejects_second_concurrent_run(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    main.start_run(main.RunStartRequest(device_node_id=node_id))

    with pytest.raises(HTTPException) as exc:
        main.start_run(main.RunStartRequest(device_node_id=node_id))
    assert exc.value.status_code == 409


def test_start_run_unknown_device_404(workflow):
    with pytest.raises(HTTPException) as exc:
        main.start_run(main.RunStartRequest(device_node_id=999))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/run/stop
# ---------------------------------------------------------------------------


def test_stop_run_no_active_run_404(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    with pytest.raises(HTTPException) as exc:
        _run(main.stop_run(main.RunStopRequest(device_node_id=node_id)))
    assert exc.value.status_code == 404


def test_stop_run_success(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))

    result = _run(main.stop_run(main.RunStopRequest(device_node_id=node_id, reason="done for the day")))
    assert result["run_id"] == run["id"]
    assert d.get_run(run["id"])["status"] == "done"
    assert d.get_run(run["id"])["reason"] == "done for the day"


# ---------------------------------------------------------------------------
# POST /api/relocate — the core action: close old run, new placement, new run
# ---------------------------------------------------------------------------


def test_relocate_requires_gateway_placement(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    with pytest.raises(HTTPException) as exc:
        main.relocate(
            main.RelocateRequest(device_node_id=node_id, floor="EG", room="R1")
        )
    assert exc.value.status_code == 409


def test_relocate_creates_placement_and_run_from_scratch(workflow):
    """relocate() also works as the *first* placement/run for a device."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(gw_id, "EG", "flur", "", "", "")

    result = main.relocate(
        main.RelocateRequest(device_node_id=node_id, floor="EG", room="R1", antenna="3dbi")
    )
    assert "placement_id" in result
    assert "run_id" in result
    assert d.get_active_placement(node_id)["id"] == result["placement_id"]
    assert d.get_active_run(node_id)["id"] == result["run_id"]


def test_relocate_closes_old_run_and_placement_opens_new(workflow):
    """The core invariant: relocating a device with an active run closes
    both the old run (status=done, reason=relocated) and the old placement,
    then opens a fresh placement + a fresh running run."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(gw_id, "EG", "flur", "", "", "")

    first = main.relocate(
        main.RelocateRequest(device_node_id=node_id, floor="EG", room="R1", description="spot A")
    )
    old_placement_id = first["placement_id"]
    old_run_id = first["run_id"]
    d.increment_run_packets(old_run_id)  # simulate a few uplinks recorded

    second = main.relocate(
        main.RelocateRequest(device_node_id=node_id, floor="1OG", room="R2", description="spot B")
    )

    # Old placement closed
    old_placement = d.get_placement(old_placement_id)
    assert old_placement["ended_at"] is not None

    # Old run closed with the 'relocated' reason, data preserved
    old_run = d.get_run(old_run_id)
    assert old_run["status"] == "done"
    assert old_run["reason"] == "relocated"
    assert old_run["packets"] == 1

    # New placement + run are active and distinct from the old ones
    assert second["placement_id"] != old_placement_id
    assert second["run_id"] != old_run_id
    active_placement = d.get_active_placement(node_id)
    assert active_placement["id"] == second["placement_id"]
    assert active_placement["description"] == "spot B"
    active_run = d.get_active_run(node_id)
    assert active_run["id"] == second["run_id"]


def test_relocate_unknown_device_404(workflow):
    with pytest.raises(HTTPException) as exc:
        main.relocate(main.RelocateRequest(device_node_id=999, floor="EG", room="R1"))
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/gateway/move — guard blocks while any run is 'running'
# ---------------------------------------------------------------------------


def test_gateway_move_succeeds_with_no_running_runs(workflow):
    d, gw_id = workflow
    d.create_placement(gw_id, "EG", "flur", "initial", "", "")

    result = _run(main.gateway_move(main.GatewayMoveRequest(floor="1OG", room="flur2")))
    assert "placement_id" in result
    assert d.get_active_placement(gw_id)["floor"] == "1OG"


def test_gateway_move_guard_blocks_on_running_runs(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))

    with pytest.raises(HTTPException) as exc:
        _run(main.gateway_move(main.GatewayMoveRequest(floor="1OG", room="flur2")))
    assert exc.value.status_code == 409
    open_runs = exc.value.detail["open_runs"]
    assert len(open_runs) == 1
    assert open_runs[0]["run_id"] == run["id"]
    assert open_runs[0]["device_node_id"] == node_id

    # Gateway must NOT have moved
    gw_placement = d.get_active_placement(gw_id)
    assert gw_placement["floor"] == "EG"


def test_gateway_move_force_aborts_running_runs_then_moves(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))

    result = _run(
        main.gateway_move_force(main.GatewayMoveRequest(floor="1OG", room="flur2"))
    )
    assert "placement_id" in result

    aborted_run = d.get_run(run["id"])
    assert aborted_run["status"] == "aborted"
    assert aborted_run["reason"] == "gateway-move"

    gw_placement = d.get_active_placement(gw_id)
    assert gw_placement["floor"] == "1OG"
    assert gw_placement["id"] == result["placement_id"]


# ---------------------------------------------------------------------------
# POST /api/placement — 404 for unknown node
# ---------------------------------------------------------------------------


def test_create_placement_unknown_node_404(workflow):
    with pytest.raises(HTTPException) as exc:
        _run(main.create_placement(main.PlacementRequest(node_id=999, floor="EG", room="R1")))
    assert exc.value.status_code == 404


def test_create_placement_closes_previous_via_endpoint(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")

    p1 = _run(main.create_placement(main.PlacementRequest(node_id=node_id, floor="EG", room="R1")))
    p2 = _run(main.create_placement(main.PlacementRequest(node_id=node_id, floor="1OG", room="R2")))

    assert d.get_placement(p1["placement_id"])["ended_at"] is not None
    assert d.get_active_placement(node_id)["id"] == p2["placement_id"]


# ---------------------------------------------------------------------------
# GET /api/nodes — placement (with photo_ids) + active_run shape
# ---------------------------------------------------------------------------


def test_list_nodes_includes_gateway_and_devices(workflow):
    d, gw_id = workflow
    d.upsert_node("device", "d1", "aaaa000000000001")

    data = _run(main.list_nodes())
    kinds = {n["kind"] for n in data["nodes"]}
    assert kinds == {"device", "gateway"}


def test_list_nodes_placement_null_when_unplaced(workflow):
    d, gw_id = workflow
    d.upsert_node("device", "d1", "aaaa000000000001")

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["placement"] is None
    assert dev_entry["active_run"] is None


def test_list_nodes_placement_includes_photo_ids(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    placement_id = d.create_placement(node_id, "3OG", "R301", "am Fenster", "", "3dbi")
    photo_id = d.add_photo(placement_id, "1.jpg")

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["placement"]["id"] == placement_id
    assert dev_entry["placement"]["floor"] == "3OG"
    assert dev_entry["placement"]["photo_ids"] == [photo_id]


def test_list_nodes_placement_no_photos_is_empty_list(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["placement"]["photo_ids"] == []


def test_list_nodes_active_run_summary(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))
    d.increment_run_packets(run["id"])

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["active_run"]["id"] == run["id"]
    assert dev_entry["active_run"]["status"] == "running"
    assert dev_entry["active_run"]["packets"] == 1
    assert "started_at" in dev_entry["active_run"]


# ---------------------------------------------------------------------------
# GET /api/runs — floor/room/description flattened onto each run (tiny fix)
# ---------------------------------------------------------------------------


def test_list_runs_flattens_placement_fields(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "am Fenster", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))

    data = _run(main.list_runs(node_id=node_id))
    assert len(data["runs"]) == 1
    r = data["runs"][0]
    assert r["id"] == run["id"]
    assert r["floor"] == "3OG"
    assert r["room"] == "R301"
    assert r["description"] == "am Fenster"
    assert r["gateway_description"] == ""
    # backward-compat nested shape still present
    assert r["device_placement"]["floor"] == "3OG"


def test_list_runs_empty_for_unknown_node(workflow):
    data = _run(main.list_runs(node_id=999))
    assert data["runs"] == []


# ---------------------------------------------------------------------------
# Phase B — _resolve_schedule: pure run-start schedule defaulting
# ---------------------------------------------------------------------------


def test_resolve_schedule_no_fields_means_no_sweep():
    """Backward compat: a bare {device_node_id} request must NOT trigger a
    sweep — this is what every Phase A test above relies on."""
    sf_schedule, planned, interval = main._resolve_schedule(
        main.RunStartRequest(device_node_id=1)
    )
    assert sf_schedule is None
    assert planned is None
    assert interval is None


def test_resolve_schedule_duration_alone_builds_default_sweep():
    sf_schedule, planned, interval = main._resolve_schedule(
        main.RunStartRequest(device_node_id=1, duration_seconds=300)
    )
    assert sf_schedule == [
        {"sf": 7, "seconds": 100},
        {"sf": 9, "seconds": 100},
        {"sf": 12, "seconds": 100},
    ]
    assert planned == 300
    assert interval == 5


def test_resolve_schedule_defaults_to_24h_when_nothing_but_interval_given():
    sf_schedule, planned, interval = main._resolve_schedule(
        main.RunStartRequest(device_node_id=1, interval_minutes=10)
    )
    assert planned == 86400
    assert sum(s["seconds"] for s in sf_schedule) == 86400
    assert [s["sf"] for s in sf_schedule] == [7, 9, 12]
    assert interval == 10


def test_resolve_schedule_explicit_schedule_used_verbatim():
    req = main.RunStartRequest(
        device_node_id=1,
        sf_schedule=[{"sf": 9, "seconds": 50}, {"sf": 12, "seconds": 50}],
    )
    sf_schedule, planned, interval = main._resolve_schedule(req)
    assert sf_schedule == [{"sf": 9, "seconds": 50}, {"sf": 12, "seconds": 50}]
    assert planned == 100  # sum of the given segments (duration_seconds omitted)
    assert interval == 5


def test_resolve_schedule_explicit_duration_overrides_schedule_sum():
    req = main.RunStartRequest(
        device_node_id=1, duration_seconds=999, sf_schedule=[{"sf": 9, "seconds": 50}]
    )
    _, planned, _ = main._resolve_schedule(req)
    assert planned == 999


def test_resolve_schedule_default_24h_sweep():
    sf_schedule, planned, interval = main._resolve_schedule(
        main.RunStartRequest(device_node_id=1, duration_seconds=86400)
    )
    assert planned == 86400
    assert sum(s["seconds"] for s in sf_schedule) == 86400
    assert sf_schedule[0] == {"sf": 7, "seconds": 28800}
    assert interval == 5


def test_sf_segment_rejects_invalid_sf():
    with pytest.raises(Exception):
        main.RunStartRequest(device_node_id=1, sf_schedule=[{"sf": 10, "seconds": 100}])


def test_sf_segment_rejects_non_positive_seconds():
    with pytest.raises(Exception):
        main.RunStartRequest(device_node_id=1, sf_schedule=[{"sf": 7, "seconds": 0}])


def test_run_start_request_rejects_out_of_range_interval():
    with pytest.raises(Exception):
        main.RunStartRequest(device_node_id=1, interval_minutes=0)
    with pytest.raises(Exception):
        main.RunStartRequest(device_node_id=1, interval_minutes=256)


# ---------------------------------------------------------------------------
# Phase B — POST /api/run/start with a sweep: profile switch + interval
# downlink ("im Raster"), interval byte format (0205 for 5 min)
# ---------------------------------------------------------------------------


def _grpc_ready(monkeypatch):
    monkeypatch.setattr(main, "_grpc_channel", object())
    monkeypatch.setattr(main, "_grpc_token", "tok")
    monkeypatch.setattr(main, "_tenant_id", "tenant")
    # F-0006 "Trust & Sichtbarkeit": main._grpc() (used by set_device_interval)
    # additionally requires _app_id — the Phase B side-effect helpers above
    # don't check it, so setting it here is a no-op for their tests.
    monkeypatch.setattr(main, "_app_id", "app")


def test_start_run_with_sweep_switches_profile_and_enqueues_interval(workflow, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    _grpc_ready(monkeypatch)

    calls = []
    monkeypatch.setattr(
        main.cs, "find_profile_id_by_name", lambda ch, tok, tid, name: f"profile-{name}"
    )
    monkeypatch.setattr(
        main.cs, "set_device_profile",
        lambda ch, tok, eui, pid: calls.append(("profile", eui, pid)),
    )
    monkeypatch.setattr(
        main.cs, "enqueue_downlink",
        lambda ch, tok, eui, fport, data: calls.append(("downlink", eui, fport, data)),
    )

    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        duration_seconds=300,
        sf_schedule=[{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}, {"sf": 12, "seconds": 100}],
        interval_minutes=5,
    ))

    assert run["current_sf"] == 7
    assert run["planned_seconds"] == 300
    assert run["sf_schedule"] == [
        {"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}, {"sf": 12, "seconds": 100},
    ]
    assert ("profile", "aaaa000000000001", "profile-WHZ-Feldtest-SF7") in calls
    # 0x02 SetSendPeriod + 5 (0x05) minutes -> "0205", confirmed by cs.enqueue_downlink's default.
    assert ("downlink", "aaaa000000000001", 1, "0205") in calls


def test_start_run_with_sweep_interval_16_minutes_byte():
    """f"02{interval_minutes:02x}" must hex-format the minute count."""
    assert f"02{16:02x}" == "0210"
    assert f"02{5:02x}" == "0205"
    assert f"02{1:02x}" == "0201"


def test_start_run_no_sweep_makes_no_grpc_calls(workflow, monkeypatch):
    """Guard against regressions: a bare run/start must not touch ChirpStack
    at all (this is also implicitly relied on by every Phase A test, which
    runs without any gRPC mocking)."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    _grpc_ready(monkeypatch)

    def _boom(*a, **kw):
        raise AssertionError("ChirpStack must not be called for a non-sweep run")

    monkeypatch.setattr(main.cs, "find_profile_id_by_name", _boom)
    monkeypatch.setattr(main.cs, "set_device_profile", _boom)
    monkeypatch.setattr(main.cs, "enqueue_downlink", _boom)

    run = main.start_run(main.RunStartRequest(device_node_id=node_id))
    assert run["status"] == "running"
    assert run["sf_schedule"] == []


def test_start_run_sweep_grpc_unavailable_still_starts_run(workflow, monkeypatch):
    """Best-effort: if ChirpStack gRPC isn't ready, the run still starts —
    only the profile switch / interval downlink are skipped (logged)."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    monkeypatch.setattr(main, "_grpc_channel", None)

    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id, sf_schedule=[{"sf": 7, "seconds": 10}], interval_minutes=5,
    ))
    assert run["status"] == "running"
    assert run["current_sf"] == 7


# ---------------------------------------------------------------------------
# Phase B — background scheduler glue: _process_run_sweep / _sf_sweep_tick
# ---------------------------------------------------------------------------


def _rewind_segment(d: Database, run_id: int, seconds_ago: int) -> None:
    past = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds_ago)
    ).isoformat(timespec="seconds")
    d.advance_run_segment(run_id, 0, past)


def test_process_run_sweep_advances_segment(workflow, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    _grpc_ready(monkeypatch)
    monkeypatch.setattr(main.cs, "find_profile_id_by_name", lambda *a: "profile-x")
    switched = []
    monkeypatch.setattr(
        main.cs, "set_device_profile", lambda ch, tok, eui, pid: switched.append((eui, pid))
    )
    monkeypatch.setattr(main.cs, "enqueue_downlink", lambda *a: None)

    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        sf_schedule=[{"sf": 7, "seconds": 1}, {"sf": 9, "seconds": 100}],
        interval_minutes=5,
    ))
    switched.clear()  # ignore the initial first-segment switch at run start

    _rewind_segment(d, run["id"], seconds_ago=5)
    main._process_run_sweep(d.get_run(run["id"]))

    updated = d.get_run(run["id"])
    assert updated["segment_index"] == 1
    assert updated["status"] == "running"
    assert switched and switched[0][0] == "aaaa000000000001"


def test_process_run_sweep_marks_done_at_schedule_end(workflow, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    monkeypatch.setattr(main, "_grpc_channel", None)

    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id, sf_schedule=[{"sf": 7, "seconds": 1}], interval_minutes=5,
    ))
    _rewind_segment(d, run["id"], seconds_ago=5)
    main._process_run_sweep(d.get_run(run["id"]))

    updated = d.get_run(run["id"])
    assert updated["status"] == "done"
    assert updated["reason"] == "schedule-complete"


def test_process_run_sweep_noop_for_non_sweep_run(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))  # no sweep

    main._process_run_sweep(d.get_run(run["id"]))  # must not raise or change anything

    assert d.get_run(run["id"])["status"] == "running"


def test_sf_sweep_tick_processes_all_running_runs(workflow, monkeypatch):
    d, gw_id = workflow
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    n2, _ = d.upsert_node("device", "d2", "bbbb000000000002")
    d.create_placement(n1, "EG", "R1", "", "", "3dbi")
    d.create_placement(n2, "EG", "R2", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    monkeypatch.setattr(main, "_grpc_channel", None)
    monkeypatch.setattr(main, "_db", d)

    r1 = main.start_run(main.RunStartRequest(
        device_node_id=n1, sf_schedule=[{"sf": 7, "seconds": 1}], interval_minutes=5,
    ))
    r2 = main.start_run(main.RunStartRequest(device_node_id=n2))  # no sweep — untouched

    _rewind_segment(d, r1["id"], seconds_ago=5)
    main._sf_sweep_tick()

    assert d.get_run(r1["id"])["status"] == "done"
    assert d.get_run(r2["id"])["status"] == "running"


def test_sf_sweep_tick_isolates_failures_per_run(workflow, monkeypatch):
    """One run's processing raising must not stop the others from being
    attempted in the same tick."""
    d, gw_id = workflow
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    n2, _ = d.upsert_node("device", "d2", "bbbb000000000002")
    d.create_placement(n1, "EG", "R1", "", "", "3dbi")
    d.create_placement(n2, "EG", "R2", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    monkeypatch.setattr(main, "_db", d)

    r1 = main.start_run(main.RunStartRequest(device_node_id=n1))
    r2 = main.start_run(main.RunStartRequest(device_node_id=n2))

    processed = []

    def _boom(run):
        processed.append(run["id"])
        if run["id"] == r1["id"]:
            raise RuntimeError("boom")

    monkeypatch.setattr(main, "_process_run_sweep", _boom)

    main._sf_sweep_tick()  # must not raise despite r1's failure

    assert set(processed) == {r1["id"], r2["id"]}


def test_sf_sweep_tick_noop_when_db_unavailable(monkeypatch):
    monkeypatch.setattr(main, "_db", None)
    main._sf_sweep_tick()  # must not raise


# ---------------------------------------------------------------------------
# Phase B — GET /api/nodes: last_run + sweep summary fields
# ---------------------------------------------------------------------------


def test_list_nodes_last_run_present_after_run_stops(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))
    _run(main.stop_run(main.RunStopRequest(device_node_id=node_id)))

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["active_run"] is None
    assert dev_entry["last_run"]["id"] == run["id"]
    assert dev_entry["last_run"]["status"] == "done"
    assert dev_entry["last_run"]["done"] is True


def test_list_nodes_last_run_none_when_never_run(workflow):
    d, gw_id = workflow
    d.upsert_node("device", "d1", "aaaa000000000001")

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["last_run"] is None


def test_list_nodes_active_run_has_sweep_progress_fields(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        sf_schedule=[{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}],
        interval_minutes=5,
    ))

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    active = dev_entry["active_run"]
    assert active["current_sf"] == 7
    assert active["segment_index"] == 0
    assert active["planned_seconds"] == 200
    assert active["done"] is False
    assert 0.0 <= active["progress"] < 1.0


def test_list_nodes_active_run_includes_interval_minutes(workflow):
    """F-0006 "Trust & Sichtbarkeit" — the frontend needs the run's target
    send interval to judge the device's measured cadence against it."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        sf_schedule=[{"sf": 7, "seconds": 100}],
        interval_minutes=7,
    ))

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["active_run"]["interval_minutes"] == 7


def test_list_nodes_phase_a_run_interval_minutes_none(workflow):
    """A Phase A fixed run (no sweep) has interval_minutes=None."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    main.start_run(main.RunStartRequest(device_node_id=node_id))

    data = _run(main.list_nodes())
    dev_entry = next(n for n in data["nodes"] if n["kind"] == "device")
    assert dev_entry["active_run"]["interval_minutes"] is None


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" (Task 1) — POST /api/coex is now a no-op
# ---------------------------------------------------------------------------


def test_coex_endpoint_is_noop_regardless_of_on_value():
    """"Funkumgebung" runs always-on; this call no longer gates anything."""
    assert _run(main.toggle_coex(main.CoexRequest(on=False))) == {"coex": True}
    assert _run(main.toggle_coex(main.CoexRequest(on=True))) == {"coex": True}


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" (Task 2) — GET /api/device/{id}/config-status
# ---------------------------------------------------------------------------


def test_device_config_status_unknown_node_404(workflow, fresh_campaign):
    with pytest.raises(HTTPException) as exc:
        main.device_config_status(999)
    assert exc.value.status_code == 404


def test_device_config_status_gateway_node_404(workflow, fresh_campaign):
    d, gw_id = workflow
    with pytest.raises(HTTPException) as exc:
        main.device_config_status(gw_id)
    assert exc.value.status_code == 404


def test_device_config_status_no_grpc_returns_empty_queue(workflow, fresh_campaign, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    monkeypatch.setattr(main, "_grpc_channel", None)

    result = main.device_config_status(node_id)
    assert result == {
        "last_uplink_at": None,
        "interval_seconds": None,
        "queued": [],
        "last_downlink_at": None,
    }


def test_device_config_status_returns_queue_and_stats(workflow, fresh_campaign, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    _grpc_ready(monkeypatch)
    fresh_campaign.process_uplink({"dev_eui": "aaaa000000000001", "rssi_dbm": -70})
    fresh_campaign.record_downlink_txack("aaaa000000000001")
    monkeypatch.setattr(
        main.cs, "get_device_queue",
        lambda ch, tok, eui: [{"f_port": 1, "data_hex": "0205"}],
    )

    result = main.device_config_status(node_id)
    assert result["queued"] == [{"f_port": 1, "data_hex": "0205"}]
    assert result["last_uplink_at"] is not None
    assert result["last_downlink_at"] is not None


def test_device_config_status_grpc_error_degrades_gracefully(workflow, fresh_campaign, monkeypatch):
    """GetQueue failing must not fail the whole endpoint — the uplink-side
    status is still useful on its own."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    _grpc_ready(monkeypatch)

    def _boom(*a, **kw):
        raise _rpc_error("unavailable")

    monkeypatch.setattr(main.cs, "get_device_queue", _boom)

    result = main.device_config_status(node_id)
    assert result["queued"] == []


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" (Task 2) — POST /api/device/{id}/set-interval
# ---------------------------------------------------------------------------


def test_set_device_interval_unknown_node_404(workflow):
    with pytest.raises(HTTPException) as exc:
        main.set_device_interval(999, main.SetIntervalRequest(minutes=5))
    assert exc.value.status_code == 404


def test_set_device_interval_requires_grpc(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    with pytest.raises(HTTPException) as exc:
        main.set_device_interval(node_id, main.SetIntervalRequest(minutes=5))
    assert exc.value.status_code == 503


def test_set_device_interval_enqueues_correct_payload(workflow, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    _grpc_ready(monkeypatch)
    calls = []
    monkeypatch.setattr(
        main.cs, "enqueue_downlink",
        lambda ch, tok, eui, fport, data: calls.append((eui, fport, data)),
    )

    result = main.set_device_interval(node_id, main.SetIntervalRequest(minutes=16))
    assert result == {"status": "enqueued", "dev_eui": "aaaa000000000001", "minutes": 16}
    assert calls == [("aaaa000000000001", 1, "0210")]


def test_set_device_interval_grpc_error_502(workflow, monkeypatch):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    _grpc_ready(monkeypatch)

    def _boom(*a, **kw):
        raise _rpc_error("boom")

    monkeypatch.setattr(main.cs, "enqueue_downlink", _boom)

    with pytest.raises(HTTPException) as exc:
        main.set_device_interval(node_id, main.SetIntervalRequest(minutes=5))
    assert exc.value.status_code == 502


def test_set_interval_request_rejects_out_of_range():
    with pytest.raises(Exception):
        main.SetIntervalRequest(minutes=0)
    with pytest.raises(Exception):
        main.SetIntervalRequest(minutes=256)


# ---------------------------------------------------------------------------
# "Verlauf" line chart — _parse_run_series (pure) + GET /api/run/{id}/series
# ---------------------------------------------------------------------------


def _write_run_csv(path, rows):
    """rows: list of dicts with a subset of CSV_COLUMNS keys; any missing
    column defaults to '' (matches what db.py's csv.DictWriter produces)."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for row in rows:
            full = {col: "" for col in CSV_COLUMNS}
            full.update(row)
            w.writerow(full)


def test_parse_run_series_missing_csv_returns_empty_points():
    started = "2026-01-01T00:00:00+00:00"
    assert main._parse_run_series("", started) == {"total": 0, "points": []}
    assert main._parse_run_series(None, started) == {"total": 0, "points": []}
    assert main._parse_run_series("/no/such/file.csv", started) == {"total": 0, "points": []}


def test_parse_run_series_no_started_at_returns_empty_points():
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    _write_run_csv(path, [{"timestamp_utc": "2026-01-01T00:00:00+00:00", "rssi_dbm": "-70"}])
    assert main._parse_run_series(path, None) == {"total": 0, "points": []}


def test_parse_run_series_parses_rows_across_sf_stages():
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    started = "2026-01-01T00:00:00+00:00"
    _write_run_csv(path, [
        {"timestamp_utc": "2026-01-01T00:00:00+00:00", "rssi_dbm": "-60",  "snr_db": "9.5",  "sf": "7",  "f_cnt": "1"},
        {"timestamp_utc": "2026-01-01T00:01:40+00:00", "rssi_dbm": "-90",  "snr_db": "1.0",  "sf": "9",  "f_cnt": "2"},
        {"timestamp_utc": "2026-01-01T00:03:20+00:00", "rssi_dbm": "-115", "snr_db": "-8.0", "sf": "12", "f_cnt": "3"},
    ])

    result = main._parse_run_series(path, started)
    assert result["total"] == 3
    pts = result["points"]
    assert [p["t"] for p in pts] == [0.0, 100.0, 200.0]
    assert [p["sf"] for p in pts] == [7, 9, 12]
    assert [p["rssi"] for p in pts] == [-60.0, -90.0, -115.0]
    assert [p["snr"] for p in pts] == [9.5, 1.0, -8.0]
    assert [p["f_cnt"] for p in pts] == [1, 2, 3]


def test_parse_run_series_missing_metrics_become_none():
    """A row whose metrics were empty at write time (device metadata not yet
    known, or a metric field genuinely absent) must not crash the parser —
    None, not a stray ''/exception."""
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    _write_run_csv(path, [{"timestamp_utc": "2026-01-01T00:00:00+00:00"}])
    result = main._parse_run_series(path, "2026-01-01T00:00:00+00:00")
    assert result["points"] == [{"t": 0.0, "rssi": None, "snr": None, "sf": None, "f_cnt": None}]


def test_parse_run_series_downsample_cap():
    """Larger-than-max_points CSVs are downsampled (every Nth row); total
    stays the RAW row count."""
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    rows = [
        {"timestamp_utc": (base + datetime.timedelta(seconds=i)).isoformat(), "rssi_dbm": "-70", "sf": "7"}
        for i in range(10)
    ]
    _write_run_csv(path, rows)

    result = main._parse_run_series(path, base.isoformat(), max_points=3)
    assert result["total"] == 10
    assert 1 <= len(result["points"]) <= 3


def test_run_series_unknown_run_404(workflow):
    with pytest.raises(HTTPException) as exc:
        _run(main.run_series(999))
    assert exc.value.status_code == 404


def test_run_series_no_packets_yet_returns_empty_points(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))

    result = _run(main.run_series(run["id"]))
    assert result["run_id"] == run["id"]
    assert result["total"] == 0
    assert result["points"] == []


def test_run_series_returns_points_from_real_run(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        sf_schedule=[{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}],
        interval_minutes=5,
    ))

    for sf in (7, 7, 9):
        d.record_uplink_for_run("aaaa000000000001", {
            "rssi_dbm": -70, "snr_db": 5.0, "sf": sf, "freq_hz": 868100000, "f_cnt": 1, "gw_eui": "x",
        })

    result = _run(main.run_series(run["id"]))
    assert result["run_id"] == run["id"]
    assert result["total"] == 3
    assert len(result["points"]) == 3
    assert [p["sf"] for p in result["points"]] == [7, 7, 9]
    assert result["planned_seconds"] == 200
    assert result["sf_schedule"] == [{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}]
    assert result["started_at"] == run["started_at"]


def test_run_series_missing_csv_file_returns_empty_points_not_error(workflow):
    """The CSV file having been deleted on disk must not error — HTTP 200
    with points: []."""
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))
    os.remove(run["csv_path"])

    result = _run(main.run_series(run["id"]))
    assert result["points"] == []
    assert result["total"] == 0


# ---------------------------------------------------------------------------
# "Trust & Sichtbarkeit" — per-SF PDR: _segment_bounds/_segment_index_for_offset
# (pure) + _compute_run_stats (pure, CSV + a hand-built run dict) + GET
# /api/run/{id}/stats + RunStartRequest.downlink_test
# ---------------------------------------------------------------------------


def test_segment_bounds():
    schedule = [{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 50}]
    assert main._segment_bounds(schedule) == [(0, 100), (100, 150)]


def test_segment_bounds_empty_schedule():
    assert main._segment_bounds([]) == []


def test_segment_index_for_offset():
    bounds = [(0, 300), (300, 600), (600, 900)]
    assert main._segment_index_for_offset(-5, bounds) is None
    assert main._segment_index_for_offset(0, bounds) == 0
    assert main._segment_index_for_offset(150, bounds) == 0
    assert main._segment_index_for_offset(300, bounds) == 1
    assert main._segment_index_for_offset(599, bounds) == 1
    assert main._segment_index_for_offset(600, bounds) == 2
    assert main._segment_index_for_offset(1000, bounds) == 2  # folds into last
    assert main._segment_index_for_offset(0, []) is None


def test_compute_run_stats_full_scenario():
    """Uplink PDR per segment (expected from the COMMANDED interval, not the
    measured one), Ø RSSI/SNR per segment, downlink PDR from dl_counts, and
    the overall aggregate row — all in one realistic-shaped scenario."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    rows = []
    # Segment 0 (SF7, [0,300)): 4 of the 5 expected packets arrived — one lost.
    for i, t in enumerate([0, 60, 120, 180]):
        rows.append({
            "timestamp_utc": (base + datetime.timedelta(seconds=t)).isoformat(),
            "rssi_dbm": str(-60 - i * 10),
            "snr_db": str(8 - i * 2),
            "sf": "7",
        })
    # Segment 1 (SF9, [300,600)): all 5 expected packets arrived.
    for t in [300, 360, 420, 480, 540]:
        rows.append({
            "timestamp_utc": (base + datetime.timedelta(seconds=t)).isoformat(),
            "rssi_dbm": "-50",
            "snr_db": "5",
            "sf": "9",
        })
    # Segment 2 (SF12, [600,900)) has not started yet at "now" below.
    _write_run_csv(path, rows)

    run = {
        "csv_path": path,
        "started_at": base.isoformat(),
        "ended_at": None,
        "status": "running",
        "sf_schedule": json.dumps([
            {"sf": 7, "seconds": 300}, {"sf": 9, "seconds": 300}, {"sf": 12, "seconds": 300},
        ]),
        "interval_minutes": 1,  # interval_s=60 -> 300s/segment -> 5 expected/segment
        "dl_counts": json.dumps({
            "by_sf": {"7": {"sent": 2, "acked": 1}, "9": {"sent": 1, "acked": 1}},
            "pending_sf": None,
        }),
    }
    now = base + datetime.timedelta(seconds=600)  # exactly at the seg1/seg2 boundary

    result = main._compute_run_stats(run, now=now)

    sf7, sf9, sf12 = result["sf_stats"]
    assert sf7 == {
        "sf": 7, "expected": 5, "received": 4, "pdr": 0.8,
        "rssi_avg": -75.0, "snr_avg": 5.0,
        "dl_sent": 2, "dl_acked": 1, "dl_pdr": 0.5,
    }
    assert sf9 == {
        "sf": 9, "expected": 5, "received": 5, "pdr": 1.0,
        "rssi_avg": -50.0, "snr_avg": 5.0,
        "dl_sent": 1, "dl_acked": 1, "dl_pdr": 1.0,
    }
    assert sf12 == {
        "sf": 12, "expected": 0, "received": 0, "pdr": 0.0,
        "rssi_avg": None, "snr_avg": None,
        "dl_sent": 0, "dl_acked": 0, "dl_pdr": None,
    }

    overall = result["overall"]
    assert overall["expected"] == 10
    assert overall["received"] == 9
    assert overall["pdr"] == 0.9
    assert overall["rssi_avg"] == -61.1
    assert overall["snr_avg"] == 5.0
    assert overall["dl_sent"] == 3
    assert overall["dl_acked"] == 2
    assert overall["dl_pdr"] == round(2 / 3, 4)


def test_compute_run_stats_pdr_clamped_to_one():
    """More packets than "expected" (e.g. a slightly-off clock or a burst)
    must clamp PDR to 1.0, never go above."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    _write_run_csv(path, [
        {"timestamp_utc": (base + datetime.timedelta(seconds=t)).isoformat(), "sf": "7"}
        for t in range(0, 60, 5)  # 12 packets in a 60 s segment
    ])
    run = {
        "csv_path": path, "started_at": base.isoformat(), "ended_at": None,
        "status": "running",
        "sf_schedule": json.dumps([{"sf": 7, "seconds": 60}]),
        "interval_minutes": 5,  # expected = round(60/300) = 0 -> denom clamped to 1
        "dl_counts": None,
    }
    result = main._compute_run_stats(run, now=base + datetime.timedelta(seconds=60))
    assert result["sf_stats"][0]["received"] == 12
    assert result["sf_stats"][0]["pdr"] == 1.0


def test_compute_run_stats_done_run_freezes_elapsed_at_ended_at():
    """A finished run's per-segment "expected" must be computed against
    ended_at, not against whatever "now" happens to be passed."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    _write_run_csv(path, [])

    run = {
        "csv_path": path,
        "started_at": base.isoformat(),
        "ended_at": (base + datetime.timedelta(seconds=480)).isoformat(),
        "status": "done",
        "sf_schedule": json.dumps([{"sf": 7, "seconds": 300}, {"sf": 9, "seconds": 300}]),
        "interval_minutes": 1,
        "dl_counts": None,
    }
    result = main._compute_run_stats(run, now=base + datetime.timedelta(days=1))

    sf7, sf9 = result["sf_stats"]
    assert sf7["expected"] == 5   # fully elapsed: 300 s / 60 s
    assert sf9["expected"] == 3   # 480 - 300 = 180 s elapsed / 60 s


def test_compute_run_stats_phase_a_run_no_schedule():
    """A Phase A fixed run (no sf_schedule/interval_minutes) has no SF
    concept — sf_stats is empty, overall still summarises the CSV."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    path = os.path.join(tempfile.mkdtemp(), "run.csv")
    _write_run_csv(path, [
        {"timestamp_utc": base.isoformat(), "rssi_dbm": "-70", "snr_db": "5"},
        {"timestamp_utc": (base + datetime.timedelta(seconds=10)).isoformat(), "rssi_dbm": "-80", "snr_db": "3"},
    ])
    run = {
        "csv_path": path, "started_at": base.isoformat(), "ended_at": None,
        "status": "running", "sf_schedule": None, "interval_minutes": None,
        "dl_counts": None,
    }
    result = main._compute_run_stats(run)
    assert result["sf_stats"] == []
    overall = result["overall"]
    assert overall == {
        "sf": None, "expected": None, "received": 2, "pdr": None,
        "rssi_avg": -75.0, "snr_avg": 4.0,
        "dl_sent": 0, "dl_acked": 0, "dl_pdr": None,
    }


def test_compute_run_stats_missing_csv_is_not_an_error():
    run = {
        "csv_path": "/no/such/file.csv",
        "started_at": "2026-01-01T00:00:00+00:00", "ended_at": None,
        "status": "running",
        "sf_schedule": json.dumps([{"sf": 7, "seconds": 100}]),
        "interval_minutes": 5,
        "dl_counts": None,
    }
    result = main._compute_run_stats(
        run, now=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    )
    assert result["sf_stats"][0]["received"] == 0


# ---------------------------------------------------------------------------
# GET /api/run/{run_id}/stats
# ---------------------------------------------------------------------------


def test_run_stats_unknown_run_404(workflow):
    with pytest.raises(HTTPException) as exc:
        _run(main.run_stats(999))
    assert exc.value.status_code == 404


def test_run_stats_defaults_downlink_test_true(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))

    result = _run(main.run_stats(run["id"]))
    assert result["downlink_test"] is True


def test_run_stats_reflects_downlink_test_disabled(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id, downlink_test=False))

    result = _run(main.run_stats(run["id"]))
    assert result["downlink_test"] is False


def test_run_stats_sweep_run_returns_sf_stats_for_each_segment(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        sf_schedule=[{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}],
        interval_minutes=5,
    ))

    for _ in range(3):
        d.record_uplink_for_run("aaaa000000000001", {
            "rssi_dbm": -70, "snr_db": 5.0, "sf": 7, "freq_hz": 868100000, "f_cnt": 1, "gw_eui": "x",
        })

    result = _run(main.run_stats(run["id"]))
    assert len(result["sf_stats"]) == 2
    assert result["sf_stats"][0]["sf"] == 7
    assert result["sf_stats"][0]["received"] == 3
    assert result["overall"]["received"] == 3


def test_run_stats_phase_a_run_returns_empty_sf_stats(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(device_node_id=node_id))  # no sweep

    result = _run(main.run_stats(run["id"]))
    assert result["sf_stats"] == []
    assert result["overall"]["received"] == 0


def test_run_stats_includes_downlink_counts(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = main.start_run(main.RunStartRequest(
        device_node_id=node_id,
        sf_schedule=[{"sf": 7, "seconds": 100}],
        interval_minutes=5,
    ))

    dl = d.maybe_trigger_downlink_test("aaaa000000000001", 3)  # K=3 for interval_minutes=5
    assert dl is not None
    d.record_downlink_test_ack("aaaa000000000001", True)

    result = _run(main.run_stats(run["id"]))
    assert result["sf_stats"][0]["dl_sent"] == 1
    assert result["sf_stats"][0]["dl_acked"] == 1
    assert result["sf_stats"][0]["dl_pdr"] == 1.0


# ---------------------------------------------------------------------------
# RunStartRequest.downlink_test — default True, passed through to db.start_run
# ---------------------------------------------------------------------------


def test_run_start_request_downlink_test_defaults_true():
    assert main.RunStartRequest(device_node_id=1).downlink_test is True


def test_run_start_request_downlink_test_can_be_disabled():
    assert main.RunStartRequest(device_node_id=1, downlink_test=False).downlink_test is False


def test_start_run_passes_downlink_test_through_to_db(workflow):
    d, gw_id = workflow
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    d.create_placement(gw_id, "EG", "flur", "", "", "")

    run = main.start_run(main.RunStartRequest(device_node_id=node_id, downlink_test=False))
    assert d.get_run(run["id"])["downlink_test"] == 0


# ---------------------------------------------------------------------------
# GET /api/rf-environment — full spectrum-survey snapshot (F-0006)
# ---------------------------------------------------------------------------


def test_rf_environment_endpoint_returns_snapshot_shape(fresh_campaign):
    result = _run(main.rf_environment())
    assert set(result.keys()) == {
        "own_frames", "foreign_frames", "unknown_frames",
        "foreign_devices", "networks", "vendors", "mtype_counts",
        "channel_sf_matrix", "frames_per_min", "frames_per_min_sparkline",
    }
    assert result["foreign_devices"] == {}
    assert result["mtype_counts"] == {"join": 0, "data_up": 0, "data_down": 0, "other": 0}


def test_rf_environment_endpoint_reflects_foreign_traffic(fresh_campaign):
    fresh_campaign.process_join("aabbccdd00000001", "01020304")
    foreign_phy = bytes([0x40, 0xaa, 0xbb, 0xcc, 0x26, 0x00, 0x01, 0x00])
    fresh_campaign.process_coex_frame(7, 868100000, -80, foreign_phy, -5.0)

    result = _run(main.rf_environment())
    assert len(result["foreign_devices"]) == 1
    assert result["networks"] == {"The Things Network": {"devices": 1, "frames": 1}}
    assert result["foreign_frames"] == 1
