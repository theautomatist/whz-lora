"""chirpstack.py — gRPC wrapper for ChirpStack v4 API.

Handles authentication, device registration (OTAA), device listing,
DevAddr lookup, and confirmed-downlink enqueueing.

Follows the same patterns as scripts/smoke_test.py: API-key auth with
fallback to admin/admin JWT login; find-or-create semantics for devices.
Reference: scripts/register_device.py (same OTAA key-storage convention).
"""
import datetime
import logging

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_placeholder(value: str) -> bool:
    return not value or value.startswith("change-me")


def _grpc_meta(token: str) -> list:
    return [("authorization", f"Bearer {token}")]


# ---------------------------------------------------------------------------
# Channel + auth
# ---------------------------------------------------------------------------


def get_channel() -> grpc.Channel:
    return grpc.insecure_channel(config.CHIRPSTACK_HOST)


def get_token(channel: grpc.Channel) -> str:
    """Return a bearer token for gRPC calls.

    Uses CHIRPSTACK_API_KEY if set and not a placeholder; otherwise logs in
    with admin credentials (same logic as smoke_test.py).
    """
    api_key = config.CHIRPSTACK_API_KEY
    if api_key and not _is_placeholder(api_key):
        logger.debug("Using CHIRPSTACK_API_KEY for gRPC auth.")
        return api_key

    stub = internal_pb2_grpc.InternalServiceStub(channel)
    resp = stub.Login(
        internal_pb2.LoginRequest(
            email=config.CHIRPSTACK_ADMIN_USER,
            password=config.CHIRPSTACK_ADMIN_PASS,
        ),
        timeout=_GRPC_TIMEOUT,
    )
    logger.debug("JWT login successful.")
    return resp.jwt


# ---------------------------------------------------------------------------
# Entity lookup
# ---------------------------------------------------------------------------


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
