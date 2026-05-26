#!/usr/bin/env python3
"""
smoke_test.py — whz-lora verification check.

Performs an end-to-end smoke test against a running ChirpStack v4 stack:

1. Authenticates to ChirpStack gRPC API on localhost:8080.
   - If CHIRPSTACK_API_KEY is set and non-placeholder, uses it directly.
   - Otherwise, logs in with CHIRPSTACK_ADMIN_USER / CHIRPSTACK_ADMIN_PASS
     and creates a temporary API key.
2. Creates (idempotent find-or-create) a Tenant, Application,
   Device Profile, and Device.  The device is provisioned as ABP so that
   the smoke test can inject a MIC-valid Unconfirmed Data Up frame without
   an over-the-air join.
3. Sends a Semtech UDP Packet Forwarder PUSH_DATA frame (stats + RXPK)
   to localhost:1700 to simulate a gateway uplink.
4. Subscribes to the MQTT uplink topic and waits up to 30 seconds for
   the event.
5. Verifies that anonymous MQTT connections are rejected.
6. Exits 0 on success, non-zero with a clear error message on failure.

Required environment variables (set via .env or CI secrets):
  MQTT_TEST_USERNAME      — MQTT username for test subscriber
  MQTT_TEST_PASSWORD      — MQTT password for test subscriber

Optional:
  CHIRPSTACK_API_KEY      — Pre-created API key (skips login if provided)
  CHIRPSTACK_ADMIN_USER   — ChirpStack admin username (default: admin)
  CHIRPSTACK_ADMIN_PASS   — ChirpStack admin password (default: admin)
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

# AES-CMAC for LoRaWAN MIC computation
from cryptography.hazmat.primitives.cmac import CMAC
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.backends import default_backend

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

# ABP session keys and address — deterministic test values.
# All-zeros NwkSKey / AppSKey are intentionally weak; this is test-only.
ABP_DEV_ADDR = "01020304"
ABP_NWK_S_KEY = "00000000000000000000000000000001"  # 16 bytes hex
ABP_APP_S_KEY = "00000000000000000000000000000002"  # 16 bytes hex

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
                supports_otaa=False,
            )
        ),
        metadata=meta,
    )
    print(f"[smoke_test] Device profile created: {resp.id}")
    return resp.id


def find_or_create_device(
    stub, meta: list, app_id: str, profile_id: str
) -> None:
    """
    Find or create the smoke-test device and ensure ABP activation is set.

    ABP is used so the smoke test can inject a MIC-valid Unconfirmed Data Up
    frame without performing an over-the-air join (which ChirpStack v4 rejects
    when the MIC is zero).
    """
    device_existed = False
    try:
        existing = stub.Get(
            device_pb2.GetDeviceRequest(dev_eui=DEVICE_EUI), metadata=meta
        )
        print(f"[smoke_test] Device already exists: {existing.device.dev_eui}")
        device_existed = True
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.NOT_FOUND:
            raise

    if not device_existed:
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

    # Ensure ABP activation is present (idempotent — overwrite is safe).
    try:
        stub.Activate(
            device_pb2.ActivateDeviceRequest(
                device_activation=device_pb2.DeviceActivation(
                    dev_eui=DEVICE_EUI,
                    dev_addr=ABP_DEV_ADDR,
                    app_s_key=ABP_APP_S_KEY,
                    nwk_s_enc_key=ABP_NWK_S_KEY,
                    s_nwk_s_int_key=ABP_NWK_S_KEY,
                    f_nwk_s_int_key=ABP_NWK_S_KEY,
                    f_cnt_up=0,
                    n_f_cnt_down=0,
                    a_f_cnt_down=0,
                )
            ),
            metadata=meta,
        )
        print(f"[smoke_test] ABP activation set for: {DEVICE_EUI} (DevAddr={ABP_DEV_ADDR})")
    except grpc.RpcError as e:
        die(f"ABP Activate failed ({e.code()}): {e.details()}")


# ---------------------------------------------------------------------------
# LoRaWAN MIC helper
# ---------------------------------------------------------------------------


def compute_uplink_mic(
    nwk_s_key: bytes,
    dev_addr: bytes,
    f_cnt: int,
    mhdr: int,
    fhdr: bytes,
    fport: int,
    frm_payload: bytes,
) -> bytes:
    """
    Compute a LoRaWAN 1.0.x uplink MIC using AES-CMAC (TS001-1.0.3 §4.4).

    B0 = 0x49 || 0x00 0x00 0x00 0x00 || Dir=0 || DevAddr (LE) || FCntUp (LE) || 0x00 || len(msg)
    msg = MHDR || FHDR || FPort || FRMPayload
    MIC = first 4 bytes of AES128_CMAC(NwkSKey, B0 || msg)
    """
    msg = bytes([mhdr]) + fhdr + bytes([fport]) + frm_payload
    b0 = (
        bytes([0x49, 0x00, 0x00, 0x00, 0x00, 0x00])
        + dev_addr  # 4 bytes, little-endian
        + struct.pack("<I", f_cnt)
        + bytes([0x00, len(msg)])
    )
    c = CMAC(AES(nwk_s_key), backend=default_backend())
    c.update(b0 + msg)
    return c.finalize()[:4]


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


def send_uplink_frame(sock: socket.socket, f_cnt: int = 1) -> None:
    """
    Send a MIC-valid Unconfirmed Data Up frame for the ABP-provisioned device.

    MHDR = 0x40 (Unconfirmed Data Up, MType=0b010, RFU=0, Major=0)
    FHDR = DevAddr (LE) || FCtrl=0x00 || FCnt (LE 2 bytes)
    FPort = 1
    FRMPayload = b'\xDE\xAD' (arbitrary test payload)
    MIC computed with NwkSEncKey using AES-CMAC per LoRaWAN 1.0.3 §4.4.
    """
    token = random.randint(0, 0xFFFF)

    nwk_s_key = bytes.fromhex(ABP_NWK_S_KEY)
    dev_addr_bytes = bytes.fromhex(ABP_DEV_ADDR)[::-1]  # little-endian

    mhdr = 0x40  # Unconfirmed Data Up
    fctrl = 0x00
    fcnt_le = struct.pack("<H", f_cnt)
    fhdr = dev_addr_bytes + bytes([fctrl]) + fcnt_le
    fport = 1
    frm_payload = b"\xDE\xAD"

    mic = compute_uplink_mic(
        nwk_s_key, dev_addr_bytes, f_cnt, mhdr, fhdr, fport, frm_payload
    )
    phy = bytes([mhdr]) + fhdr + bytes([fport]) + frm_payload + mic

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
    print(
        f"[smoke_test] Sent Unconfirmed Data Up PUSH_DATA "
        f"(DevAddr={ABP_DEV_ADDR}, FCnt={f_cnt}, token={token:#06x})"
    )


# ---------------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------------


def wait_for_uplink(
    app_id: str,
    username: str,
    password: str,
    subscribed_gate: threading.Event,
) -> bool:
    """
    Subscribe to application events and wait up to UPLINK_TIMEOUT_SECONDS.

    Sets subscribed_gate once the MQTT subscription is confirmed (SUBACK),
    so that the inject thread can start only after the subscriber is ready.
    Returns True if an event is received within the timeout.
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
            subscribed_gate.set()  # unblock inject thread even on failure

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        print(f"[smoke_test] MQTT subscription confirmed (mid={mid})")
        subscribed_gate.set()

    def on_message(client, userdata, msg):
        print(f"[smoke_test] MQTT event on {msg.topic}: {msg.payload[:120]!r}")
        received.set()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="whz-smoke-sub",
        clean_session=True,
    )
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.username_pw_set(username, password)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    except OSError as e:
        die(f"Cannot connect to Mosquitto at {MQTT_HOST}:{MQTT_PORT}: {e}")

    client.loop_start()
    ok = received.wait(timeout=UPLINK_TIMEOUT_SECONDS)
    client.loop_stop()
    client.disconnect()
    return ok


def verify_anonymous_rejected() -> None:
    """Assert that anonymous MQTT connections are refused."""
    connected = threading.Event()
    rc_holder = [None]

    def on_connect(client, userdata, flags, reason_code, properties):
        rc_holder[0] = reason_code
        connected.set()

    anon = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="whz-smoke-anon",
        clean_session=True,
    )
    anon.on_connect = on_connect

    try:
        anon.connect(MQTT_HOST, MQTT_PORT, keepalive=5)
        anon.loop_start()
        if not connected.wait(timeout=5):
            anon.loop_stop()
            # TCP connection made but no CONNACK arrived — treat as rejected.
            print("[smoke_test] Anonymous MQTT: no CONNACK within 5s — treated as rejected OK")
            anon.disconnect()
            return
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
    # Step 4 — Subscribe first, then inject UDP frame after subscription
    #           is confirmed to avoid the race between inject and subscribe.
    # ------------------------------------------------------------------
    subscribed_gate = threading.Event()

    def inject_uplink() -> None:
        # Wait until the MQTT subscriber has confirmed its subscription
        # before sending the frame; avoids the inject-before-subscribe race.
        if not subscribed_gate.wait(timeout=15):
            print(
                "[smoke_test] WARNING: MQTT subscription not confirmed within 15s; "
                "injecting anyway.",
                file=sys.stderr,
            )
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_stats_frame(sock)
            time.sleep(0.5)
            send_uplink_frame(sock)
            sock.close()
        except Exception as exc:
            print(f"[smoke_test] UDP inject error: {exc}", file=sys.stderr)

    inject_thread = threading.Thread(target=inject_uplink, daemon=True)
    inject_thread.start()

    print(
        f"[smoke_test] Waiting up to {UPLINK_TIMEOUT_SECONDS}s for MQTT event ..."
    )
    received = wait_for_uplink(app_id, test_user, test_pass, subscribed_gate)

    if not received:
        die(
            f"No MQTT event received within {UPLINK_TIMEOUT_SECONDS}s on "
            f"application/{app_id}/device/{DEVICE_EUI}/event/+. "
            "Check 'docker compose logs chirpstack' for errors."
        )

    print("[smoke_test] SUCCESS — end-to-end verification passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
