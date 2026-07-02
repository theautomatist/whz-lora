#!/usr/bin/env python3
"""register_device.py — register one OTAA device into the whz-feldtest app.

Looks up tenant 'whz-lora', application 'whz-feldtest' and device profile
'WHZ-Feldtest-EU868' by name, then creates the device and sets its OTAA
key. For LoRaWAN 1.0.x the single AppKey is stored in ChirpStack's
'nwk_key' field (a known v4 quirk). Idempotent: re-running updates the key.

Usage (keys are printed on the TRV label / datasheet):
  .venv/bin/python scripts/register_device.py \
      --name trv-1 --dev-eui <16hex> --app-key <32hex> [--join-eui <16hex>]
"""
import argparse, sys, grpc
from chirpstack_api.api import (internal_pb2, internal_pb2_grpc,
    tenant_pb2, tenant_pb2_grpc,
    application_pb2, application_pb2_grpc,
    device_profile_pb2, device_profile_pb2_grpc,
    device_pb2, device_pb2_grpc)

TENANT, APP, PROFILE = "whz-lora", "whz-feldtest", "WHZ-Feldtest-EU868"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--dev-eui", required=True, help="16 hex chars")
    ap.add_argument("--app-key", required=True, help="32 hex chars (LoRaWAN 1.0.x AppKey)")
    ap.add_argument("--join-eui", default="0000000000000000", help="16 hex chars (default all-zero)")
    ap.add_argument("--server", default="localhost:8080")
    a = ap.parse_args()
    dev_eui = a.dev_eui.lower().replace(":", "")
    app_key = a.app_key.lower().replace(":", "")
    join_eui = a.join_eui.lower().replace(":", "")
    if len(dev_eui) != 16: sys.exit("dev-eui must be 16 hex chars")
    if len(app_key) != 32: sys.exit("app-key must be 32 hex chars")

    ch = grpc.insecure_channel(a.server)
    jwt = internal_pb2_grpc.InternalServiceStub(ch).Login(
        internal_pb2.LoginRequest(email="admin", password="admin")).jwt
    meta = [("authorization", f"Bearer {jwt}")]

    tid = next((t.id for t in tenant_pb2_grpc.TenantServiceStub(ch).List(
        tenant_pb2.ListTenantsRequest(limit=100), metadata=meta).result if t.name == TENANT), None)
    aid = next((x.id for x in application_pb2_grpc.ApplicationServiceStub(ch).List(
        application_pb2.ListApplicationsRequest(limit=100, tenant_id=tid), metadata=meta).result if x.name == APP), None)
    pid = next((p.id for p in device_profile_pb2_grpc.DeviceProfileServiceStub(ch).List(
        device_profile_pb2.ListDeviceProfilesRequest(limit=100, tenant_id=tid), metadata=meta).result if p.name == PROFILE), None)
    for label, val in (("tenant", tid), ("application", aid), ("device profile", pid)):
        if not val: sys.exit(f"{label} not found — run the profile/app setup first")

    dstub = device_pb2_grpc.DeviceServiceStub(ch)
    try:
        dstub.Get(device_pb2.GetDeviceRequest(dev_eui=dev_eui), metadata=meta)
        print(f"device {dev_eui} exists — keeping it")
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.NOT_FOUND: raise
        dstub.Create(device_pb2.CreateDeviceRequest(device=device_pb2.Device(
            dev_eui=dev_eui, name=a.name, join_eui=join_eui,
            application_id=aid, device_profile_id=pid, is_disabled=False)), metadata=meta)
        print(f"device created: {dev_eui} ({a.name})")

    keys = device_pb2.DeviceKeys(dev_eui=dev_eui, nwk_key=app_key)  # 1.0.x: AppKey -> nwk_key
    try:
        dstub.CreateKeys(device_pb2.CreateDeviceKeysRequest(device_keys=keys), metadata=meta)
        print("OTAA key set")
    except grpc.RpcError as e:
        if e.code() != grpc.StatusCode.ALREADY_EXISTS: raise
        dstub.UpdateKeys(device_pb2.UpdateDeviceKeysRequest(device_keys=keys), metadata=meta)
        print("OTAA key updated")
    print(f"OK: {a.name} ready for OTAA join (JoinEUI={join_eui})")

if __name__ == "__main__":
    main()
