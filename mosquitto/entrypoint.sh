#!/bin/sh
# Mosquitto entrypoint - generate passwd file from environment variables,
# then exec the broker.  The passwd file is written to a named volume at
# /mosquitto/data, never the bind-mounted /mosquitto/config (Windows host
# permission round-trips break read-back from the daemon).
set -eu

PASSWD_FILE=/mosquitto/data/passwd

mkdir -p /mosquitto/data
chown -R mosquitto:mosquitto /mosquitto/data

# Create / overwrite the passwd file with the two required users.
mosquitto_passwd -b -c "$PASSWD_FILE" \
    "$CHIRPSTACK_MQTT_USERNAME" "$CHIRPSTACK_MQTT_PASSWORD"
mosquitto_passwd -b "$PASSWD_FILE" \
    "$MQTT_TEST_USERNAME" "$MQTT_TEST_PASSWORD"

# mosquitto_passwd writes 0600 owned by root; the daemon drops privileges
# to the mosquitto user and would not be able to read it otherwise.
chown mosquitto:mosquitto "$PASSWD_FILE"

exec /usr/sbin/mosquitto -c /mosquitto/config/mosquitto.conf
