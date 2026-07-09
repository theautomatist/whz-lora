"""main.py — Feldtest-Cockpit FastAPI application.

Routes:
  GET  /                       serves static/index.html (HTTP 200, no redirect)
  GET  /healthz                unauthenticated health check
  GET  /api/devices            list devices in whz-feldtest
  POST /api/devices            register (find-or-create) an OTAA device
  POST /api/point              set current measurement-point metadata
  POST /api/recording          start/stop CSV recording
  GET  /api/csv                download current CSV file
  GET  /api/state              current dashboard snapshot (JSON)
  POST /api/downlink           enqueue a confirmed downlink
  POST /api/antenna            toggle antenna type tag
  POST /api/coex               no-op (kept for API compat) — "Funkumgebung" is
                                always-on; see /api/state's coex_* fields
  GET  /api/rf-environment     full RF-environment / spectrum survey snapshot (foreign
                                traffic: devices/networks/vendors/MType/heatmap/rate) —
                                aggregated from the persistent rf_frame log
  GET  /api/rf-environment/csv download the rf_frame survey log as CSV
  POST /api/phase              switch all devices to a fixed-SF or ADR device profile
  GET  /api/events             SSE stream of live events (uplink/join/ack/nack/coex/state/nodes)

  F-0006 Feldmess-Workflow (Phase A) — device-centric, no GPS:
  GET  /api/nodes              list nodes (devices + gateway) with placement + active run
  POST /api/placement          close current placement, open a new one (no run)
  POST /api/photo/{placement_id}   attach a photo (multipart, max 3 per placement)
  GET  /api/photo/{photo_id}   serve a photo
  POST /api/run/start          start a run (requires device + gateway placements)
  POST /api/run/stop           stop a device's active run
  POST /api/relocate           close run, new placement, start new run — one call
  POST /api/gateway/move       move the gateway (409 while any run is active)
  POST /api/gateway/move/force move the gateway, aborting active runs
  GET  /api/runs               run history — every run (F-0007 History view), or one
                                device's with ?node_id=; newest first, each entry carries
                                device + both placements' summaries and an overall PDR
  GET  /api/run/{id}/csv       download a run's CSV file
  GET  /api/run/{id}/series    per-run RSSI/SNR/SF time series for the "Verlauf" line chart
  GET  /api/run/{id}/stats     per-SF uplink + downlink PDR for one run (coverage that matters)

  F-0007 History / Analysis view (Phase 1) — browse past measurements:
  GET  /api/run/{id}/detail    run + device/gateway names + both placements (incl. photo_ids)
                                as they stood during the run; measurement data itself stays on
                                the /series, /stats, /csv, and /api/photo/{id} endpoints above

  F-0008 Map / Placement Editor (PoC) — drag node markers onto an uploaded map
  image; positions are image-relative fractions, not real-world coordinates:
  POST   /api/floorplan            upload a map image (multipart), becomes current
  GET    /api/floorplan            the current floorplan + its markers
  GET    /api/floorplan/{id}/image serve a floorplan image
  PUT    /api/marker               upsert a node's marker position on the current floorplan
  DELETE /api/marker/{node_id}     remove a node's marker from the current floorplan

  F-0006 Phase B — timed per-device SF-sweep on top of /api/run/start:
  optional duration_seconds/sf_schedule/interval_minutes switch the device
  through SF7 -> SF9 -> SF12 (default 24 h, 8 h each) on a 5-min send
  interval; a background task (started in the lifespan) advances/finishes
  sweeps every ~60 s. See scheduler.py for the pure decision logic.

  F-0006 "Trust & Sichtbarkeit" — always-on coexistence view (see
  ingest.py/state.py; no HTTP surface beyond the existing GET /api/state
  coex_* fields) + per-device config visibility:
  GET  /api/device/{node_id}/config-status   live uplink/downlink-queue status for one device
  POST /api/device/{node_id}/set-interval    manually enqueue the Vicki send-interval downlink

  F-0006 "Trust & Sichtbarkeit" — per-SF PDR (coverage that actually
  matters, not RSSI which barely varies with SF): POST /api/run/start's
  downlink_test flag + ingest.py's confirmed-downlink test feed
  GET /api/run/{id}/stats above.
"""
import asyncio
import base64
import csv
import datetime
import io
import json
import logging
import math
import mimetypes
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import grpc
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import chirpstack as cs
from . import config
from . import scheduler
from .db import MAX_PHOTOS_PER_PLACEMENT, RF_FRAME_COLUMNS, Database, parse_dl_counts
from .ingest import MQTTIngest
from .state import CampaignState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_static_dir = os.path.join(os.path.dirname(__file__), "static")

# ---------------------------------------------------------------------------
# Shared state (initialised in lifespan)
# ---------------------------------------------------------------------------

campaign = CampaignState(data_dir=config.DATA_DIR)
_ingest: Optional[MQTTIngest] = None
_grpc_channel: Optional[grpc.Channel] = None
_grpc_token: Optional[str] = None
_tenant_id: Optional[str] = None
_app_id: Optional[str] = None
_db: Optional[Database] = None
_gateway_node_id: Optional[int] = None
_sweep_task: Optional[asyncio.Task] = None

# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _grpc_channel, _grpc_token, _tenant_id, _app_id, _ingest, _db, _gateway_node_id, _sweep_task

    campaign.set_loop(asyncio.get_running_loop())

    # Warn loudly when the cockpit ships with the placeholder password.
    if not config.COCKPIT_PASSWORD or config.COCKPIT_PASSWORD == "change-me":
        logger.warning(
            "COCKPIT_PASSWORD is the default placeholder 'change-me' — "
            "set a real password in .env before exposing this service on any network."
        )

    # F-0006 persistence — local SQLite, no network dependency, so this
    # never needs a retry loop like the ChirpStack gRPC connect below.
    _db = Database(config.DB_PATH)
    _db.init_schema()
    campaign.set_db(_db)
    gw_node_id, gw_created = _db.upsert_node(
        "gateway", config.GATEWAY_NAME, config.GATEWAY_EUI
    )
    _gateway_node_id = gw_node_id
    logger.info(
        "Node sync: gateway %s (%s) -> node #%d (%s)",
        config.GATEWAY_NAME,
        config.GATEWAY_EUI,
        gw_node_id,
        "created" if gw_created else "found",
    )

    # Connect to ChirpStack gRPC with retries to tolerate slow stack start-up
    for attempt in range(10):
        try:
            ch = cs.get_channel()
            tok = cs.get_token(ch)
            tid, t_created = cs.find_or_create_tenant(ch, tok)
            aid, a_created = cs.find_or_create_application(ch, tok, tid)
            _grpc_channel, _grpc_token, _tenant_id, _app_id = ch, tok, tid, aid
            logger.info(
                "ChirpStack gRPC ready: tenant=%s (%s) app=%s (%s)",
                _tenant_id,
                "created" if t_created else "found",
                _app_id,
                "created" if a_created else "found",
            )
            break
        except Exception as e:
            logger.warning(
                "ChirpStack connect attempt %d/10 failed: %s", attempt + 1, e
            )
            if attempt < 9:
                await asyncio.sleep(3)
    else:
        logger.error(
            "ChirpStack gRPC not reachable after 10 attempts — cockpit degraded"
        )

    # Ensure all four device profiles exist (idempotent; resilient — a missing
    # ADR plugin just logs a warning and does not crash the cockpit). SF7 was
    # added in Phase B for the automatic SF-sweep (SF7 -> SF9 -> SF12).
    if _grpc_channel and _tenant_id:
        _PROFILE_SPECS = [
            (config.PROFILE_NAME, "default"),
            (config.PROFILE_SF9,  "fixed_dr3"),
            (config.PROFILE_SF12, "fixed_dr0"),
            (config.PROFILE_SF7,  "fixed_dr5"),
        ]
        for prof_name, adr_id in _PROFILE_SPECS:
            try:
                _, p_created = cs.find_or_create_profile(
                    _grpc_channel, _grpc_token, _tenant_id, prof_name, adr_id
                )
                logger.info(
                    "Device profile %r (adr=%s): %s",
                    prof_name,
                    adr_id,
                    "created" if p_created else "found",
                )
            except Exception as e:
                logger.warning(
                    "Could not provision profile %r (adr=%s): %s — "
                    "POST /api/phase %r will 502 until this is resolved.",
                    prof_name,
                    adr_id,
                    e,
                    adr_id.replace("fixed_", "") if "fixed_" in adr_id else "adr",
                )

    # Fetch known DevAddrs for coex own/foreign classification (best-effort)
    if _grpc_channel and _app_id:
        try:
            devs = cs.list_devices(_grpc_channel, _grpc_token, _app_id)
            for d in devs:
                addr = cs.get_device_addr(
                    _grpc_channel, _grpc_token, d["dev_eui"]
                )
                if addr:
                    campaign.process_join(d["dev_eui"], addr)
        except Exception as e:
            logger.warning("Could not pre-fetch DevAddrs: %s", e)

    # Node sync — idempotently upsert every ChirpStack device as a `node`
    # row (kind='device') so the Feldmess-Workflow can reference it. The
    # gateway node was already ensured above (it does not depend on gRPC).
    if _grpc_channel and _app_id:
        try:
            for d in cs.list_devices(_grpc_channel, _grpc_token, _app_id):
                node_id, created = _db.upsert_node("device", d["name"], d["dev_eui"])
                logger.info(
                    "Node sync: device %s (%s) -> node #%d (%s)",
                    d["name"],
                    d["dev_eui"],
                    node_id,
                    "created" if created else "found",
                )
        except Exception as e:
            logger.warning("Node sync (devices) failed: %s", e)

    # Start MQTT ingest — gRPC channel/token (if available) enable the
    # per-SF downlink reliability test (F-0006 "Trust & Sichtbarkeit");
    # ingest degrades gracefully (test disabled) when they're None.
    if _app_id:
        _ingest = MQTTIngest(campaign, _app_id, _db, _grpc_channel, _grpc_token)
        _ingest.start()
    else:
        logger.warning("MQTT ingest not started — no app_id available")

    # F-0006 Phase B — background task advancing/finishing per-device
    # SF-sweeps every ~60 s. Cancelled cleanly on shutdown below.
    _sweep_task = asyncio.create_task(_sf_sweep_loop())

    yield  # application is running

    # Shutdown
    if _sweep_task:
        _sweep_task.cancel()
        try:
            await _sweep_task
        except asyncio.CancelledError:
            pass
    if _ingest:
        _ingest.stop()
    if _grpc_channel:
        _grpc_channel.close()
    if _db:
        _db.close()


# ---------------------------------------------------------------------------
# F-0006 Phase B — background SF-sweep scheduler
#
# Polls every ~60 s (scheduler.POLL_INTERVAL_SECONDS); each run is wrapped
# in its own try/except so one failure doesn't stop the others from being
# checked. The pure decision (scheduler.evaluate_run_schedule) is unit-
# tested directly — this loop is just DB/gRPC/SSE glue around it.
# ---------------------------------------------------------------------------


async def _sf_sweep_loop() -> None:
    while True:
        try:
            await asyncio.sleep(scheduler.POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        try:
            _sf_sweep_tick()
        except Exception:
            logger.exception("SF-sweep scheduler tick failed")


def _sf_sweep_tick() -> None:
    if _db is None:
        return
    for run in _db.list_running_runs():
        try:
            _process_run_sweep(run)
        except Exception as e:
            logger.warning("SF-sweep: run #%s failed: %s", run.get("id"), e)


def _process_run_sweep(run: dict) -> None:
    schedule = scheduler.parse_schedule(run.get("sf_schedule"))
    if not schedule:
        return  # Phase A fixed run — no sweep, nothing to do

    now = datetime.datetime.now(datetime.timezone.utc)
    started_at = scheduler.parse_iso(run["started_at"])
    segment_started_at = scheduler.parse_iso(run.get("segment_started_at")) or started_at
    segment_index = run.get("segment_index") or 0

    decision = scheduler.evaluate_run_schedule(
        now, started_at, segment_started_at, segment_index, schedule, run.get("planned_seconds")
    )

    if decision["advance"]:
        next_index = decision["next_index"]
        next_sf = schedule[next_index]["sf"]
        node = _db.get_node(run["device_node_id"])
        if node:
            _switch_device_profile_best_effort(node["eui"], next_sf)
        _db.advance_run_segment(run["id"], next_index, now.isoformat(timespec="seconds"))
        campaign.broadcast_event({"type": "nodes"})
    elif decision["done"]:
        _db.stop_run(run["id"], status="done", reason="schedule-complete")
        campaign.broadcast_event({"type": "nodes"})


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Feldtest-Cockpit", version="0.1.0", lifespan=_lifespan)
_security = HTTPBasic()


@app.middleware("http")
async def _basic_auth_middleware(request: Request, call_next):
    """Challenge EVERY request with HTTP Basic (except /healthz) so a browser is
    prompted for credentials on page load and then sends them with the /static
    and /api requests too — a bare `fetch()` never triggers the auth dialog on a
    401, which otherwise leaves the SPA stuck 'loading' once the page (served
    unauthenticated) can't reach the API. Also closes the previously
    unauthenticated static-UI gap."""
    if request.url.path == "/healthz":
        return await call_next(request)
    header = request.headers.get("authorization", "")
    authorized = False
    if header.startswith("Basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
            authorized = (
                secrets.compare_digest(user, config.COCKPIT_USER)
                and secrets.compare_digest(pw, config.COCKPIT_PASSWORD)
            )
        except Exception:
            authorized = False
    if not authorized:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Feldtest-Cockpit"'},
        )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


def _require_auth(
    credentials: HTTPBasicCredentials = Depends(_security),
) -> HTTPBasicCredentials:
    """HTTP Basic auth guard using secrets.compare_digest (timing-safe)."""
    ok_user = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        config.COCKPIT_USER.encode("utf-8"),
    )
    ok_pass = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        config.COCKPIT_PASSWORD.encode("utf-8"),
    )
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials


# ---------------------------------------------------------------------------
# gRPC availability helper
# ---------------------------------------------------------------------------


def _grpc() -> tuple:
    """Return (channel, token, tenant_id, app_id) or raise 503."""
    if not all([_grpc_channel, _grpc_token, _tenant_id, _app_id]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ChirpStack gRPC not available; check logs.",
        )
    return _grpc_channel, _grpc_token, _tenant_id, _app_id


def _dbh() -> Database:
    """Return the shared Database instance or raise 503."""
    if _db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available; check logs.",
        )
    return _db


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RegisterDeviceRequest(BaseModel):
    name: str
    dev_eui: str
    app_key: str
    join_eui: str = "0000000000000000"


class PointRequest(BaseModel):
    pos_id: str
    floor: str = ""
    room: str = ""
    point_type: str = ""
    path: str = ""
    los: str = ""
    mounting: str = ""
    expected_n: Optional[int] = None


class RecordingRequest(BaseModel):
    on: bool


class DownlinkRequest(BaseModel):
    dev_eui: str
    f_port: int
    data_hex: str = "00"
    count: bool = True  # when False, skip record_downlink_sent (keep-alive/config commands)

    @field_validator("f_port")
    @classmethod
    def _check_f_port(cls, v: int) -> int:
        if not 1 <= v <= 223:
            raise ValueError("f_port must be between 1 and 223")
        return v

    @field_validator("data_hex")
    @classmethod
    def _check_data_hex(cls, v: str) -> str:
        v = v.strip()
        if len(v) % 2 != 0:
            raise ValueError("data_hex must have an even number of hex digits")
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("data_hex contains non-hex characters")
        return v


class AntennaRequest(BaseModel):
    type: str  # '3dbi' or '12dbi'


class CoexRequest(BaseModel):
    on: bool


class PhaseRequest(BaseModel):
    phase: str

    @field_validator("phase")
    @classmethod
    def _check_phase(cls, v: str) -> str:
        if v not in ("sf9", "sf12", "adr"):
            raise ValueError("phase must be 'sf9', 'sf12', or 'adr'")
        return v


# ---------------------------------------------------------------------------
# F-0006 Feldmess-Workflow — request models
# ---------------------------------------------------------------------------


class PlacementRequest(BaseModel):
    node_id: int
    floor: str = ""
    room: str = ""
    description: str = ""
    note: str = ""
    antenna: str = ""


class SFSegment(BaseModel):
    """One leg of a Phase B SF-sweep, e.g. {"sf": 7, "seconds": 28800}."""

    sf: int
    seconds: int

    @field_validator("sf")
    @classmethod
    def _check_sf(cls, v: int) -> int:
        if v not in (7, 9, 12):
            raise ValueError("sf must be 7, 9, or 12")
        return v

    @field_validator("seconds")
    @classmethod
    def _check_seconds(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("seconds must be positive")
        return v


class RunStartRequest(BaseModel):
    device_node_id: int
    # Phase B — all optional; omitting all three keeps the exact Phase A
    # behaviour (a plain fixed run, no SF-sweep, no gRPC side effects).
    duration_seconds: Optional[int] = None
    sf_schedule: Optional[list[SFSegment]] = None
    interval_minutes: Optional[int] = None
    # "Trust & Sichtbarkeit" — per-SF confirmed-downlink reliability test,
    # on by default; only actually fires for a sweep run (see
    # db.maybe_trigger_downlink_test), so it is harmless on a plain run too.
    downlink_test: bool = True

    @field_validator("interval_minutes")
    @classmethod
    def _check_interval(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1 <= v <= 255):
            raise ValueError("interval_minutes must be between 1 and 255")
        return v


class RunStopRequest(BaseModel):
    device_node_id: int
    reason: Optional[str] = None


class RelocateRequest(BaseModel):
    device_node_id: int
    floor: str = ""
    room: str = ""
    description: str = ""
    note: str = ""
    antenna: str = ""


class GatewayMoveRequest(BaseModel):
    floor: str = ""
    room: str = ""
    description: str = ""
    note: str = ""


class SetIntervalRequest(BaseModel):
    """F-0006 "Trust & Sichtbarkeit" — POST /api/device/{node_id}/set-interval."""

    minutes: int

    @field_validator("minutes")
    @classmethod
    def _check_minutes(cls, v: int) -> int:
        if not 1 <= v <= 255:
            raise ValueError("minutes must be between 1 and 255")
        return v


class MarkerUpsertRequest(BaseModel):
    """F-0008 Map / Placement Editor (PoC) — PUT /api/marker. x/y are
    fractions (0..1) of the current floorplan image, not real-world
    coordinates — see the floorplan/map_marker table comments in db.py."""

    node_id: int
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


# Map logical phase names to ChirpStack device-profile names
_PHASE_PROFILES: dict[str, str] = {
    "sf9":  config.PROFILE_SF9,
    "sf12": config.PROFILE_SF12,
    "adr":  config.PROFILE_NAME,
}


# ---------------------------------------------------------------------------
# Unauthenticated endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Unauthenticated liveness probe — returns 200 when the process is up."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def _root():
    """Serve index.html directly (HTTP 200, no redirect)."""
    return FileResponse(os.path.join(_static_dir, "index.html"))


# ---------------------------------------------------------------------------
# Panel 1 — Device registration
# Handlers are plain `def` so FastAPI runs them in the threadpool — blocking
# gRPC stubs must not run in the async event loop.
# ---------------------------------------------------------------------------


@app.get("/api/devices", dependencies=[Depends(_require_auth)])
def list_devices():
    channel, token, _, app_id = _grpc()
    try:
        devices = cs.list_devices(channel, token, app_id)
    except grpc.RpcError as e:
        raise HTTPException(status_code=502, detail=e.details())
    return {"devices": devices}


@app.post("/api/devices", dependencies=[Depends(_require_auth)])
def register_device(req: RegisterDeviceRequest):
    channel, token, tenant_id, app_id = _grpc()
    try:
        profile_id = cs.find_profile_id(channel, token, tenant_id)
        dev_eui = cs.register_device(
            channel,
            token,
            app_id,
            profile_id,
            req.name,
            req.dev_eui,
            req.app_key,
            req.join_eui,
        )
    except grpc.RpcError as e:
        raise HTTPException(status_code=502, detail=e.details())
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"dev_eui": dev_eui, "status": "registered"}


# ---------------------------------------------------------------------------
# Panel 2 — Measurement point + CSV
# ---------------------------------------------------------------------------


@app.post("/api/point", dependencies=[Depends(_require_auth)])
async def set_point(req: PointRequest):
    campaign.set_point(
        req.pos_id,
        req.floor,
        req.room,
        req.point_type,
        req.path,
        req.los,
        req.mounting,
        req.expected_n,
    )
    return {"pos_id": req.pos_id, "status": "set"}


@app.post("/api/recording", dependencies=[Depends(_require_auth)])
async def toggle_recording(req: RecordingRequest):
    if req.on:
        path = campaign.start_recording()
        return {"recording": True, "csv_path": path}
    path = campaign.stop_recording()
    return {"recording": False, "csv_path": path}


@app.get("/api/csv", dependencies=[Depends(_require_auth)])
async def download_csv():
    path = campaign.current_csv_path()
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No CSV file recorded yet.")
    return FileResponse(
        path, media_type="text/csv", filename=os.path.basename(path)
    )


# ---------------------------------------------------------------------------
# Panel 3 — Dashboard snapshot
# ---------------------------------------------------------------------------


@app.get("/api/state", dependencies=[Depends(_require_auth)])
async def get_state():
    return campaign.get_dashboard()


# ---------------------------------------------------------------------------
# Panel 4 — Downlink loopback
# Plain `def` — gRPC Enqueue must not block the event loop.
# ---------------------------------------------------------------------------


@app.post("/api/downlink", dependencies=[Depends(_require_auth)])
def enqueue_downlink(req: DownlinkRequest):
    channel, token, _, _ = _grpc()
    try:
        cs.enqueue_downlink(channel, token, req.dev_eui, req.f_port, req.data_hex)
        if req.count:
            campaign.record_downlink_sent(req.dev_eui)
    except grpc.RpcError as e:
        raise HTTPException(status_code=502, detail=e.details())
    return {"status": "enqueued", "dev_eui": req.dev_eui, "f_port": req.f_port}


# ---------------------------------------------------------------------------
# Panel 5 — Coexistence scan
# ---------------------------------------------------------------------------


@app.post("/api/coex", dependencies=[Depends(_require_auth)])
async def toggle_coex(req: CoexRequest):
    """No-op — kept for API backward-compatibility only.

    "Funkumgebung" (F-0006 "Trust & Sichtbarkeit") is always-on: the gateway
    physically receives every LoRa frame in range regardless of any toggle,
    so this endpoint no longer gates anything. GET /api/state always carries
    live coex_frames/coex_own_frames/coex_foreign_frames counts.
    """
    return {"coex": True}


@app.get("/api/rf-environment", dependencies=[Depends(_require_auth)])
async def rf_environment():
    """Full RF-environment / spectrum survey snapshot (F-0006) — foreign-
    traffic detail (per-device, per-network, per-vendor from joins, MType
    breakdown, foreign-only per-(channel,SF) matrix, frames/min + a short
    sparkline) on top of the always-on coex classification.

    Aggregated straight from the persistent rf_frame log (see
    Database.get_rf_environment), not from in-memory state — so this
    reflects the whole campaign's recording, survives a cockpit restart,
    and a page reload shows the accumulated data."""
    return _dbh().get_rf_environment()


@app.get("/api/rf-environment/csv", dependencies=[Depends(_require_auth)])
async def rf_environment_csv():
    """Export the full rf_frame survey log as CSV — a research artifact on
    top of the aggregated /api/rf-environment snapshot."""
    rows = _dbh().list_rf_frames()
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=RF_FRAME_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    filename = f"rf_environment_{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Panel 6 — Antenna toggle
# ---------------------------------------------------------------------------


@app.post("/api/antenna", dependencies=[Depends(_require_auth)])
async def set_antenna(req: AntennaRequest):
    if req.type not in ("3dbi", "12dbi"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="type must be '3dbi' or '12dbi'",
        )
    campaign.set_antenna(req.type)
    return {"antenna": req.type}


# ---------------------------------------------------------------------------
# Panel 0 — Phase / fixed-SF switch
# Plain `def` — gRPC DeviceService calls must not block the event loop.
# ---------------------------------------------------------------------------


def _apply_phase_to_devices(
    channel: grpc.Channel,
    token: str,
    app_id: str,
    profile_id: str,
) -> tuple[list, list]:
    """Switch all devices in *app_id* to *profile_id*.

    Returns (switched, failed) where:
      switched — list of dev_eui strings that succeeded
      failed   — list of {dev_eui, error} dicts for RpcError failures
    """
    devices = cs.list_devices(channel, token, app_id)
    switched: list[str] = []
    failed: list[dict] = []
    for d in devices:
        try:
            cs.set_device_profile(channel, token, d["dev_eui"], profile_id)
            switched.append(d["dev_eui"])
        except grpc.RpcError as e:
            failed.append({"dev_eui": d["dev_eui"], "error": e.details()})
    return switched, failed


@app.post("/api/phase", dependencies=[Depends(_require_auth)])
def set_phase(req: PhaseRequest):
    """Switch every device in the application to the profile matching *phase*.

    campaign.set_phase is called ONLY when all devices switched successfully.
    On partial failure, returns HTTP 502 with {phase, switched, failed} so the
    frontend can surface which devices failed without mislabelling the campaign
    phase in the CSV.
    """
    channel, token, tenant_id, app_id = _grpc()
    profile_name = _PHASE_PROFILES[req.phase]
    try:
        profile_id = cs.find_profile_id_by_name(channel, token, tenant_id, profile_name)
    except (ValueError, grpc.RpcError) as e:
        raise HTTPException(
            status_code=502,
            detail=f"Cannot find profile {profile_name!r}: {e}",
        )
    try:
        switched, failed = _apply_phase_to_devices(channel, token, app_id, profile_id)
    except grpc.RpcError as e:
        raise HTTPException(status_code=502, detail=e.details())

    if failed:
        raise HTTPException(
            status_code=502,
            detail={"phase": req.phase, "switched": switched, "failed": failed},
        )
    campaign.set_phase(req.phase)
    return {"phase": req.phase, "switched": switched, "failed": failed}


# ---------------------------------------------------------------------------
# F-0006 Feldmess-Workflow (Phase A) — nodes, placements, photos, runs
#
# Device-centric field-measurement workflow layered on top of the panels
# above. No GPS: a "placement" is floor/room/description, not coordinates.
# Persistence lives in db.py (SQLite); this section is HTTP glue only.
# ---------------------------------------------------------------------------


def _run_entry(run: dict) -> dict:
    """Shape a run row for the API: base fields + Phase B sweep summary
    (planned_seconds/elapsed_seconds/current_sf/segment_index/progress/
    sf_schedule/done) via scheduler.run_summary_fields — works for both
    sweep and Phase A fixed runs."""
    entry = {
        "id": run["id"],
        "status": run["status"],
        "packets": run["packets"],
        "started_at": run["started_at"],
        # F-0006 "Trust & Sichtbarkeit" — the frontend needs the run's target
        # send interval to judge the device's measured cadence against it.
        "interval_minutes": run.get("interval_minutes"),
    }
    entry.update(scheduler.run_summary_fields(run))
    return entry


@app.get("/api/nodes", dependencies=[Depends(_require_auth)])
async def list_nodes():
    """List every node (devices + the gateway) with its current placement
    (including attached photo_ids) and, for devices, the active run (if
    any) plus the most recent run regardless of status (last_run) — the
    latter lets the frontend show a "fertig" badge right after a sweep
    completes, since it is no longer "active" at that point."""
    d = _dbh()
    out = []
    for n in d.list_nodes():
        placement = d.get_active_placement(n["id"])
        if placement is not None:
            placement = dict(placement)
            placement["photo_ids"] = [p["id"] for p in d.list_photos(placement["id"])]
        entry = {
            "id": n["id"],
            "kind": n["kind"],
            "name": n["name"],
            "eui": n["eui"],
            "placement": placement,
        }
        if n["kind"] == "device":
            active = d.get_active_run(n["id"])
            entry["active_run"] = _run_entry(active) if active else None
            last = d.get_last_run(n["id"])
            entry["last_run"] = _run_entry(last) if last else None
        out.append(entry)
    return {"nodes": out}


@app.post("/api/placement", dependencies=[Depends(_require_auth)])
async def create_placement(req: PlacementRequest):
    """Close the node's current active placement (if any) and open a new one.

    Does NOT start a run — call POST /api/run/start (or /api/relocate, which
    combines both) for that.
    """
    d = _dbh()
    node = d.get_node(req.node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    placement_id = d.create_placement(
        req.node_id, req.floor, req.room, req.description, req.note, req.antenna
    )
    campaign.broadcast_event({"type": "nodes"})
    return {"placement_id": placement_id}


@app.post("/api/photo/{placement_id}", dependencies=[Depends(_require_auth)])
async def upload_photo(placement_id: int, file: UploadFile = File(...)):
    """Attach a photo to a placement. Max MAX_PHOTOS_PER_PLACEMENT (409 above that)."""
    d = _dbh()
    if d.get_placement(placement_id) is None:
        raise HTTPException(status_code=404, detail="placement not found")

    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    dir_path = os.path.join(config.PHOTOS_DIR, str(placement_id))
    os.makedirs(dir_path, exist_ok=True)
    n = d.count_photos(placement_id) + 1
    filename = f"{n}{ext}"
    dest = os.path.join(dir_path, filename)

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    try:
        photo_id = d.add_photo(placement_id, filename)
    except ValueError:
        os.remove(dest)
        raise HTTPException(
            status_code=409,
            detail=f"placement already has the maximum of "
            f"{MAX_PHOTOS_PER_PLACEMENT} photos",
        )

    campaign.broadcast_event({"type": "nodes"})
    return {"photo_id": photo_id, "count": d.count_photos(placement_id)}


@app.get("/api/photo/{photo_id}", dependencies=[Depends(_require_auth)])
async def get_photo(photo_id: int):
    d = _dbh()
    photo = d.get_photo(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="photo not found")
    path = os.path.join(config.PHOTOS_DIR, str(photo["placement_id"]), photo["filename"])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="photo file missing on disk")
    media_type, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=media_type or "application/octet-stream")


# ---------------------------------------------------------------------------
# F-0008 Map / Placement Editor (PoC) — drag node markers onto an uploaded
# map image. Explicitly a placeholder: the first real map is an isometric
# building view whose perspective distorts real coordinates, so x/y are
# fractions (0..1) of the image, not real-world positions — this is about
# the editor UX + persistence, not accurate positioning yet. A new upload
# simply becomes the current floorplan (the most recently uploaded row);
# older floorplans/markers are kept, not surfaced. Reboot-safe: same
# SQLite DB as everything else, images under /data/floorplans/.
# ---------------------------------------------------------------------------


@app.post("/api/floorplan", dependencies=[Depends(_require_auth)])
async def upload_floorplan(file: UploadFile = File(...), name: str = Form("")):
    """Upload a map image — any image is fine (the isometric PoC JPEG now,
    a real floor plan later); becomes the current floorplan."""
    d = _dbh()
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    os.makedirs(config.FLOORPLANS_DIR, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"floorplan_{ts}{ext}"
    dest = os.path.join(config.FLOORPLANS_DIR, filename)

    content = await file.read()
    with open(dest, "wb") as f:
        f.write(content)

    fp = d.create_floorplan(name.strip() or file.filename or "Map", filename)
    return {"id": fp["id"], "name": fp["name"], "image_url": f"/api/floorplan/{fp['id']}/image"}


@app.get("/api/floorplan", dependencies=[Depends(_require_auth)])
async def get_current_floorplan():
    """The current floorplan (most recently uploaded) + its markers, joined
    with each node's name/kind. {"floorplan": null, "markers": []} when
    nothing has been uploaded yet."""
    d = _dbh()
    fp = d.get_current_floorplan()
    if fp is None:
        return {"floorplan": None, "markers": []}
    return {
        "floorplan": {
            "id": fp["id"],
            "name": fp["name"],
            "image_url": f"/api/floorplan/{fp['id']}/image",
        },
        "markers": d.list_markers(fp["id"]),
    }


@app.get("/api/floorplan/{floorplan_id}/image", dependencies=[Depends(_require_auth)])
async def get_floorplan_image(floorplan_id: int):
    d = _dbh()
    fp = d.get_floorplan(floorplan_id)
    if fp is None:
        raise HTTPException(status_code=404, detail="floorplan not found")
    path = os.path.join(config.FLOORPLANS_DIR, fp["image_filename"])
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="floorplan image missing on disk")
    media_type, _ = mimetypes.guess_type(path)
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@app.put("/api/marker", dependencies=[Depends(_require_auth)])
async def upsert_marker(req: MarkerUpsertRequest):
    """Upsert a node's marker position (x,y as fractions 0..1) on the
    current floorplan — one marker per node, unique per (floorplan, node)."""
    d = _dbh()
    fp = d.get_current_floorplan()
    if fp is None:
        raise HTTPException(status_code=404, detail="no floorplan uploaded yet")
    if d.get_node(req.node_id) is None:
        raise HTTPException(status_code=404, detail="node not found")
    d.upsert_marker(fp["id"], req.node_id, req.x, req.y)
    return {"ok": True}


@app.delete("/api/marker/{node_id}", dependencies=[Depends(_require_auth)])
async def remove_marker(node_id: int):
    """Remove a node's marker from the current floorplan — a no-op (still
    200) if it wasn't on the map."""
    d = _dbh()
    fp = d.get_current_floorplan()
    if fp is None:
        raise HTTPException(status_code=404, detail="no floorplan uploaded yet")
    d.delete_marker(fp["id"], node_id)
    return {"ok": True}


def _resolve_run_placements(
    d: Database, device_node_id: int, gateway_node_id: Optional[int]
) -> tuple[Optional[dict], Optional[dict], list[str]]:
    """Return (device_placement, gateway_placement, missing).

    *missing* lists human-readable reasons a run cannot start right now —
    empty when both placements are active. Pure w.r.t. HTTP, so it is
    unit-testable without a running FastAPI app (mirrors
    _apply_phase_to_devices above).
    """
    device_placement = d.get_active_placement(device_node_id)
    gateway_placement = (
        d.get_active_placement(gateway_node_id) if gateway_node_id else None
    )
    missing: list[str] = []
    if device_placement is None:
        missing.append("device has no active placement")
    if gateway_placement is None:
        missing.append("gateway has no active placement")
    return device_placement, gateway_placement, missing


def _resolve_schedule(
    req: RunStartRequest,
) -> tuple[Optional[list], Optional[int], Optional[int]]:
    """Pure: derive (sf_schedule, planned_seconds, interval_minutes) from a
    RunStartRequest. Unit-testable without HTTP/DB/gRPC.

    Returns (None, None, None) — no sweep — unless the caller supplied at
    least one of duration_seconds/sf_schedule/interval_minutes; a bare
    {device_node_id} request therefore behaves exactly like Phase A, with
    no ChirpStack side effects at all (keeps every existing test passing).

    Defaults applied once a sweep IS requested: duration_seconds=86400
    (24 h), sf_schedule=SF7/SF9/SF12 each duration_seconds/3,
    interval_minutes=5.
    """
    sweep_requested = (
        req.duration_seconds is not None
        or bool(req.sf_schedule)
        or req.interval_minutes is not None
    )
    if not sweep_requested:
        return None, None, None

    duration_seconds = (
        req.duration_seconds
        if req.duration_seconds is not None
        else scheduler.DEFAULT_DURATION_SECONDS
    )
    if req.sf_schedule:
        sf_schedule = [{"sf": seg.sf, "seconds": seg.seconds} for seg in req.sf_schedule]
        planned_seconds = (
            req.duration_seconds
            if req.duration_seconds is not None
            else sum(seg["seconds"] for seg in sf_schedule)
        )
    else:
        sf_schedule = scheduler.default_sf_schedule(duration_seconds)
        planned_seconds = duration_seconds

    interval_minutes = (
        req.interval_minutes
        if req.interval_minutes is not None
        else scheduler.DEFAULT_INTERVAL_MINUTES
    )
    return sf_schedule, planned_seconds, interval_minutes


def _switch_device_profile_best_effort(dev_eui: str, sf: int) -> None:
    """Best-effort SF-profile switch — logs and returns on failure instead
    of raising: the DB-side run/segment state has already been committed
    and should not be rolled back over a transient ChirpStack hiccup
    (mirrors the resilience pattern used for profile provisioning in the
    lifespan above)."""
    if not (_grpc_channel and _grpc_token and _tenant_id):
        logger.warning(
            "SF-sweep: ChirpStack gRPC not available — cannot switch %s to SF%s",
            dev_eui, sf,
        )
        return
    profile_name = config.SF_PROFILES.get(sf)
    if not profile_name:
        logger.warning("SF-sweep: no profile mapped for SF%s", sf)
        return
    try:
        profile_id = cs.find_profile_id_by_name(
            _grpc_channel, _grpc_token, _tenant_id, profile_name
        )
        cs.set_device_profile(_grpc_channel, _grpc_token, dev_eui, profile_id)
    except (ValueError, grpc.RpcError) as e:
        logger.warning(
            "SF-sweep: could not switch %s to SF%s (%s): %s", dev_eui, sf, profile_name, e
        )


def _apply_sweep_start_side_effects(dev_eui: str, first_sf: int, interval_minutes: int) -> None:
    """On run start with a sweep: switch to the first segment's SF profile
    and enqueue the Vicki send-interval downlink to put the device "im
    Raster". Both best-effort — see _switch_device_profile_best_effort.

    0x02 = Vicki SetSendPeriod; e.g. interval_minutes=5 -> data_hex="0205".
    Calls cs.enqueue_downlink directly (bypassing POST /api/downlink), so
    campaign.record_downlink_sent is never invoked — equivalent to
    count=False, keeping this keep-alive-style command out of the DL-PDR
    denominator.
    """
    _switch_device_profile_best_effort(dev_eui, first_sf)
    if not (_grpc_channel and _grpc_token):
        return
    try:
        cs.enqueue_downlink(_grpc_channel, _grpc_token, dev_eui, 1, f"02{interval_minutes:02x}")
    except grpc.RpcError as e:
        logger.warning("SF-sweep: could not enqueue interval downlink for %s: %s", dev_eui, e)


@app.post("/api/run/start", dependencies=[Depends(_require_auth)])
def start_run(req: RunStartRequest):
    """Start a run for a device. Requires an active placement for both the
    device and the gateway; else 409 with a clear message.

    Phase B: passing duration_seconds/sf_schedule/interval_minutes starts a
    timed SF-sweep instead of a plain fixed run — see _resolve_schedule for
    the defaulting rules. The response is the raw run row merged with its
    scheduler.run_summary_fields (progress=0 at the very start)."""
    d = _dbh()
    node = d.get_node(req.device_node_id)
    if node is None or node["kind"] != "device":
        raise HTTPException(status_code=404, detail="device node not found")
    if d.get_active_run(req.device_node_id):
        raise HTTPException(
            status_code=409, detail="a run is already active for this device"
        )

    device_placement, gateway_placement, missing = _resolve_run_placements(
        d, req.device_node_id, _gateway_node_id
    )
    if missing:
        raise HTTPException(status_code=409, detail="; ".join(missing))

    sf_schedule, planned_seconds, interval_minutes = _resolve_schedule(req)

    run = d.start_run(
        req.device_node_id,
        device_placement["id"],
        gateway_placement["id"],
        campaign.get_phase(),
        config.DATA_DIR,
        node["eui"],
        planned_seconds=planned_seconds,
        sf_schedule=sf_schedule,
        interval_minutes=interval_minutes,
        downlink_test=req.downlink_test,
    )

    if sf_schedule:
        _apply_sweep_start_side_effects(node["eui"], sf_schedule[0]["sf"], interval_minutes)

    campaign.broadcast_event({"type": "nodes"})
    run = dict(run)
    run.update(scheduler.run_summary_fields(run))
    return run


@app.post("/api/run/stop", dependencies=[Depends(_require_auth)])
async def stop_run(req: RunStopRequest):
    d = _dbh()
    run_id = d.stop_active_run_for_device(
        req.device_node_id, status="done", reason=req.reason
    )
    if run_id is None:
        raise HTTPException(status_code=404, detail="no active run for this device")
    campaign.broadcast_event({"type": "nodes"})
    return {"run_id": run_id, "status": "done"}


@app.post("/api/relocate", dependencies=[Depends(_require_auth)])
def relocate(req: RelocateRequest):
    """Core action: close any active run, create a new placement, start a
    new run — atomically from the caller's point of view (one API call)."""
    d = _dbh()
    node = d.get_node(req.device_node_id)
    if node is None or node["kind"] != "device":
        raise HTTPException(status_code=404, detail="device node not found")
    gateway_placement = (
        d.get_active_placement(_gateway_node_id) if _gateway_node_id else None
    )
    if gateway_placement is None:
        raise HTTPException(
            status_code=409, detail="gateway has no active placement — set one first"
        )

    d.stop_active_run_for_device(req.device_node_id, status="done", reason="relocated")
    placement_id = d.create_placement(
        req.device_node_id, req.floor, req.room, req.description, req.note, req.antenna
    )
    run = d.start_run(
        req.device_node_id,
        placement_id,
        gateway_placement["id"],
        campaign.get_phase(),
        config.DATA_DIR,
        node["eui"],
    )
    campaign.broadcast_event({"type": "nodes"})
    return {"placement_id": placement_id, "run_id": run["id"]}


def _open_runs_payload(running: list[dict]) -> list[dict]:
    return [
        {
            "device_node_id": r["device_node_id"],
            "name": r["device_name"],
            "run_id": r["id"],
            "started_at": r["started_at"],
            "packets": r["packets"],
        }
        for r in running
    ]


@app.post("/api/gateway/move", dependencies=[Depends(_require_auth)])
async def gateway_move(req: GatewayMoveRequest):
    """Move the gateway — GUARDED: refuses (409) while any device run is
    still 'running', listing the open runs so the operator can stop them."""
    d = _dbh()
    if _gateway_node_id is None:
        raise HTTPException(status_code=503, detail="gateway node not provisioned yet")

    running = d.list_running_runs()
    if running:
        raise HTTPException(
            status_code=409,
            detail={"open_runs": _open_runs_payload(running)},
        )
    placement_id = d.create_placement(
        _gateway_node_id, req.floor, req.room, req.description, req.note, ""
    )
    campaign.broadcast_event({"type": "nodes"})
    return {"placement_id": placement_id}


@app.post("/api/gateway/move/force", dependencies=[Depends(_require_auth)])
async def gateway_move_force(req: GatewayMoveRequest):
    """Acknowledge path for gateway/move: abort all running device runs
    (status='aborted', reason='gateway-move'; their CSV data is kept), then
    move the gateway."""
    d = _dbh()
    if _gateway_node_id is None:
        raise HTTPException(status_code=503, detail="gateway node not provisioned yet")

    d.abort_running_runs(reason="gateway-move")
    placement_id = d.create_placement(
        _gateway_node_id, req.floor, req.room, req.description, req.note, ""
    )
    campaign.broadcast_event({"type": "nodes"})
    return {"placement_id": placement_id}


@app.get("/api/runs", dependencies=[Depends(_require_auth)])
async def list_runs(node_id: Optional[int] = None):
    """Run history, newest first — every run across the whole campaign
    (F-0007 History view), or one device's with ?node_id= (the per-device
    History section in "Selected device / gateway" — unchanged behavior).

    floor/room/description are each placement as it stood at the time of
    the run (joined from db.py) — device AND gateway. Each entry also
    carries the Phase B sweep summary (planned_seconds/elapsed_seconds/
    current_sf/segment_index/progress/sf_schedule/done, frozen at ended_at
    for finished runs, live for a running one) and an overall uplink-PDR
    summary (see _compute_run_stats) — reading every run's CSV is fine at
    field-test campaign scale; there is no separate lightweight path."""
    d = _dbh()
    runs = d.list_runs(node_id)
    out = []
    for r in runs:
        entry = {
            "id": r["id"],
            "run_id": r["id"],  # F-0007 History view's preferred key name
            "status": r["status"],
            "phase": r["phase"],
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "reason": r["reason"],
            "packets": r["packets"],
            "csv_path": r["csv_path"],
            "device": {"name": r["device_name"], "eui": r["device_eui"]},
            "floor": r["d_floor"],
            "room": r["d_room"],
            "description": r["d_description"],
            "gateway_description": r["g_description"],
            # kept for backward compatibility with any existing caller
            "device_placement": {
                "floor": r["d_floor"],
                "room": r["d_room"],
                "description": r["d_description"],
            },
            "gateway_placement": {
                "floor": r["g_floor"],
                "room": r["g_room"],
                "description": r["g_description"],
            },
            "overall": _compute_run_stats(r)["overall"],
        }
        entry.update(scheduler.run_summary_fields(r))
        out.append(entry)
    return {"runs": out}


@app.get("/api/run/{run_id}/detail", dependencies=[Depends(_require_auth)])
async def run_detail(run_id: int):
    """Everything the F-0007 History detail view needs about one run beyond
    the measurement data itself (that stays on the existing /series,
    /stats, /csv, and /api/photo/{id} endpoints — not duplicated here): the
    run row (+ sweep summary, via _run_entry), the device and gateway node
    identities, and both placements as they stood during this run (floor/
    room/description/note[/antenna for the device]/started_at/ended_at/
    photo_ids)."""
    d = _dbh()
    run = d.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    device_node = d.get_node(run["device_node_id"])
    device_placement = d.get_placement(run["device_placement_id"])
    gateway_placement = d.get_placement(run["gateway_placement_id"])
    gateway_node = d.get_node(gateway_placement["node_id"]) if gateway_placement else None

    def _placement_summary(p: Optional[dict], include_antenna: bool = False) -> Optional[dict]:
        if p is None:
            return None
        out = {
            "floor": p["floor"],
            "room": p["room"],
            "description": p["description"],
            "note": p["note"],
            "started_at": p["started_at"],
            "ended_at": p["ended_at"],
            "photo_ids": [ph["id"] for ph in d.list_photos(p["id"])],
        }
        if include_antenna:
            out["antenna"] = p["antenna"]
        return out

    run_summary = _run_entry(run)
    run_summary["ended_at"] = run.get("ended_at")
    run_summary["phase"] = run.get("phase")
    run_summary["reason"] = run.get("reason")

    return {
        "run": run_summary,
        "device": {"name": device_node["name"], "eui": device_node["eui"]} if device_node else None,
        "gateway": {"name": gateway_node["name"], "eui": gateway_node["eui"]} if gateway_node else None,
        "device_placement": _placement_summary(device_placement, include_antenna=True),
        "gateway_placement": _placement_summary(gateway_placement),
    }


@app.get("/api/run/{run_id}/csv", dependencies=[Depends(_require_auth)])
async def download_run_csv(run_id: int):
    d = _dbh()
    run = d.get_run(run_id)
    if run is None or not run["csv_path"] or not os.path.exists(run["csv_path"]):
        raise HTTPException(status_code=404, detail="run CSV not found")
    return FileResponse(
        run["csv_path"], media_type="text/csv", filename=os.path.basename(run["csv_path"])
    )


# ---------------------------------------------------------------------------
# "Verlauf" line chart — per-run RSSI/SNR/SF time series — and the per-SF
# PDR stats below it (F-0006 "Trust & Sichtbarkeit" — coverage that actually
# matters is delivery reliability per SF, not RSSI, which barely changes
# with SF).
#
# Both parse the run's CSV file directly (that's where record_uplink_for_run
# writes per-uplink metrics; the sqlite `run` row only holds the summary/
# packet count) — pure w.r.t. HTTP/DB, so unit-testable without a running
# FastAPI app or a real run (mirrors _resolve_schedule above).
# ---------------------------------------------------------------------------

_RUN_SERIES_MAX_POINTS = 600  # downsample cap — keeps the SVG chart light


def _to_number(value, cast):
    """cast(value), or None for empty/invalid — CSV cells are '' when a
    metric was missing at write time (see db.py's record_uplink_for_run)."""
    if value in (None, ""):
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _read_run_csv_rows(csv_path: Optional[str]) -> list[dict]:
    """Read a run's CSV rows as dicts, or [] if csv_path is empty/missing —
    shared by _parse_run_series and _compute_run_stats below."""
    if not csv_path or not os.path.exists(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_run_series(
    csv_path: Optional[str], started_at: Optional[str], max_points: int = _RUN_SERIES_MAX_POINTS
) -> dict:
    """Return {"total": int, "points": [{"t","rssi","snr","sf","f_cnt"}, ...]}.

    total is the RAW row count (before downsampling); points is capped to
    *max_points* by keeping every Nth row when the CSV is larger. A missing/
    empty CSV — or a run with no started_at (defensive) — is not an error:
    it just yields no points, so the caller can always return HTTP 200.
    """
    started = scheduler.parse_iso(started_at)
    if started is None:
        return {"total": 0, "points": []}

    rows = _read_run_csv_rows(csv_path)
    total = len(rows)

    if total > max_points:
        step = math.ceil(total / max_points)
        rows = rows[::step]

    points = []
    for row in rows:
        ts = scheduler.parse_iso(row.get("timestamp_utc"))
        if ts is None:
            continue
        points.append({
            "t": (ts - started).total_seconds(),
            "rssi": _to_number(row.get("rssi_dbm"), float),
            "snr": _to_number(row.get("snr_db"), float),
            "sf": _to_number(row.get("sf"), int),
            "f_cnt": _to_number(row.get("f_cnt"), int),
        })
    return {"total": total, "points": points}


@app.get("/api/run/{run_id}/series", dependencies=[Depends(_require_auth)])
async def run_series(run_id: int):
    """Time series for the "Verlauf" line chart — RSSI/SNR/SF/f_cnt vs.
    seconds-since-start. A run with no packets yet (or whose CSV file is
    missing) is NOT an error — returns points: [] with HTTP 200 so the
    frontend can show its own empty state."""
    d = _dbh()
    run = d.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    series = _parse_run_series(run["csv_path"], run["started_at"])
    return {
        "run_id": run["id"],
        "started_at": run["started_at"],
        "planned_seconds": run.get("planned_seconds"),
        "sf_schedule": scheduler.parse_schedule(run.get("sf_schedule")),
        "total": series["total"],
        "points": series["points"],
    }


# ---------------------------------------------------------------------------
# Per-SF PDR stats — GET /api/run/{run_id}/stats
#
# Uplink PDR is derived from the CSV (expected from the run's COMMANDED
# interval_minutes — NOT the measured cadence, which would hide loss —
# received = CSV rows whose timestamp falls in that segment's time window).
# Downlink PDR comes from run.dl_counts, maintained by
# db.maybe_trigger_downlink_test/record_downlink_test_ack as confirmed
# downlinks are sent/acked (see db.py's "Trust & Sichtbarkeit" section).
# ---------------------------------------------------------------------------


def _segment_bounds(schedule: list[dict]) -> list[tuple[float, float]]:
    """Cumulative (start, end) offsets in seconds since started_at for each
    schedule segment, back-to-back in order."""
    bounds = []
    acc = 0.0
    for seg in schedule:
        bounds.append((acc, acc + seg["seconds"]))
        acc += seg["seconds"]
    return bounds


def _segment_index_for_offset(t: float, bounds: list[tuple[float, float]]) -> Optional[int]:
    """Which schedule segment does offset *t* (seconds since started_at)
    fall into? A t past the last boundary folds into the last segment
    (covers scheduler-tick lag and a manually-stopped run's tail packets);
    None for a negative offset (defensive — should not happen) or an empty
    schedule."""
    if t < 0 or not bounds:
        return None
    for i, (start, end) in enumerate(bounds):
        if start <= t < end:
            return i
    return len(bounds) - 1


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def _compute_run_stats(run: dict, now: Optional[datetime.datetime] = None) -> dict:
    """Return {"sf_stats": [...], "overall": {...}} — see module docstring
    above. Pure w.r.t. HTTP/DB beyond the already-fetched *run* row — only
    reads the CSV file, so unit-testable without a running app.
    """
    schedule = scheduler.parse_schedule(run.get("sf_schedule"))
    started_at = scheduler.parse_iso(run.get("started_at"))
    interval_minutes = run.get("interval_minutes")
    rows = _read_run_csv_rows(run.get("csv_path"))
    dl_counts = parse_dl_counts(run.get("dl_counts"))
    by_sf_dl = dl_counts.get("by_sf", {})

    if not schedule or not interval_minutes or started_at is None:
        # Phase A fixed run (or corrupted/legacy data) — no SF-segment
        # concept (no commanded interval to derive "expected" from); still
        # surface an overall row so the panel has *something* to show.
        rssi_vals = [v for v in (_to_number(r.get("rssi_dbm"), float) for r in rows) if v is not None]
        snr_vals = [v for v in (_to_number(r.get("snr_db"), float) for r in rows) if v is not None]
        dl_sent = sum(e.get("sent", 0) for e in by_sf_dl.values())
        dl_acked = sum(e.get("acked", 0) for e in by_sf_dl.values())
        overall = {
            "sf": None, "expected": None, "received": len(rows), "pdr": None,
            "rssi_avg": _avg(rssi_vals), "snr_avg": _avg(snr_vals),
            "dl_sent": dl_sent, "dl_acked": dl_acked,
            "dl_pdr": round(dl_acked / dl_sent, 4) if dl_sent else None,
        }
        return {"sf_stats": [], "overall": overall}

    if run.get("status") == "running":
        reference = now or datetime.datetime.now(datetime.timezone.utc)
    else:
        reference = scheduler.parse_iso(run.get("ended_at")) or now or datetime.datetime.now(
            datetime.timezone.utc
        )
    elapsed_total = max(0.0, (reference - started_at).total_seconds())

    bounds = _segment_bounds(schedule)
    buckets: list[list[dict]] = [[] for _ in schedule]
    for row in rows:
        ts = scheduler.parse_iso(row.get("timestamp_utc"))
        if ts is None:
            continue
        idx = _segment_index_for_offset((ts - started_at).total_seconds(), bounds)
        if idx is not None:
            buckets[idx].append(row)

    interval_s = interval_minutes * 60
    sf_stats = []
    total_expected = total_received = total_dl_sent = total_dl_acked = 0
    all_rssi: list[float] = []
    all_snr: list[float] = []

    for i, seg in enumerate(schedule):
        seg_start, seg_end = bounds[i]
        seg_elapsed = max(0.0, min(elapsed_total, seg_end) - seg_start)
        expected = round(seg_elapsed / interval_s)
        seg_rows = buckets[i]
        received = len(seg_rows)
        rssi_vals = [v for v in (_to_number(r.get("rssi_dbm"), float) for r in seg_rows) if v is not None]
        snr_vals = [v for v in (_to_number(r.get("snr_db"), float) for r in seg_rows) if v is not None]
        dl_entry = by_sf_dl.get(str(seg["sf"]), {})
        dl_sent = dl_entry.get("sent", 0)
        dl_acked = dl_entry.get("acked", 0)

        sf_stats.append({
            "sf": seg["sf"],
            "expected": expected,
            "received": received,
            "pdr": round(min(1.0, received / max(1, expected)), 4),
            "rssi_avg": _avg(rssi_vals),
            "snr_avg": _avg(snr_vals),
            "dl_sent": dl_sent,
            "dl_acked": dl_acked,
            "dl_pdr": round(dl_acked / dl_sent, 4) if dl_sent else None,
        })
        total_expected += expected
        total_received += received
        all_rssi.extend(rssi_vals)
        all_snr.extend(snr_vals)
        total_dl_sent += dl_sent
        total_dl_acked += dl_acked

    overall = {
        "sf": None,
        "expected": total_expected,
        "received": total_received,
        "pdr": round(min(1.0, total_received / max(1, total_expected)), 4),
        "rssi_avg": _avg(all_rssi),
        "snr_avg": _avg(all_snr),
        "dl_sent": total_dl_sent,
        "dl_acked": total_dl_acked,
        "dl_pdr": round(total_dl_acked / total_dl_sent, 4) if total_dl_sent else None,
    }
    return {"sf_stats": sf_stats, "overall": overall}


@app.get("/api/run/{run_id}/stats", dependencies=[Depends(_require_auth)])
async def run_stats(run_id: int):
    """Per-SF uplink PDR (expected from the commanded interval_minutes,
    never the measured one — that would hide loss) + downlink PDR (from
    confirmed-downlink tests, see db.maybe_trigger_downlink_test) for one
    run. A Phase A fixed run (no sf_schedule) gets sf_stats: [] and an
    overall-only summary."""
    d = _dbh()
    run = d.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    stats = _compute_run_stats(run)
    return {
        "run_id": run["id"],
        "downlink_test": bool(run.get("downlink_test")),
        "sf_stats": stats["sf_stats"],
        "overall": stats["overall"],
    }


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" — device config visibility
#
# LoRaWAN Class A only delivers a queued downlink right after the device's
# own next uplink — a silent device means nothing has reached it yet. These
# two endpoints let the operator see whether a config downlink actually
# landed (or is still waiting) and manually nudge the send interval without
# starting a run. Deliberately NOT embedded in GET /api/nodes (that endpoint
# must stay light); called only when a device is selected in the UI.
# ---------------------------------------------------------------------------


@app.get(
    "/api/device/{node_id}/config-status", dependencies=[Depends(_require_auth)]
)
def device_config_status(node_id: int):
    """last_uplink_at/interval_seconds/last_downlink_at (from CampaignState)
    + the device's live ChirpStack downlink queue. gRPC is best-effort here
    — an unavailable channel degrades to an empty queue rather than failing
    the whole call, since the uplink-side status is still useful on its own.
    """
    d = _dbh()
    node = d.get_node(node_id)
    if node is None or node["kind"] != "device":
        raise HTTPException(status_code=404, detail="device node not found")

    stats = campaign.get_device_uplink_stats(node["eui"])
    queued: list[dict] = []
    if _grpc_channel and _grpc_token:
        try:
            queued = cs.get_device_queue(_grpc_channel, _grpc_token, node["eui"])
        except grpc.RpcError as e:
            logger.warning(
                "config-status: GetQueue failed for %s: %s", node["eui"], e.details()
            )
    return {
        "last_uplink_at": stats["last_uplink_at"],
        "interval_seconds": stats["interval_seconds"],
        "queued": queued,
        "last_downlink_at": stats["last_downlink_at"],
    }


@app.post(
    "/api/device/{node_id}/set-interval", dependencies=[Depends(_require_auth)]
)
def set_device_interval(node_id: int, req: SetIntervalRequest):
    """Manually enqueue the Vicki send-interval downlink (0x02 SetSendPeriod)
    for one device, independent of any run — e.g. to nudge a device that
    drifted back to 5 min. Reuses the same "02"+minutes payload format as
    the automatic sweep-start side effect (_apply_sweep_start_side_effects)
    and, like it, does not call campaign.record_downlink_sent — a keep-
    alive-style config command, not a measurement round-trip for DL-PDR.
    """
    d = _dbh()
    node = d.get_node(node_id)
    if node is None or node["kind"] != "device":
        raise HTTPException(status_code=404, detail="device node not found")
    channel, token, _, _ = _grpc()
    try:
        cs.enqueue_downlink(channel, token, node["eui"], 1, f"02{req.minutes:02x}")
    except grpc.RpcError as e:
        raise HTTPException(status_code=502, detail=e.details())
    return {"status": "enqueued", "dev_eui": node["eui"], "minutes": req.minutes}


# ---------------------------------------------------------------------------
# SSE — live event stream
# ---------------------------------------------------------------------------


@app.get("/api/events")
async def sse_events(
    credentials: HTTPBasicCredentials = Depends(_require_auth),
):
    """Server-Sent Events stream.

    Event types: uplink, join, ack, nack, coex, state.
    A keep-alive comment is sent every 30 s to prevent proxy timeouts.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    campaign.subscribe(queue)

    async def _generate():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            campaign.unsubscribe(queue)

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Static assets (/static/app.js, /static/style.css, …)
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=_static_dir), name="static")
