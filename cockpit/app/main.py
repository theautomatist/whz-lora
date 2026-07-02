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
  POST /api/coex               enable/disable coexistence scan
  GET  /api/events             SSE stream of live events (uplink/join/ack/nack/coex/state)
"""
import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from typing import Optional

import grpc
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from . import chirpstack as cs
from . import config
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

# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _grpc_channel, _grpc_token, _tenant_id, _app_id, _ingest

    campaign.set_loop(asyncio.get_running_loop())

    # Warn loudly when the cockpit ships with the placeholder password.
    if not config.COCKPIT_PASSWORD or config.COCKPIT_PASSWORD == "change-me":
        logger.warning(
            "COCKPIT_PASSWORD is the default placeholder 'change-me' — "
            "set a real password in .env before exposing this service on any network."
        )

    # Connect to ChirpStack gRPC with retries to tolerate slow stack start-up
    for attempt in range(10):
        try:
            ch = cs.get_channel()
            tok = cs.get_token(ch)
            tid = cs.find_tenant_id(ch, tok)
            aid = cs.find_app_id(ch, tok, tid)
            _grpc_channel, _grpc_token, _tenant_id, _app_id = ch, tok, tid, aid
            logger.info(
                "ChirpStack gRPC ready: tenant=%s app=%s", _tenant_id, _app_id
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

    # Start MQTT ingest
    if _app_id:
        _ingest = MQTTIngest(campaign, _app_id)
        _ingest.start()
    else:
        logger.warning("MQTT ingest not started — no app_id available")

    yield  # application is running

    # Shutdown
    if _ingest:
        _ingest.stop()
    if _grpc_channel:
        _grpc_channel.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Feldtest-Cockpit", version="0.1.0", lifespan=_lifespan)
_security = HTTPBasic()


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
        campaign.record_downlink_sent(req.dev_eui)
    except grpc.RpcError as e:
        raise HTTPException(status_code=502, detail=e.details())
    return {"status": "enqueued", "dev_eui": req.dev_eui, "f_port": req.f_port}


# ---------------------------------------------------------------------------
# Panel 5 — Coexistence scan
# ---------------------------------------------------------------------------


@app.post("/api/coex", dependencies=[Depends(_require_auth)])
async def toggle_coex(req: CoexRequest):
    campaign.toggle_coex(req.on)
    return {"coex": req.on}


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
