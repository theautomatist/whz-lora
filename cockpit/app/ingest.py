"""ingest.py — MQTT subscriber that feeds CampaignState.

Two subscription groups:
  application/<app_id>/device/+/event/+  — JSON events (up / join / ack / txack)
  eu868/gateway/+/event/up               — protobuf UplinkFrame (always-on
                                            "Funkumgebung" coex classification,
                                            F-0006 "Trust & Sichtbarkeit")

Runs paho-mqtt loop_forever in a daemon thread; reconnects automatically on
disconnect (paho default behaviour when loop_forever is used).
"""
import json
import logging
import threading
from typing import Optional

import grpc
import paho.mqtt.client as mqtt
from chirpstack_api.gw import gw_pb2

from . import chirpstack as cs
from . import config
from .db import Database
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

    def __init__(
        self,
        state: CampaignState,
        app_id: str,
        db: Optional[Database] = None,
        grpc_channel: Optional[grpc.Channel] = None,
        grpc_token: Optional[str] = None,
    ) -> None:
        self._state = state
        self._app_id = app_id
        self._db = db  # F-0006 per-run CSV recording; None disables it (tests)
        # "Trust & Sichtbarkeit" — per-SF downlink reliability test; None
        # disables it (tests, or gRPC not (yet) available at startup).
        self._grpc_channel = grpc_channel
        self._grpc_token = grpc_token
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
            if self._db is not None:
                packet_count = None
                try:
                    packet_count = self._db.record_uplink_for_run(dev_eui, metrics)
                except Exception as e:
                    logger.warning(
                        "record_uplink_for_run failed for %s: %s", dev_eui, e
                    )
                if packet_count is not None:
                    self._maybe_send_downlink_test(dev_eui, packet_count)
        elif event_type == "join":
            dev_addr = evt.get("devAddr", "")
            self._state.process_join(dev_eui, dev_addr)
        elif event_type == "ack":
            # FIX: only count as ACK when the device actually acknowledged the
            # downlink. A confirmed downlink that timed out also triggers an
            # event/ack message with acknowledged=false — treat that as NACK.
            # Either way, ChirpStack has resolved the downlink attempt, so
            # record it as the device's last-downlink activity (F-0006
            # "Trust & Sichtbarkeit" — Geräte-Status).
            self._state.record_downlink_txack(dev_eui)
            acknowledged = bool(evt.get("acknowledged"))
            if self._db is not None:
                try:
                    self._db.record_downlink_test_ack(dev_eui, acknowledged)
                except Exception as e:
                    logger.warning(
                        "record_downlink_test_ack failed for %s: %s", dev_eui, e
                    )
            if acknowledged:
                self._state.process_ack(dev_eui)
            else:
                self._state.broadcast_nack(dev_eui)
        elif event_type == "txack":
            # ChirpStack confirms the downlink was actually transmitted over
            # the air (independent of confirmed/unconfirmed) — the earliest
            # "gesendet" signal for the Geräte-Status block.
            self._state.record_downlink_txack(dev_eui)

    def _maybe_send_downlink_test(self, dev_eui: str, packet_count: int) -> None:
        """F-0006 "Trust & Sichtbarkeit" — per-SF downlink reliability test.
        Best-effort: does nothing without both a DB (to decide/track) and a
        gRPC channel (to actually enqueue) — db.py already guards against
        piling up (never triggers while one is still pending/un-acked) and
        against a disabled run (downlink_test=False)."""
        if self._db is None or not (self._grpc_channel and self._grpc_token):
            return
        try:
            dl = self._db.maybe_trigger_downlink_test(dev_eui, packet_count)
        except Exception as e:
            logger.warning(
                "maybe_trigger_downlink_test failed for %s: %s", dev_eui, e
            )
            return
        if dl is None:
            return
        try:
            cs.enqueue_downlink(
                self._grpc_channel, self._grpc_token, dl["dev_eui"], dl["f_port"], dl["data_hex"]
            )
        except grpc.RpcError as e:
            logger.warning("downlink-test enqueue failed for %s: %s", dev_eui, e)

    def _handle_gateway_up(self, payload: bytes) -> None:
        """Decode a gateway UplinkFrame protobuf and forward to coex scan.

        Always-on (F-0006 "Trust & Sichtbarkeit"): every gateway frame is
        classified regardless of any UI toggle — there is no start/stop gate
        here anymore.
        """
        try:
            frame = gw_pb2.UplinkFrame.FromString(payload)
        except Exception as e:
            logger.warning("Gateway UplinkFrame decode error: %s", e)
            return

        tx = frame.tx_info
        sf = tx.modulation.lora.spreading_factor
        freq = tx.frequency
        # NOTE: rx_info is a *singular* message field in chirpstack-api
        # 4.18.0 (not repeated) — HasField, not indexing, is the correct
        # presence check. (Fixed here: the previous frame.rx_info[0] would
        # have raised TypeError on every real gateway uplink once this path
        # started running unconditionally.)
        rssi = frame.rx_info.rssi if frame.HasField("rx_info") else 0
        snr = frame.rx_info.snr if frame.HasField("rx_info") else 0.0
        phy = bytes(frame.phy_payload)

        if sf and freq:
            self._state.process_coex_frame(sf, freq, rssi, phy, snr)
