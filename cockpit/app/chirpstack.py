"""chirpstack.py — gRPC wrapper for ChirpStack v4 API.

Handles authentication, device registration (OTAA), device listing,
DevAddr lookup, and confirmed-downlink enqueueing.

Follows the same patterns as scripts/smoke_test.py: API-key auth with
fallback to admin/admin JWT login; find-or-create semantics for devices.
Reference: scripts/register_device.py (same OTAA key-storage convention).
"""
import base64
import datetime
import functools
import json
import logging
import threading
import time

import grpc
from chirpstack_api.api import (
    application_pb2,
    application_pb2_grpc,
    device_pb2,
    device_pb2_grpc,
    device_profile_pb2,
    device_profile_pb2_grpc,
    internal_pb2,
    internal_pb2_grpc,
    tenant_pb2,
    tenant_pb2_grpc,
)
from chirpstack_api.common import common_pb2

from . import config

logger = logging.getLogger(__name__)

# Default deadline for every gRPC stub call.  A stalled ChirpStack would
# otherwise block the calling thread (and, for async handlers that forget to
# use run_in_executor, the event loop) indefinitely.
_GRPC_TIMEOUT = 10  # seconds

# ChirpStack issues the admin-login JWT with a 24 h lifetime.  Renew it a few
# minutes early so a request never travels with a token that expires
# mid-flight.
_TOKEN_REFRESH_MARGIN = 300  # seconds
# Fallback lifetime for a token whose "exp" claim cannot be read.
_TOKEN_FALLBACK_TTL = 3600  # seconds

# The MQTT ingest thread and the FastAPI handlers both fetch tokens, so the
# cache needs a lock.
_token_lock = threading.Lock()
_cached_token: str | None = None
_cached_token_expiry: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_placeholder(value: str) -> bool:
    return not value or value.startswith("change-me")


def _grpc_meta(token: str) -> list:
    return [("authorization", f"Bearer {token}")]


def uses_api_key() -> bool:
    """True when a real (non-placeholder) API key is configured.

    An API key never expires; the admin-login JWT does.  Both paths work — this
    only tells them apart for logging.
    """
    return bool(config.CHIRPSTACK_API_KEY) and not _is_placeholder(
        config.CHIRPSTACK_API_KEY
    )


def _jwt_expiry(token: str) -> float | None:
    """Return the "exp" claim of a JWT as a Unix timestamp, or None.

    Reads the payload without verifying the signature — we only need to know
    when to ask for a new token, and ChirpStack verifies it for real on every
    call anyway.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None
    exp = claims.get("exp")
    try:
        return float(exp)
    except (TypeError, ValueError):
        return None


def _renew_token_on_auth_error(fn):
    """Retry a call once with a fresh token when ChirpStack rejects it.

    Proactive renewal in get_token() covers the predictable case.  This is the
    safety net for the one it cannot predict: the field host has no buffered
    RTC, so its clock can jump forward by hours once NTP kicks in and retire a
    token that looked fresh the moment it was issued.
    """

    @functools.wraps(fn)
    def wrapper(channel, token, *args, **kwargs):
        try:
            return fn(channel, token, *args, **kwargs)
        except grpc.RpcError as e:
            if e.code() != grpc.StatusCode.UNAUTHENTICATED:
                raise
            logger.warning(
                "ChirpStack rejected the token for %s (%s) — renewing and retrying once.",
                fn.__name__,
                e.details(),
            )
            return fn(channel, get_token(channel, force_refresh=True), *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Channel + auth
# ---------------------------------------------------------------------------


def get_channel() -> grpc.Channel:
    return grpc.insecure_channel(config.CHIRPSTACK_HOST)


def get_token(channel: grpc.Channel, force_refresh: bool = False) -> str:
    """Return a currently valid bearer token for gRPC calls.

    Uses CHIRPSTACK_API_KEY if set and not a placeholder — an API key does not
    expire, so it is handed back unchanged.  Otherwise logs in with admin
    credentials (same logic as smoke_test.py) and caches the JWT until shortly
    before it expires.

    The caching is what makes this safe to call on every request: ChirpStack
    issues the login JWT with a 24 h lifetime, and a token fetched once at
    start-up and never renewed silently disables every ChirpStack-backed
    feature exactly one day later — the cockpit keeps answering /healthz while
    device lists, SF switching and downlinks all fail.  See
    docs/developer/analysis/pi-field-diagnosis-2026-08-01.md, finding B-1.
    """
    global _cached_token, _cached_token_expiry

    api_key = config.CHIRPSTACK_API_KEY
    if api_key and not _is_placeholder(api_key):
        logger.debug("Using CHIRPSTACK_API_KEY for gRPC auth.")
        return api_key

    with _token_lock:
        now = time.time()
        if (
            not force_refresh
            and _cached_token
            and now < _cached_token_expiry - _TOKEN_REFRESH_MARGIN
        ):
            return _cached_token

        stub = internal_pb2_grpc.InternalServiceStub(channel)
        resp = stub.Login(
            internal_pb2.LoginRequest(
                email=config.CHIRPSTACK_ADMIN_USER,
                password=config.CHIRPSTACK_ADMIN_PASS,
            ),
            timeout=_GRPC_TIMEOUT,
        )
        _cached_token = resp.jwt
        expiry = _jwt_expiry(resp.jwt)
        _cached_token_expiry = (
            expiry if expiry is not None else time.time() + _TOKEN_FALLBACK_TTL
        )
        logger.info(
            "ChirpStack JWT obtained, valid for %.1f h.",
            (_cached_token_expiry - time.time()) / 3600,
        )
        return _cached_token


# ---------------------------------------------------------------------------
# Entity lookup
# ---------------------------------------------------------------------------


@_renew_token_on_auth_error
def find_tenant_id(channel: grpc.Channel, token: str) -> str:
    """Return the ID of the tenant named TENANT_NAME; raises ValueError if absent."""
    stub = tenant_pb2_grpc.TenantServiceStub(channel)
    resp = stub.List(
        tenant_pb2.ListTenantsRequest(limit=100),
        metadata=_grpc_meta(token),
        timeout=_GRPC_TIMEOUT,
    )
    for t in resp.result:
        if t.name == config.TENANT_NAME:
            return t.id
    raise ValueError(f"Tenant {config.TENANT_NAME!r} not found in ChirpStack")


@_renew_token_on_auth_error
def find_app_id(channel: grpc.Channel, token: str, tenant_id: str) -> str:
    """Return the ID of APP_NAME inside tenant_id; raises ValueError if absent."""
    stub = application_pb2_grpc.ApplicationServiceStub(channel)
    resp = stub.List(
        application_pb2.ListApplicationsRequest(limit=100, tenant_id=tenant_id),
        metadata=_grpc_meta(token),
        timeout=_GRPC_TIMEOUT,
    )
    for a in resp.result:
        if a.name == config.APP_NAME:
            return a.id
    raise ValueError(f"Application {config.APP_NAME!r} not found")


# ---------------------------------------------------------------------------
# Idempotent provisioning (find-or-create)
# ---------------------------------------------------------------------------


@_renew_token_on_auth_error
def find_or_create_tenant(
    channel: grpc.Channel, token: str
) -> tuple[str, bool]:
    """Return (tenant_id, created).  Creates TENANT_NAME if it does not exist."""
    stub = tenant_pb2_grpc.TenantServiceStub(channel)
    meta = _grpc_meta(token)
    resp = stub.List(
        tenant_pb2.ListTenantsRequest(limit=100),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    for t in resp.result:
        if t.name == config.TENANT_NAME:
            return t.id, False
    resp = stub.Create(
        tenant_pb2.CreateTenantRequest(
            tenant=tenant_pb2.Tenant(
                name=config.TENANT_NAME,
                description="Created by whz-lora cockpit",
                can_have_gateways=True,
            )
        ),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    return resp.id, True


@_renew_token_on_auth_error
def find_or_create_application(
    channel: grpc.Channel, token: str, tenant_id: str
) -> tuple[str, bool]:
    """Return (app_id, created).  Creates APP_NAME if it does not exist."""
    stub = application_pb2_grpc.ApplicationServiceStub(channel)
    meta = _grpc_meta(token)
    resp = stub.List(
        application_pb2.ListApplicationsRequest(limit=100, tenant_id=tenant_id),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    for a in resp.result:
        if a.name == config.APP_NAME:
            return a.id, False
    resp = stub.Create(
        application_pb2.CreateApplicationRequest(
            application=application_pb2.Application(
                name=config.APP_NAME,
                description="Created by whz-lora cockpit",
                tenant_id=tenant_id,
            )
        ),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    return resp.id, True


@_renew_token_on_auth_error
def find_or_create_profile(
    channel: grpc.Channel,
    token: str,
    tenant_id: str,
    name: str,
    adr_algorithm_id: str,
) -> tuple[str, bool]:
    """Return (profile_id, created).

    Creates a device profile with EU868 / MAC 1.0.3 / RP002-1.0.3 / Class A /
    OTAA / uplink_interval=300 s if a profile named *name* does not exist yet.
    The given *adr_algorithm_id* must be a plugin registered in ChirpStack
    (e.g. "default", "fixed_dr3", "fixed_dr0").
    """
    stub = device_profile_pb2_grpc.DeviceProfileServiceStub(channel)
    meta = _grpc_meta(token)
    resp = stub.List(
        device_profile_pb2.ListDeviceProfilesRequest(limit=100, tenant_id=tenant_id),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    for dp in resp.result:
        if dp.name == name:
            return dp.id, False
    resp = stub.Create(
        device_profile_pb2.CreateDeviceProfileRequest(
            device_profile=device_profile_pb2.DeviceProfile(
                name=name,
                description=f"Created by whz-lora cockpit (adr={adr_algorithm_id})",
                tenant_id=tenant_id,
                region=common_pb2.Region.EU868,
                mac_version=common_pb2.MacVersion.LORAWAN_1_0_3,
                reg_params_revision=common_pb2.RegParamsRevision.RP002_1_0_3,
                adr_algorithm_id=adr_algorithm_id,
                supports_otaa=True,
                uplink_interval=300,
            )
        ),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    return resp.id, True


@_renew_token_on_auth_error
def find_profile_id_by_name(
    channel: grpc.Channel, token: str, tenant_id: str, name: str
) -> str:
    """Return the ID of the device profile with the given name; raises ValueError if absent."""
    stub = device_profile_pb2_grpc.DeviceProfileServiceStub(channel)
    resp = stub.List(
        device_profile_pb2.ListDeviceProfilesRequest(limit=100, tenant_id=tenant_id),
        metadata=_grpc_meta(token),
        timeout=_GRPC_TIMEOUT,
    )
    for dp in resp.result:
        if dp.name == name:
            return dp.id
    raise ValueError(f"Device profile {name!r} not found")


def find_profile_id(channel: grpc.Channel, token: str, tenant_id: str) -> str:
    """Return the ID of PROFILE_NAME (default ADR profile). Backward-compat wrapper."""
    return find_profile_id_by_name(channel, token, tenant_id, config.PROFILE_NAME)


@_renew_token_on_auth_error
def set_device_profile(
    channel: grpc.Channel, token: str, dev_eui: str, profile_id: str
) -> None:
    """Switch a device to a different device profile (e.g. fixed-SF9/SF12).

    Reads the current Device, replaces device_profile_id, and calls Update
    so that all other fields (name, AppEUI, tags …) are preserved.
    """
    stub = device_pb2_grpc.DeviceServiceStub(channel)
    meta = _grpc_meta(token)
    get_resp = stub.Get(
        device_pb2.GetDeviceRequest(dev_eui=dev_eui),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    device = get_resp.device
    device.device_profile_id = profile_id
    stub.Update(
        device_pb2.UpdateDeviceRequest(device=device),
        metadata=meta,
        timeout=_GRPC_TIMEOUT,
    )
    logger.debug("Device %s switched to profile %s", dev_eui, profile_id)


# ---------------------------------------------------------------------------
# Device registration (OTAA)
# ---------------------------------------------------------------------------


@_renew_token_on_auth_error
def register_device(
    channel: grpc.Channel,
    token: str,
    app_id: str,
    profile_id: str,
    name: str,
    dev_eui: str,
    app_key: str,
    join_eui: str = "0000000000000000",
) -> str:
    """Find-or-create an OTAA device and set/update its AppKey.

    LoRaWAN 1.0.x convention (assumed by the WHZ-Feldtest-EU868 profile,
    which is MAC 1.0.x): the single AppKey is stored in DeviceKeys.nwk_key.
    ChirpStack v4 uses nwk_key for the 1.0.x root key and app_key for the
    optional 1.1.x application-layer root key — leave app_key unset here.
    Reference: scripts/register_device.py (same logic).

    Returns dev_eui on success.
    """
    stub = device_pb2_grpc.DeviceServiceStub(channel)
    meta = _grpc_meta(token)

    # Find or create device
    device_existed = False
    try:
        stub.Get(
            device_pb2.GetDeviceRequest(dev_eui=dev_eui),
            metadata=meta,
            timeout=_GRPC_TIMEOUT,
        )
        device_existed = True
        logger.debug("Device %s already exists.", dev_eui)
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.NOT_FOUND:
            raise

    if not device_existed:
        stub.Create(
            device_pb2.CreateDeviceRequest(
                device=device_pb2.Device(
                    dev_eui=dev_eui,
                    name=name,
                    application_id=app_id,
                    device_profile_id=profile_id,
                    join_eui=join_eui,
                )
            ),
            metadata=meta,
            timeout=_GRPC_TIMEOUT,
        )
        logger.info("Device created: %s (%s)", name, dev_eui)

    # Set/update OTAA keys — try CreateKeys first, fall back to UpdateKeys
    dk = device_pb2.DeviceKeys(dev_eui=dev_eui, nwk_key=app_key)
    try:
        stub.CreateKeys(
            device_pb2.CreateDeviceKeysRequest(device_keys=dk),
            metadata=meta,
            timeout=_GRPC_TIMEOUT,
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.ALREADY_EXISTS:
            stub.UpdateKeys(
                device_pb2.UpdateDeviceKeysRequest(device_keys=dk),
                metadata=meta,
                timeout=_GRPC_TIMEOUT,
            )
        else:
            raise

    return dev_eui


# ---------------------------------------------------------------------------
# Device listing
# ---------------------------------------------------------------------------


@_renew_token_on_auth_error
def list_devices(channel: grpc.Channel, token: str, app_id: str) -> list[dict]:
    """Return a list of dicts for all devices in the application."""
    stub = device_pb2_grpc.DeviceServiceStub(channel)
    resp = stub.List(
        device_pb2.ListDevicesRequest(limit=1000, application_id=app_id),
        metadata=_grpc_meta(token),
        timeout=_GRPC_TIMEOUT,
    )
    devices = []
    for d in resp.result:
        ts = d.last_seen_at
        last_seen = (
            ts.ToDatetime(tzinfo=datetime.timezone.utc).isoformat()
            if ts.seconds
            else None
        )
        devices.append(
            {
                "dev_eui": d.dev_eui,
                "name": d.name,
                "device_profile_name": d.device_profile_name,
                "last_seen_at": last_seen,
            }
        )
    return devices


@_renew_token_on_auth_error
def get_device_addr(channel: grpc.Channel, token: str, dev_eui: str) -> str | None:
    """Return the current DevAddr of an activated device, or None."""
    stub = device_pb2_grpc.DeviceServiceStub(channel)
    try:
        resp = stub.GetActivation(
            device_pb2.GetDeviceActivationRequest(dev_eui=dev_eui),
            metadata=_grpc_meta(token),
            timeout=_GRPC_TIMEOUT,
        )
        return resp.device_activation.dev_addr or None
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return None
        raise


# ---------------------------------------------------------------------------
# Downlink
# ---------------------------------------------------------------------------


@_renew_token_on_auth_error
def enqueue_downlink(
    channel: grpc.Channel,
    token: str,
    dev_eui: str,
    f_port: int,
    data_hex: str = "00",
) -> None:
    """Enqueue a confirmed downlink for a device (Phase 5 loopback)."""
    stub = device_pb2_grpc.DeviceServiceStub(channel)
    stub.Enqueue(
        device_pb2.EnqueueDeviceQueueItemRequest(
            queue_item=device_pb2.DeviceQueueItem(
                dev_eui=dev_eui,
                confirmed=True,
                f_port=f_port,
                data=bytes.fromhex(data_hex),
            )
        ),
        metadata=_grpc_meta(token),
        timeout=_GRPC_TIMEOUT,
    )
    logger.debug("Downlink enqueued: dev=%s fport=%d data=%s", dev_eui, f_port, data_hex)


@_renew_token_on_auth_error
def get_device_queue(channel: grpc.Channel, token: str, dev_eui: str) -> list[dict]:
    """Return a device's current downlink queue as
    [{"f_port": int, "data_hex": str}, ...] — used by the config-status
    endpoint (F-0006 "Trust & Sichtbarkeit") to show whether a queued config
    downlink has already left the network, or is still waiting for the
    device's next Class A receive window.
    """
    stub = device_pb2_grpc.DeviceServiceStub(channel)
    resp = stub.GetQueue(
        device_pb2.GetDeviceQueueItemsRequest(dev_eui=dev_eui),
        metadata=_grpc_meta(token),
        timeout=_GRPC_TIMEOUT,
    )
    return [{"f_port": item.f_port, "data_hex": item.data.hex()} for item in resp.result]
