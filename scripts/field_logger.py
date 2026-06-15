#!/usr/bin/env python3
"""field_logger.py — log ChirpStack v4 uplink metrics to CSV for the field test.

Subscribes to ``application/<app_id>/device/+/event/up`` and appends one CSV row
per received uplink:

    timestamp_utc, dev_eui, pos_id, rssi_dbm, snr_db, sf, freq_hz, f_cnt, gw_eui

The current measurement point (``pos_id``) is set *live* in the terminal: type a
new ID + Enter before moving to the next point; type ``q`` to finish. RSSI / SNR /
SF / frequency / fCnt / gateway come straight from each uplink — see the test
concept (``docs/developer/analysis/test-concept.pdf``). PDR per point is later
``received (this CSV) / sent (known N)``.

Before the field test:
  * stack running:        docker compose up -d --wait
  * device profile:       ADR = Disabled, fixed SF; test node joined
  * .env:                 MQTT_TEST_USERNAME / MQTT_TEST_PASSWORD
  * application id known:  CHIRPSTACK_APP_ID  (or pass --app-id)

Usage:
  py -3.12 scripts/field_logger.py --app-id <uuid> [--out field.csv] [--pos P0]
"""
import argparse
import csv
import datetime
import json
import os
import sys
import threading

import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
COLUMNS = ["timestamp_utc", "dev_eui", "pos_id", "rssi_dbm", "snr_db",
           "sf", "freq_hz", "f_cnt", "gw_eui"]

_state = {"pos_id": "P0"}
_lock = threading.Lock()


def _now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def best_rx(rx_info: list) -> dict:
    """Pick the gateway reception with the strongest RSSI (one GW in this test)."""
    if not rx_info:
        return {}
    return max(rx_info, key=lambda r: r.get("rssi", -9999))


def parse_event(evt: dict) -> dict:
    """Extract the metrics from a ChirpStack v4 uplink (event/up) JSON object."""
    dev = evt.get("deviceInfo", {}) or {}
    tx = evt.get("txInfo", {}) or {}
    lora = (tx.get("modulation", {}) or {}).get("lora", {}) or {}
    rx = best_rx(evt.get("rxInfo", []) or [])
    return {
        "dev_eui": dev.get("devEui", ""),
        "rssi_dbm": rx.get("rssi", ""),
        "snr_db": rx.get("snr", ""),
        "sf": lora.get("spreadingFactor", ""),
        "freq_hz": tx.get("frequency", ""),
        "f_cnt": evt.get("fCnt", ""),
        "gw_eui": rx.get("gatewayId", ""),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Log ChirpStack uplink metrics to CSV per measurement point.")
    ap.add_argument("--app-id", default=os.environ.get("CHIRPSTACK_APP_ID", ""),
                    help="ChirpStack Application-ID (UUID); alternativ CHIRPSTACK_APP_ID.")
    ap.add_argument("--out", default="", help="CSV-Datei (Default: field_<UTC-Zeit>.csv).")
    ap.add_argument("--pos", default="P0", help="Start-Messpunkt-ID (Default: P0).")
    args = ap.parse_args()

    if not args.app_id:
        sys.exit("FEHLER: --app-id <uuid> angeben oder CHIRPSTACK_APP_ID setzen "
                 "(App-ID aus der ChirpStack-UI bzw. aus smoke_test.py).")

    _state["pos_id"] = args.pos
    out = args.out or f"field_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M')}.csv"
    user = os.environ.get("MQTT_TEST_USERNAME", "testsubscriber")
    pw = os.environ.get("MQTT_TEST_PASSWORD", "testsubscriber")
    topic = f"application/{args.app_id}/device/+/event/up"

    new_file = not os.path.exists(out)
    fh = open(out, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=COLUMNS)
    if new_file:
        writer.writeheader()
        fh.flush()
    counts: dict = {}

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print(f"[field_logger] MQTT verbunden — abonniere {topic}")
            client.subscribe(topic)
        else:
            print(f"[field_logger] MQTT-Verbindung abgelehnt (rc={reason_code})", file=sys.stderr)

    def on_subscribe(client, userdata, mid, reason_codes, properties):
        print("[field_logger] Abo bestätigt — bereit.")

    def on_message(client, userdata, msg):
        try:
            evt = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        row = parse_event(evt)
        with _lock:
            pos = _state["pos_id"]
        row["pos_id"] = pos
        row["timestamp_utc"] = _now_utc()
        writer.writerow(row)
        fh.flush()
        counts[pos] = counts.get(pos, 0) + 1
        print(f"  [{pos}] #{counts[pos]:>3}  dev={row['dev_eui']}  rssi={row['rssi_dbm']} dBm  "
              f"snr={row['snr_db']} dB  sf={row['sf']}  fcnt={row['f_cnt']}  gw={row['gw_eui']}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="whz-field-logger",
                         clean_session=True)
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.username_pw_set(user, pw)
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    except OSError as e:
        sys.exit(f"FEHLER: keine MQTT-Verbindung zu {MQTT_HOST}:{MQTT_PORT}: {e}")

    client.loop_start()
    print(f"[field_logger] CSV: {out}   ·   aktueller Messpunkt: {_state['pos_id']}")
    print("[field_logger] Neuen Messpunkt setzen: ID eingeben + Enter (z. B. 'V_3OG'); 'q' = Ende.")
    try:
        while True:
            line = input().strip()
            if line.lower() in ("q", "quit", "exit"):
                break
            if line:
                with _lock:
                    _state["pos_id"] = line
                print(f"  → Messpunkt jetzt: {line}  (bisher {counts.get(line, 0)} Pakete an diesem Punkt)")
    except (EOFError, KeyboardInterrupt):
        pass

    client.loop_stop()
    client.disconnect()
    fh.close()
    total = sum(counts.values())
    print(f"\n[field_logger] Ende. {total} Pakete in {len(counts)} Messpunkten -> {out}")
    for pos, n in sorted(counts.items()):
        print(f"  {pos}: {n}")


if __name__ == "__main__":
    main()
