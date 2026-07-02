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

# Well-known ChirpStack entities that must already exist
TENANT_NAME: str = "whz-lora"
APP_NAME: str = "whz-feldtest"
PROFILE_NAME: str = "WHZ-Feldtest-EU868"
