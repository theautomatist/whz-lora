#!/usr/bin/env python3
"""
smoke_test.py — whz-lora verification check.

Performs an end-to-end smoke test against a running ChirpStack v4 stack:

1. Authenticates to ChirpStack gRPC API on localhost:8080.
   - If CHIRPSTACK_API_KEY is set and non-placeholder, uses it directly.
   - Otherwise, logs in with CHIRPSTACK_ADMIN_USER / CHIRPSTACK_ADMIN_PASS
     and creates a temporary API key.
2. Creates (idempotent find-or-create) a Tenant, Application,
   Device Profile, and Device.
3. Sends a Semtech UDP Packet Forwarder PUSH_DATA frame (stats + RXPK)
   to localhost:1700 to simulate a gateway uplink.
4. Subscribes to the MQTT uplink topic and waits up to 30 seconds for
   the event.
5. Verifies that anonymous MQTT connections are rejected.
6. Exits 0 on success, non-zero with a clear error message on failure.

Required environment variables (set via .env or CI secrets):
  CHIRPSTACK_ADMIN_USER   — ChirpStack admin username (default: admin)
  CHIRPSTACK_ADMIN_PASS   — ChirpStack admin password (default: admin)
  MQTT_TEST_USERNAME      — MQTT username for test subscriber
  MQTT_TEST_PASSWORD      — MQTT password for test subscriber

Optional:
  CHIRPSTACK_API_KEY      — Pre-created API key (skips login if provided)
"""

import base64
import json
import os
import socket
import struct
import sys
import threading
import time
import random

import grpc
import paho.mqtt.client as mqtt

# gRPC stubs from chirpstack-api package
from chirpstack_api.api import tenant_pb2, tenant_pb2_grpc
from chirpstack_api.api import application_pb2, application_pb2_grpc
from chirpstack_api.api import device_profile_pb2, device_profile_pb2_grpc
from chirpstack_api.api import device_pb2, device_pb2_grpc
from chirpstack_api.api import internal_pb2, internal_pb2_grpc
from chirpstack_api.common import common_pb2

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHIRPSTACK_HOST = os.environ.get("CHIRPSTACK_HOST", "localhost:8080")
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
UDP_HOST = os.environ.get("UDP_HOST", "localhost")
UDP_PORT = int(os.environ.get("UDP_PORT", "1700"))
UPLINK_TIMEOUT_SECONDS = 30

# Test entity identifiers — stable across runs for idempotency.
TENANT_NAME = "whz-smoke-test-tenant"
APP_NAME = "whz-smoke-test-app"
DEVICE_PROFILE_NAME = "whz-smoke-test-profile"
DEVICE_EUI = "0102030405060708"
DEVICE_NAME = "whz-smoke-test-device"
GATEWAY_EUI = "aabbccddee010203"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def die(message: str, code: int = 1) -> None:
    print(f"[smoke_test] ERROR: {message}", file=sys.stderr)
    sys.exit(code)


def grpc_metadata(token: str) -> list:
    return [("authorization", f"Bearer {token}")]


def _is_placeholder(value: str) -> bool:
    return not value or value.startswith("change-me")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def get_auth_token(channel: grpc.Channel) -> str:
    """
    Return a valid bearer token for ChirpStack gRPC calls.

    If CHIRPSTACK_API_KEY is set and is not a placeholder, use it directly.
    Otherwise login with admin credentials to obtain a JWT.
    """
    api_key = os.environ.get("CHIRPSTACK_API_KEY", "")
    if api_key and not _is_placeholder(api_key):
        print("[smoke_test] Using CHIRPSTACK_API_KEY from environment.")
        return api_key

    admin_user = os.environ.get("CHIRPSTACK_ADMIN_USER", "admin")
    admin_pass = os.environ.get("CHIRPSTACK_ADMIN_PASS", "admin")

    print(
        f"[smoke_test] CHIRPSTACK_API_KEY not set or placeholder — "
        f"logging in as {admin_user!r} to obtain JWT."
    )
    stub = internal_pb2_grpc.InternalServiceStub(channel)
    try:
        resp = stub.Login(
            internal_pb2.LoginRequest(email=admin_user, password=admin_pass)
        )
        print("[smoke_test] Login successful, JWT obtained.")
        return resp.jwt
    except grpc.RpcError as e:
        die(
            f"Login failed ({e.code()}): {e.details()}. "
            "Set CHIRPSTACK_ADMIN_USER / CHIRPSTACK_ADMIN_PASS correctly."
        )


# ---------------------------------------------------------------------------
# gRPC provisioning — find-or-create
# ---------------------------------------------------------------------------


def find_or_create_tenant(stub, meta: list) -> str:
    req = tenant_pb2.ListTenantsRequest(limit=100)
    resp = stub.List(req, metadata=meta)
    for t in resp.result:
        if t.name == TENANT_NAME:
            print(f"[smoke_test] Tenant already exists: {t.id}")
            return t.id

    resp = stub.Create(
        tenant_pb2.CreateTenantRequest(
            tenant=tenant_pb2.Tenant(
                name=TENANT_NAME,
                description="Created by smoke_test.py",
                can_have_gateways=True,
            )
        ),
        metadata=meta,
    )
    print(f"[smoke_test] Tenant created: {resp.id}")
    return resp.id


def find_or_create_application(stub, meta: list, tenant_id: str) -> str:
    req = application_pb2.ListApplicationsRequest(limit=100, tenant_id=tenant_id)
    resp = stub.List(req, metadata=meta)
    for a in resp.result:
        if a.name == APP_NAME:
            print(f"[smoke_test] Application already exists: {a.id}")
            return a.id

    resp = stub.Create(
        application_pb2.CreateApplicationRequest(
            application=application_pb2.Application(
                name=APP_NAME,
                description="Created by smoke_test.py",
                tenant_id=tenant_id,
            )
        ),
        metadata=meta,
    )
    print(f"[smoke_test] Application created: {resp.id}")
    return resp.id


def find_or_create_device_profile(stub, meta: list, tenant_id: str) -> str:
    req = device_profile_pb2.ListDeviceProfilesRequest(
        limit=100, tenant_id=tenant_id
    )
    resp = stub.List(req, metadata=meta)
    for dp in resp.result:
        if dp.name == DEVICE_PROFILE_NAME:
            print(f"[smoke_test] Device profile already exists: {dp.id}")
            return dp.id

    resp = stub.Create(
        device_profile_pb2.CreateDeviceProfileRequest(
            device_profile=device_profile_pb2.DeviceProfile(
                name=DEVICE_PROFILE_NAME,
                description="Created by smoke_test.py",
                tenant_id=tenant_id,
                region=common_pb2.Region.EU868,
                mac_version=common_pb2.MacVersion.LORAWAN_1_0_3,
                reg_params_revision=common_pb2.RegParamsRevision.RP002_1_0_3,
                adr_algorithm_id="default",
                payload_codec_runtime=device_profile_pb2.CodecRuntime.JS,
                uplink_codec_script=(
                    "function decodeUplink(input) {\n"
                    "  var hex = Array.from(input.bytes)"
                    ".map(function(b){return b.toString(16).padStart(2,'0')}).join('');\n"
                    "  return { data: { raw: hex } };\n"
                    "}\n"
                    "function encodeDownlink(input) { return { bytes: [] }; }\n"
                ),
                supports_otaa=True,
            )
        ),
        metadata=meta,
    )
    print(f"[smoke_test] Device profile created: {resp.id}")
    return resp.id


def find_or_create_device(
    stub, meta: list, app_id: str, profile_id: str
) -> None:
    try:
        existing = stub.Get(
            device_pb2.GetDeviceRequest(dev_eui=DEVICE_EUI), metadata=meta
        )
        print(f"[smoke_test] Device already exists: {existing.device.dev_eui}")
        return
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.NOT_FOUND:
            raise

    stub.Create(
        device_pb2.CreateDeviceRequest(
            device=device_pb2.Device(
                dev_eui=DEVICE_EUI,
                name=DEVICE_NAME,
                description="Created by smoke_test.py",
                application_id=app_id,
                device_profile_id=profile_id,
                is_disabled=False,
            )
        ),
        metadata=meta,
    )
    print(f"[smoke_test] Device created: {DEVICE_EUI}")

    stub.CreateKeys(
        device_pb2.CreateDeviceKeysRequest(
            device_keys=device_pb2.DeviceKeys(
                dev_eui=DEVICE_EUI,
                nwk_key="00000000000000000000000000000001",
                app_key="00000000000000000000000000000001",
            )
        ),
        metadata=meta,
    )
    print(f"[smoke_test] Device keys set for: {DEVICE_EUI}")


# ---------------------------------------------------------------------------
# UDP Packet Forwarder
# ---------------------------------------------------------------------------


def build_push_data(token: int, payload: dict) -> bytes:
    """
    Build a Semtech UDP Packet Forwarder PUSH_DATA packet (protocol v2).

    Layout:
      1 byte  protocol version = 2
      2 bytes token (big-endian)
      1 byte  identifier = 0x00 (PUSH_DATA)
      8 bytes gateway MAC (little-endian)
      N bytes JSON payload
    """
    header = struct.pack("!BHB", 2, token, 0x00)
    gw_mac_le = bytes.fromhex(GATEWAY_EUI)[::-1]
    return header + gw_mac_le + json.dumps(payload).encode("utf-8")


def send_stats_frame(sock: socket.socket) -> None:
    token = random.randint(0, 0xFFFF)
    payload = {
        "stat": {
            "time": time.strftime("%Y-%m-%d %H:%M:%S GMT", time.gmtime()),
            "rxnb": 0,
            "rxok": 0,
            "rxfw": 0,
            "ackr": 100.0,
            "dwnb": 0,
            "txnb": 0,
        }
    }
    sock.sendto(build_push_data(token, payload), (UDP_HOST, UDP_PORT))
    print(f"[smoke_test] Sent stats PUSH_DATA (token={token:#06x})")


def send_uplink_frame(sock: socket.socket) -> None:
    """
    Send a Join Request frame so ChirpStack emits an event on MQTT.

    ChirpStack publishes a join/up event even when the MIC check fails,
    which lets the smoke test confirm the full pipeline without a real
    over-the-air join.
    """
    token = random.randint(0, 0xFFFF)
    mhdr = 0x00  # JoinRequest
    join_eui = bytes(8)  # all zeros
    dev_eui_le = bytes.fromhex(DEVICE_EUI)[::-1]
    dev_nonce = struct.pack("<H", random.randint(1, 0xFFFF))
    mic = bytes(4)
    phy = bytes([mhdr]) + join_eui + dev_eui_le + dev_nonce + mic

    payload = {
        "rxpk": [
            {
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "tmst": int(time.time() * 1_000_000) & 0xFFFF_FFFF,
                "chan": 0,
                "rfch": 0,
                "freq": 868.1,
                "stat": 1,
                "modu": "LORA",
                "datr": "SF7BW125",
                "codr": "4/5",
                "rssi": -60,
                "lsnr": 9.0,
                "size": len(phy),
                "data": base64.b64encode(phy).decode("ascii"),
            }
        ]
    }
    sock.sendto(build_push_data(token, payload), (UDP_HOST, UDP_PORT))
    print(f"[smoke_test] Sent uplink PUSH_DATA (token={token:#06x})")


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------


def wait_for_uplink(app_id: str, username: str, password: str) -> bool:
    """
    Subscribe to application events and wait up to UPLINK_TIMEOUT_SECONDS.
    Returns True if any event is received.
    """
    topic = f"application/{app_id}/device/{DEVICE_EUI}/event/+"
    received = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[smoke_test] MQTT connected — subscribing to {topic}")
            client.subscribe(topic)
        else:
            print(
                f"[smoke_test] MQTT connect rejected (rc={reason_code})",
                file=sys.stderr,
            )

    def on_message(client, userdata, msg):
        print(f"[smoke_test] MQTT event on {msg.topic}: {msg.payload[:120]!r}")
        received.set()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="whz-smoke-sub",
        clean_session=True,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.username_pw_set(username, password)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    except OSError as e:
        die(f"Cannot connect to Mosquitto at {MQTT_HOST}:{MQTT_PORT}: {e}")

    client.loop_start()
    result = received.wait(timeout=UPLINK_TIMEOUT_SECONDS)
    client.loop_stop()
    client.disconnect()
    return result


def verify_anonymous_rejected() -> None:
    """Assert that anonymous MQTT connections are refused."""
    rc_holder = [None]

    def on_connect(client, userdata, flags, reason_code, properties):
        rc_holder[0] = reason_code

    anon = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="whz-smoke-anon",
        clean_session=True,
    )
    anon.on_connect = on_connect

    try:
        anon.connect(MQTT_HOST, MQTT_PORT, keepalive=5)
        anon.loop_start()
        time.sleep(2)
        anon.loop_stop()
        anon.disconnect()
    except OSError:
        print("[smoke_test] Anonymous MQTT: connection refused at TCP level — OK")
        return

    rc = rc_holder[0]
    if rc == 0:
        die(
            "Anonymous MQTT connection was accepted (rc=0). "
            "Mosquitto must have allow_anonymous false."
        )
    print(f"[smoke_test] Anonymous MQTT correctly rejected (rc={rc})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    test_user = os.environ.get("MQTT_TEST_USERNAME", "testsubscriber")
    test_pass = os.environ.get("MQTT_TEST_PASSWORD", "testsubscriber")

    # ------------------------------------------------------------------
    # Step 1 — Connect to gRPC and obtain auth token
    # ------------------------------------------------------------------
    print(f"[smoke_test] Connecting to ChirpStack at {CHIRPSTACK_HOST} ...")
    try:
        channel = grpc.insecure_channel(CHIRPSTACK_HOST)
        grpc.channel_ready_future(channel).result(timeout=15)
    except grpc.FutureTimeoutError:
        die(
            f"Cannot reach ChirpStack gRPC API at {CHIRPSTACK_HOST} "
            "(timeout 15 s). Is the stack running?"
        )

    print("[smoke_test] gRPC channel ready.")
    token = get_auth_token(channel)
    meta = grpc_metadata(token)

    # ------------------------------------------------------------------
    # Step 2 — Provision tenant / application / device profile / device
    # ------------------------------------------------------------------
    try:
        tenant_id = find_or_create_tenant(
            tenant_pb2_grpc.TenantServiceStub(channel), meta
        )
        app_id = find_or_create_application(
            application_pb2_grpc.ApplicationServiceStub(channel), meta, tenant_id
        )
        profile_id = find_or_create_device_profile(
            device_profile_pb2_grpc.DeviceProfileServiceStub(channel), meta, tenant_id
        )
        find_or_create_device(
            device_pb2_grpc.DeviceServiceStub(channel), meta, app_id, profile_id
        )
    except grpc.RpcError as e:
        die(f"gRPC provisioning failed: {e.code()} — {e.details()}")

    # ------------------------------------------------------------------
    # Step 3 — Verify anonymous MQTT is rejected
    # ------------------------------------------------------------------
    print("[smoke_test] Checking anonymous MQTT rejection ...")
    verify_anonymous_rejected()

    # ------------------------------------------------------------------
    # Step 4 — Subscribe and inject UDP frame
    # ------------------------------------------------------------------
    def inject_uplink() -> None:
        time.sleep(2)  # wait for subscriber to be connected
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_stats_frame(sock)
            time.sleep(1)
            send_uplink_frame(sock)
            sock.close()
        except Exception as exc:
            print(f"[smoke_test] UDP inject error: {exc}", file=sys.stderr)

    threading.Thread(target=inject_uplink, daemon=True).start()

    print(
        f"[smoke_test] Waiting up to {UPLINK_TIMEOUT_SECONDS}s for MQTT event ..."
    )
    if not wait_for_uplink(app_id, test_user, test_pass):
        die(
            f"No MQTT event received within {UPLINK_TIMEOUT_SECONDS}s on "
            f"application/{app_id}/device/{DEVICE_EUI}/event/+. "
            "Check 'docker compose logs chirpstack' for errors."
        )

    print("[smoke_test] SUCCESS — end-to-end verification passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
