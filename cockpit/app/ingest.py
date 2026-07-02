"""ingest.py — MQTT subscriber that feeds CampaignState.

Two subscription groups:
  application/<app_id>/device/+/event/+  — JSON events (up / join / ack)
  eu868/gateway/+/event/up               — protobuf UplinkFrame (coex scan)

Runs paho-mqtt loop_forever in a daemon thread; reconnects automatically on
disconnect (paho default behaviour when loop_forever is used).
"""
import json
import logging
import threading
from typing import Optional

import paho.mqtt.client as mqtt
from chirpstack_api.gw import gw_pb2

from . import config
from .state import CampaignState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Uplink-event parser (replicates field_logger.parse_event logic)
# ---------------------------------------------------------------------------


def _best_rx(rx_info: list) -> dict:
    """Return the gateway RX entry with the highest RSSI."""
    if not rx_info:
        return {}
    return max(rx_info, key=lambda r: r.get("rssi", -9999))


def _parse_uplink_event(evt: dict) -> dict:
    """Extract per-uplink metrics from a ChirpStack v4 event/up JSON object."""
    dev_info = evt.get("deviceInfo", {}) or {}
    tx = evt.get("txInfo", {}) or {}
    lora = (tx.get("modulation", {}) or {}).get("lora", {}) or {}
    rx = _best_rx(evt.get("rxInfo", []) or [])
    return {
        "dev_eui": dev_info.get("devEui", ""),
        "rssi_dbm": rx.get("rssi"),
        "snr_db": rx.get("snr"),
        "sf": lora.get("spreadingFactor"),
        "freq_hz": tx.get("frequency"),
        "f_cnt": evt.get("fCnt"),
        "gw_eui": rx.get("gatewayId", ""),
    }


# ---------------------------------------------------------------------------
# MQTT ingest
# ---------------------------------------------------------------------------


class MQTTIngest:
    """Subscribes to application and gateway MQTT topics and updates state."""

    def __init__(self, state: CampaignState, app_id: str) -> None:
        self._state = state
        self._app_id = app_id
        self._client: Optional[mqtt.Client] = None
        self._thread: Optional[threading.Thread] = None
        self._app_topic = f"application/{app_id}/device/+/event/+"
        self._gw_topic = "eu868/gateway/+/event/up"

    def start(self) -> None:
        """Connect to Mosquitto and start the receive loop in a daemon thread."""
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="whz-cockpit-ingest",
            clean_session=True,
        )
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)

        try:
            client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
        except OSError as e:
            logger.error(
                "MQTT connect failed to %s:%d: %s",
                config.MQTT_HOST,
                config.MQTT_PORT,
                e,
            )
            return

        self._client = client
        self._thread = threading.Thread(
            target=client.loop_forever, daemon=True, name="mqtt-ingest"
        )
        self._thread.start()
        logger.info(
            "MQTT ingest started (%s:%d)", config.MQTT_HOST, config.MQTT_PORT
        )

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code != 0:
            logger.error("MQTT connection rejected (rc=%s)", reason_code)
            return
        client.subscribe([(self._app_topic, 0), (self._gw_topic, 0)])
        logger.info(
            "MQTT subscribed to %r and %r", self._app_topic, self._gw_topic
        )

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        if reason_code != 0:
            logger.warning("MQTT disconnected (rc=%s) — will reconnect.", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        topic: str = msg.topic
        payload: bytes = msg.payload

        if topic.startswith("application/"):
            # application/<app_id>/device/<dev_eui>/event/<type>
            parts = topic.split("/")
            if len(parts) >= 6:
                self._handle_app_event(parts[5], payload)
        elif topic.endswith("/event/up") and "gateway" in topic:
            self._handle_gateway_up(payload)

    def _handle_app_event(self, event_type: str, payload: bytes) -> None:
        try:
            evt = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            logger.warning("App event JSON decode error: %s", e)
            return

        dev_info = evt.get("deviceInfo", {}) or {}
        dev_eui = dev_info.get("devEui", "")

        if event_type == "up":
            metrics = _parse_uplink_event(evt)
            self._state.process_uplink(metrics)
        elif event_type == "join":
            dev_addr = evt.get("devAddr", "")
            self._state.process_join(dev_eui, dev_addr)
        elif event_type == "ack":
            # FIX: only count as ACK when the device actually acknowledged the
            # downlink. A confirmed downlink that timed out also triggers an
            # event/ack message with acknowledged=false — treat that as NACK.
            if evt.get("acknowledged"):
                self._state.process_ack(dev_eui)
            else:
                self._state.broadcast_nack(dev_eui)

    def _handle_gateway_up(self, payload: bytes) -> None:
        """Decode a gateway UplinkFrame protobuf and forward to coex scan."""
        if not self._state.is_coex_active():
            return
        try:
            frame = gw_pb2.UplinkFrame.FromString(payload)
        except Exception as e:
            logger.warning("Gateway UplinkFrame decode error: %s", e)
            return

        tx = frame.tx_info
        sf = tx.modulation.lora.spreading_factor
        freq = tx.frequency
        rssi = frame.rx_info[0].rssi if frame.rx_info else 0
        phy = bytes(frame.phy_payload)

        if sf and freq:
            self._state.process_coex_frame(sf, freq, rssi, phy)
