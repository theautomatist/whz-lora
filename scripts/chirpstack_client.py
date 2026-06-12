"""
chirpstack_client.py — shared gRPC core for whz-lora.

Provides reusable helpers for connecting to the ChirpStack v4 gRPC API,
authenticating, and idempotent find-or-create operations for tenants,
applications, and device profiles.

Imported by smoke_test.py and provisioning/provisioning.py.

Region, MAC version and RP002 revision below are intentional and
load-bearing for this single-region base: EU868 / LoRaWAN 1.0.3 / RP002-1.0.3.
"""

import os

import grpc

from chirpstack_api.api import tenant_pb2, tenant_pb2_grpc
from chirpstack_api.api import application_pb2, application_pb2_grpc
from chirpstack_api.api import device_profile_pb2, device_profile_pb2_grpc
from chirpstack_api.api import device_pb2, device_pb2_grpc
from chirpstack_api.api import internal_pb2, internal_pb2_grpc
from chirpstack_api.common import common_pb2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_placeholder(value: str) -> bool:
    return not value or value.startswith("change-me")


def set_device_keys_idempotent(dev_stub, meta: list, dev_eui: str, app_key: str) -> str:
    """
    Create or update a device's OTAA root keys, idempotently.

    LoRaWAN 1.0.x mapping: the vendor AppKey goes into nwk_key; the app_key
    field is 32 hex zeros. ChirpStack reports an existing-keys collision as
    INTERNAL (a PostgreSQL duplicate-key violation), NOT ALREADY_EXISTS, so we
    probe with GetKeys first instead of relying on CreateKeys' status code.

    Returns: "created" | "updated" | "exists".
    """
    keys = device_pb2.DeviceKeys(dev_eui=dev_eui, nwk_key=app_key, app_key="0" * 32)
    try:
        resp = dev_stub.GetKeys(
            device_pb2.GetDeviceKeysRequest(dev_eui=dev_eui), metadata=meta
        )
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.NOT_FOUND:
            raise
        dev_stub.CreateKeys(
            device_pb2.CreateDeviceKeysRequest(device_keys=keys), metadata=meta
        )
        return "created"

    if resp.device_keys.nwk_key == app_key:
        return "exists"
    dev_stub.UpdateKeys(
        device_pb2.UpdateDeviceKeysRequest(device_keys=keys), metadata=meta
    )
    return "updated"


def _paginate(list_fn, request_cls, extra_kwargs: dict, meta: list) -> list:
    """
    Generic paginator: collect all results by incrementing offset until
    total_count is reached.

    *list_fn*    — a stub method (e.g. stub.List)
    *request_cls* — the request protobuf class
    *extra_kwargs* — keyword args for the request (e.g. tenant_id, limit)
    *meta*        — gRPC metadata list

    Returns the concatenated result list.
    """
    PAGE = 100
    offset = 0
    collected = []
    while True:
        req = request_cls(limit=PAGE, offset=offset, **extra_kwargs)
        resp = list_fn(req, metadata=meta)
        collected.extend(resp.result)
        if len(collected) >= resp.total_count:
            break
        offset += PAGE
    return collected


# ---------------------------------------------------------------------------
# Channel
# ---------------------------------------------------------------------------


def open_channel(host: str) -> grpc.Channel:
    """
    Open an insecure gRPC channel to *host* and wait until it is ready.

    Raises grpc.FutureTimeoutError if the channel is not ready within 15 s.
    """
    channel = grpc.insecure_channel(host)
    grpc.channel_ready_future(channel).result(timeout=15)
    return channel


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def get_auth_token(channel: grpc.Channel) -> str:
    """
    Return a valid bearer token for ChirpStack gRPC calls.

    If CHIRPSTACK_API_KEY is set and is not a placeholder, return it directly.
    Otherwise log in with CHIRPSTACK_ADMIN_USER / CHIRPSTACK_ADMIN_PASS and
    return the resulting JWT.
    """
    api_key = os.environ.get("CHIRPSTACK_API_KEY", "")
    if api_key and not _is_placeholder(api_key):
        return api_key

    admin_user = os.environ.get("CHIRPSTACK_ADMIN_USER", "admin")
    admin_pass = os.environ.get("CHIRPSTACK_ADMIN_PASS", "admin")

    stub = internal_pb2_grpc.InternalServiceStub(channel)
    resp = stub.Login(
        internal_pb2.LoginRequest(email=admin_user, password=admin_pass)
    )
    return resp.jwt


def grpc_metadata(token: str) -> list:
    return [("authorization", f"Bearer {token}")]


# ---------------------------------------------------------------------------
# Find-or-create operations
# ---------------------------------------------------------------------------


def find_or_create_tenant(stub, meta: list, name: str) -> str:
    """
    Return the ID of the tenant with *name*, creating it if absent.

    Paginates the full tenant list so that a tenant beyond the first page
    is found rather than duplicated.

    *stub* must be a TenantServiceStub.
    """
    all_tenants = _paginate(
        stub.List, tenant_pb2.ListTenantsRequest, {}, meta
    )
    for t in all_tenants:
        if t.name == name:
            return t.id

    resp = stub.Create(
        tenant_pb2.CreateTenantRequest(
            tenant=tenant_pb2.Tenant(
                name=name,
                description="Created by chirpstack_client",
                can_have_gateways=True,
            )
        ),
        metadata=meta,
    )
    return resp.id


def find_or_create_application(
    stub, meta: list, tenant_id: str, name: str
) -> str:
    """
    Return the ID of the application with *name* inside *tenant_id*, creating
    it if absent.

    Paginates so that an application beyond the first page is found rather
    than duplicated.

    *stub* must be an ApplicationServiceStub.
    """
    all_apps = _paginate(
        stub.List,
        application_pb2.ListApplicationsRequest,
        {"tenant_id": tenant_id},
        meta,
    )
    for a in all_apps:
        if a.name == name:
            return a.id

    resp = stub.Create(
        application_pb2.CreateApplicationRequest(
            application=application_pb2.Application(
                name=name,
                description="Created by chirpstack_client",
                tenant_id=tenant_id,
            )
        ),
        metadata=meta,
    )
    return resp.id


def find_or_create_device_profile(
    stub,
    meta: list,
    tenant_id: str,
    name: str,
    *,
    supports_otaa: bool,
    supports_class_c: bool = False,
    class_c_timeout: int = 0,
) -> str:
    """
    Return the ID of the device profile with *name* inside *tenant_id*,
    creating it if absent.

    Region EU868, LoRaWAN 1.0.3 / RP002-1.0.3, default ADR, JS passthrough
    codec.  OTAA / Class-C support is configurable via keyword arguments.

    Paginates so that a profile beyond the first page is found rather than
    duplicated.

    *stub* must be a DeviceProfileServiceStub.
    """
    all_profiles = _paginate(
        stub.List,
        device_profile_pb2.ListDeviceProfilesRequest,
        {"tenant_id": tenant_id},
        meta,
    )
    for dp in all_profiles:
        if dp.name == name:
            return dp.id

    resp = stub.Create(
        device_profile_pb2.CreateDeviceProfileRequest(
            device_profile=device_profile_pb2.DeviceProfile(
                name=name,
                description="Created by chirpstack_client",
                tenant_id=tenant_id,
                region=common_pb2.Region.EU868,
                mac_version=common_pb2.MacVersion.LORAWAN_1_0_3,
                reg_params_revision=common_pb2.RegParamsRevision.RP002_1_0_3,
                adr_algorithm_id="default",
                payload_codec_runtime=device_profile_pb2.CodecRuntime.JS,
                payload_codec_script=(
                    "function decodeUplink(input) {\n"
                    "  var hex = Array.from(input.bytes)"
                    ".map(function(b){return b.toString(16).padStart(2,'0')}).join('');\n"
                    "  return { data: { raw: hex } };\n"
                    "}\n"
                    "function encodeDownlink(input) { return { bytes: [] }; }\n"
                ),
                supports_otaa=supports_otaa,
                supports_class_c=supports_class_c,
                class_c_timeout=class_c_timeout,
            )
        ),
        metadata=meta,
    )
    return resp.id
