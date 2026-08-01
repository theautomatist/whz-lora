"""config.py — environment-based configuration for the Feldtest-Cockpit.

All env vars have in-compose defaults; override via docker-compose environment
or a .env file. No external imports — plain os.environ.
"""
import os

# ChirpStack gRPC endpoint (inside compose: service name + port)
CHIRPSTACK_HOST: str = os.environ.get("CHIRPSTACK_HOST", "chirpstack:8080")

# MQTT broker (inside compose: service name)
MQTT_HOST: str = os.environ.get("MQTT_HOST", "mosquitto")
MQTT_PORT: int = int(os.environ.get("MQTT_PORT", "1883"))

# MQTT credentials — testsubscriber has read access to application/# and eu868/gateway/#
MQTT_USERNAME: str = os.environ.get("MQTT_TEST_USERNAME", "testsubscriber")
MQTT_PASSWORD: str = os.environ.get("MQTT_TEST_PASSWORD", "testsubscriber")

# ChirpStack auth: API key takes priority over admin login
CHIRPSTACK_API_KEY: str = os.environ.get("CHIRPSTACK_API_KEY", "")
CHIRPSTACK_ADMIN_USER: str = os.environ.get("CHIRPSTACK_ADMIN_USER", "admin")
CHIRPSTACK_ADMIN_PASS: str = os.environ.get("CHIRPSTACK_ADMIN_PASS", "admin")

# Cockpit HTTP Basic auth
COCKPIT_USER: str = os.environ.get("COCKPIT_USER", "admin")
COCKPIT_PASSWORD: str = os.environ.get("COCKPIT_PASSWORD", "change-me")

# Data directory for CSV recordings (mounted volume in compose)
DATA_DIR: str = os.environ.get("DATA_DIR", "/data")

# F-0006 Feldmess-Workflow persistence (SQLite db + photo uploads), both
# inside the same mounted /data volume — reboot-safe.
DB_PATH: str = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "cockpit.db"))
PHOTOS_DIR: str = os.environ.get("PHOTOS_DIR", os.path.join(DATA_DIR, "photos"))

# F-0008 Map / Placement Editor (PoC) — uploaded floorplan/map images.
FLOORPLANS_DIR: str = os.environ.get("FLOORPLANS_DIR", os.path.join(DATA_DIR, "floorplans"))

# Well-known ChirpStack entities that must already exist
TENANT_NAME: str = "whz-lora"
APP_NAME: str = "whz-feldtest"
PROFILE_NAME: str = "WHZ-Feldtest-EU868"   # normal ADR (default)
PROFILE_SF9: str  = "WHZ-Feldtest-SF9"     # fixed DR3 = SF9  (adr_algorithm_id: fixed_dr3)
PROFILE_SF12: str = "WHZ-Feldtest-SF12"    # fixed DR0 = SF12 (adr_algorithm_id: fixed_dr0)
PROFILE_SF7: str  = "WHZ-Feldtest-SF7"     # fixed DR5 = SF7  (adr_algorithm_id: fixed_dr5)

# F-0006 Phase B — SF -> ChirpStack device-profile name, used by the
# per-device SF-sweep (run/start + the background scheduler).
SF_PROFILES: dict[int, str] = {
    7:  PROFILE_SF7,
    9:  PROFILE_SF9,
    12: PROFILE_SF12,
}

# Fixed gateway node — the single Kerlink iFemtoCell Evolution (bring-up
# confirmed against this EUI; see docs/user/kerlink-ifemtocell-bring-up.md).
GATEWAY_NAME: str = "whz-kerlink-ifevo"
GATEWAY_EUI: str = "7076ff0064071a3d"
