"""
provisioning.py — device provisioning and status operations for whz-lora.

Uses the shared gRPC core (chirpstack_client) and chirpstack-api stubs to
provision OTAA devices and read their status from ChirpStack v4.
"""

import os
import sys
import datetime
import logging
import threading

import grpc

from chirpstack_api.api import device_pb2, device_pb2_grpc
from chirpstack_api.api import tenant_pb2_grpc
from chirpstack_api.api import application_pb2_grpc
from chirpstack_api.api import device_profile_pb2_grpc

# Resolve chirpstack_client from scripts/ directory.
# In Docker (PYTHONPATH=/app, chirpstack_client.py at /app/):
#   importable directly — no path manipulation needed.
# In development (running from repo root with provisioning/ as cwd):
#   scripts/ is one level up; add it if it exists.
_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from chirpstack_client import (
    open_channel,
    get_auth_token,
    grpc_metadata,
    find_or_create_tenant,
    find_or_create_application,
    find_or_create_device_profile,
    set_device_keys_idempotent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read once at module level with defaults)
# ---------------------------------------------------------------------------

CHIRPSTACK_HOST = os.environ.get("CHIRPSTACK_HOST", "chirpstack:8080")
CHIRPSTACK_API_KEY = os.environ.get("CHIRPSTACK_API_KEY", "")
CHIRPSTACK_ADMIN_USER = os.environ.get("CHIRPSTACK_ADMIN_USER", "admin")
CHIRPSTACK_ADMIN_PASS = os.environ.get("CHIRPSTACK_ADMIN_PASS", "admin")
PROVISIONING_TENANT = os.environ.get("PROVISIONING_TENANT", "ChirpStack")
PROVISIONING_APPLICATION = os.environ.get("PROVISIONING_APPLICATION", "WHZ-Stellantriebe")
PROVISIONING_PROFILE = os.environ.get("PROVISIONING_PROFILE", "WHZ-Stellantrieb-ClassA-OTAA")

# ---------------------------------------------------------------------------
# Per-process cache for resolved IDs and auth token
# Thread-safety: all reads, writes and clear-then-retry of the cache are
# guarded by _cache_lock so that concurrent uvicorn threadpool handlers
# cannot race on the shared mutable state.
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict = {
    "channel": None,
    "token": None,
    "tenant_id": None,
    "app_id": None,
    "profile_id": None,
}


def _get_channel() -> grpc.Channel:
    # Called under _cache_lock.
    if _cache["channel"] is None:
        _cache["channel"] = open_channel(CHIRPSTACK_HOST)
    return _cache["channel"]


def _refresh_token(channel: grpc.Channel) -> str:
    # Called under _cache_lock.
    token = get_auth_token(channel)
    _cache["token"] = token
    return token


def _get_meta() -> tuple:
    """Return (channel, metadata). Opens channel lazily; refreshes token if unset."""
    with _cache_lock:
        channel = _get_channel()
        if _cache["token"] is None:
            _refresh_token(channel)
        return channel, grpc_metadata(_cache["token"])


def _resolve_ids(channel: grpc.Channel, meta: list) -> tuple:
    """Return (tenant_id, app_id, profile_id), resolving once and caching."""
    with _cache_lock:
        if _cache["tenant_id"] is None:
            _cache["tenant_id"] = find_or_create_tenant(
                tenant_pb2_grpc.TenantServiceStub(channel), meta, PROVISIONING_TENANT
            )
        if _cache["app_id"] is None:
            _cache["app_id"] = find_or_create_application(
                application_pb2_grpc.ApplicationServiceStub(channel),
                meta,
                _cache["tenant_id"],
                PROVISIONING_APPLICATION,
            )
        if _cache["profile_id"] is None:
            _cache["profile_id"] = find_or_create_device_profile(
                device_profile_pb2_grpc.DeviceProfileServiceStub(channel),
                meta,
                _cache["tenant_id"],
                PROVISIONING_PROFILE,
                supports_otaa=True,
                supports_class_c=False,
            )
        return _cache["tenant_id"], _cache["app_id"], _cache["profile_id"]


def _call_with_auth_retry(fn):
    """
    Call fn(channel, meta) once.  On UNAUTHENTICATED, refresh the token and
    retry exactly once.  Re-raises any other gRPC error.
    """
    channel, meta = _get_meta()
    try:
        return fn(channel, meta)
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.UNAUTHENTICATED:
            raise
        logger.info("Token expired — refreshing.")
        with _cache_lock:
            _refresh_token(channel)
            # Also clear cached IDs; re-resolve after re-auth.
            _cache["tenant_id"] = None
            _cache["app_id"] = None
            _cache["profile_id"] = None
        channel2, meta2 = _get_meta()
        return fn(channel2, meta2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def provision_device(
    dev_eui: str,
    name: str,
    join_eui: str,
    app_key: str,
) -> str:
    """
    Idempotently provision an OTAA device in ChirpStack.

    LoRaWAN 1.0.x key mapping:
      - vendor AppKey → nwk_key
      - app_key field → 32 hex zeros

    Returns one of: "created" | "keys-updated" | "exists"
    Raises grpc.RpcError on unrecoverable errors.
    """
    def _do(channel, meta):
        _, app_id, profile_id = _resolve_ids(channel, meta)
        dev_stub = device_pb2_grpc.DeviceServiceStub(channel)

        # 1. Find or create device.
        status = "exists"
        try:
            dev_stub.Get(
                device_pb2.GetDeviceRequest(dev_eui=dev_eui), metadata=meta
            )
        except grpc.RpcError as e:
            if e.code() not in (grpc.StatusCode.NOT_FOUND,):
                raise
            try:
                dev_stub.Create(
                    device_pb2.CreateDeviceRequest(
                        device=device_pb2.Device(
                            dev_eui=dev_eui,
                            name=name,
                            description="Provisioned via whz-lora provisioning app",
                            application_id=app_id,
                            device_profile_id=profile_id,
                            join_eui=join_eui or "0000000000000000",
                            is_disabled=False,
                        )
                    ),
                    metadata=meta,
                )
                status = "created"
            except grpc.RpcError as ce:
                if ce.code() != grpc.StatusCode.ALREADY_EXISTS:
                    raise
                status = "exists"

        # 2. Set OTAA keys idempotently. ChirpStack reports an existing-keys
        #    collision as INTERNAL (a PostgreSQL duplicate-key violation), not
        #    ALREADY_EXISTS, so the shared helper probes with GetKeys first.
        key_status = set_device_keys_idempotent(dev_stub, meta, dev_eui, app_key)

        if status == "created":
            return "created"
        return "exists" if key_status == "exists" else "keys-updated"

    return _call_with_auth_retry(_do)


def list_device_states() -> list:
    """
    Return a list of device state dicts for the provisioning application.

    Each dict has:
      name, dev_eui, state ("online" | "joined" | "provisioned"),
      last_seen (datetime or None), rssi (float or None), snr (float or None)

    Paginates the full device list to avoid truncation at a fixed limit.
    """
    def _do(channel, meta):
        _, app_id, _ = _resolve_ids(channel, meta)
        dev_stub = device_pb2_grpc.DeviceServiceStub(channel)

        PAGE = 100
        offset = 0
        all_items = []
        while True:
            resp = dev_stub.List(
                device_pb2.ListDevicesRequest(
                    application_id=app_id, limit=PAGE, offset=offset
                ),
                metadata=meta,
            )
            all_items.extend(resp.result)
            if len(all_items) >= resp.total_count:
                break
            offset += PAGE

        results = []
        for item in all_items:
            state_info = _device_state(dev_stub, meta, item)
            results.append(state_info)

        return results

    return _call_with_auth_retry(_do)


def _device_state(dev_stub, meta: list, item) -> dict:
    """Determine state and best-effort RSSI/SNR for one DeviceListItem."""
    dev_eui = item.dev_eui
    last_seen = None
    rssi = None
    snr = None

    # last_seen_at is a google.protobuf.Timestamp; HasField works on message fields.
    if item.HasField("last_seen_at"):
        ts = item.last_seen_at
        last_seen = datetime.datetime.fromtimestamp(
            ts.seconds + ts.nanos / 1e9, tz=datetime.timezone.utc
        )
        state = "online"
    else:
        # Check whether the device has ever joined (has a DevAddr from OTAA).
        try:
            act_resp = dev_stub.GetActivation(
                device_pb2.GetDeviceActivationRequest(dev_eui=dev_eui),
                metadata=meta,
            )
            if act_resp.device_activation.dev_addr:
                state = "joined"
            else:
                state = "provisioned"
        except grpc.RpcError:
            state = "provisioned"

    # Best-effort RSSI/SNR via link metrics (last hour).
    if state == "online":
        try:
            rssi, snr = _get_link_metrics(dev_stub, meta, dev_eui)
        except Exception:
            pass

    return {
        "name": item.name,
        "dev_eui": dev_eui,
        "state": state,
        "last_seen": last_seen,
        "rssi": rssi,
        "snr": snr,
    }


def _get_link_metrics(dev_stub, meta: list, dev_eui: str):
    """
    Fetch last-hour link metrics and return (rssi, snr) or (None, None).

    Uses HOUR aggregation for a 1-hour window ending now.
    """
    from chirpstack_api.api import device_pb2 as _d
    from chirpstack_api.common import common_pb2 as _c
    from google.protobuf import timestamp_pb2

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    start = now - datetime.timedelta(hours=1)

    def _ts(dt):
        pb = timestamp_pb2.Timestamp()
        pb.FromDatetime(dt)
        return pb

    resp = dev_stub.GetLinkMetrics(
        _d.GetDeviceLinkMetricsRequest(
            dev_eui=dev_eui,
            start=_ts(start),
            end=_ts(now),
            aggregation=_c.Aggregation.HOUR,
        ),
        metadata=meta,
    )

    # gw_rssi and gw_snr are Metric messages with datasets and timestamps.
    rssi_val = _last_metric_value(resp.gw_rssi)
    snr_val = _last_metric_value(resp.gw_snr)
    return rssi_val, snr_val


def _last_metric_value(metric):
    """Return the last non-zero float from a Metric's first dataset, or None."""
    if not metric.datasets:
        return None
    dataset = metric.datasets[0]
    # data is a list of floats; scan from the end for the first non-zero value.
    for v in reversed(list(dataset.data)):
        if v != 0.0:
            return float(v)
    return None


def delete_device(dev_eui: str) -> None:
    """
    Delete a device by DevEUI.

    Raises grpc.RpcError on failure (NOT_FOUND included — caller handles).
    """
    def _do(channel, meta):
        dev_stub = device_pb2_grpc.DeviceServiceStub(channel)
        dev_stub.Delete(
            device_pb2.DeleteDeviceRequest(dev_eui=dev_eui), metadata=meta
        )

    _call_with_auth_retry(_do)
