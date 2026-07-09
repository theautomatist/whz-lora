"""test_ingest.py — unit tests for the F-0006 per-run recording hook in
ingest.py: on every 'up' event, MQTTIngest must call
db.record_uplink_for_run(dev_eui, metrics) in addition to the existing
state.process_uplink(metrics) — and must not crash the ingest loop if that
call raises.

Also covers F-0006 "Trust & Sichtbarkeit": the always-on gateway-frame path
(_handle_gateway_up, Task 1) and the txack/ack downlink-visibility hooks
(Task 2).

No real MQTT broker or ChirpStack server involved — _handle_app_event is
called directly with a JSON payload matching ChirpStack v4's event/up shape.
"""
import json
from unittest.mock import MagicMock

from chirpstack_api.gw import gw_pb2

from app.ingest import MQTTIngest

SAMPLE_UP_EVENT = {
    "deviceInfo": {"devEui": "aaaa000000000001"},
    "fCnt": 12,
    "txInfo": {
        "frequency": 868100000,
        "modulation": {"lora": {"spreadingFactor": 9}},
    },
    "rxInfo": [
        {"rssi": -71, "snr": 7.2, "gatewayId": "7076ff0064071a3d"},
    ],
}


def _make_ingest(db=None):
    state = MagicMock()
    return MQTTIngest(state, "app-id", db), state


def test_up_event_calls_process_uplink():
    ingest, state = _make_ingest(db=None)
    ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))
    state.process_uplink.assert_called_once()
    metrics = state.process_uplink.call_args[0][0]
    assert metrics["dev_eui"] == "aaaa000000000001"
    assert metrics["rssi_dbm"] == -71
    assert metrics["sf"] == 9


def test_up_event_calls_record_uplink_for_run_when_db_present():
    db = MagicMock()
    ingest, state = _make_ingest(db=db)
    ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))

    db.record_uplink_for_run.assert_called_once()
    dev_eui, metrics = db.record_uplink_for_run.call_args[0]
    assert dev_eui == "aaaa000000000001"
    assert metrics["sf"] == 9


def test_up_event_no_db_does_not_crash():
    """db=None (e.g. not yet initialised) must not raise — ingest keeps working."""
    ingest, state = _make_ingest(db=None)
    ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))
    state.process_uplink.assert_called_once()


def test_up_event_db_exception_is_swallowed():
    """record_uplink_for_run raising must not stop the ingest loop or
    prevent live-metrics processing."""
    db = MagicMock()
    db.record_uplink_for_run.side_effect = RuntimeError("disk full")
    ingest, state = _make_ingest(db=db)

    # Must not raise
    ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))
    state.process_uplink.assert_called_once()


def test_join_event_unaffected_by_db():
    db = MagicMock()
    ingest, state = _make_ingest(db=db)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "devAddr": "01020304"}
    ingest._handle_app_event("join", json.dumps(evt).encode("utf-8"))

    state.process_join.assert_called_once_with("aaaa000000000001", "01020304")
    db.record_uplink_for_run.assert_not_called()


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" (Task 2) — txack/ack -> record_downlink_txack
# ---------------------------------------------------------------------------


def test_txack_event_calls_record_downlink_txack():
    ingest, state = _make_ingest(db=None)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}}
    ingest._handle_app_event("txack", json.dumps(evt).encode("utf-8"))
    state.record_downlink_txack.assert_called_once_with("aaaa000000000001")


def test_ack_event_acknowledged_also_records_txack():
    ingest, state = _make_ingest(db=None)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "acknowledged": True}
    ingest._handle_app_event("ack", json.dumps(evt).encode("utf-8"))
    state.record_downlink_txack.assert_called_once_with("aaaa000000000001")
    state.process_ack.assert_called_once_with("aaaa000000000001")
    state.broadcast_nack.assert_not_called()


def test_ack_event_nack_also_records_txack():
    """Even a NACK (acknowledged=false) means ChirpStack transmitted the
    downlink — record_downlink_txack must still fire."""
    ingest, state = _make_ingest(db=None)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "acknowledged": False}
    ingest._handle_app_event("ack", json.dumps(evt).encode("utf-8"))
    state.record_downlink_txack.assert_called_once_with("aaaa000000000001")
    state.broadcast_nack.assert_called_once_with("aaaa000000000001")
    state.process_ack.assert_not_called()


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" (Task 1) — always-on "Funkumgebung"
# ---------------------------------------------------------------------------


def test_gateway_up_processes_frame_without_coex_toggle():
    """process_coex_frame must be called on every gateway uplink regardless
    of any coex toggle — there is no is_coex_active() gate anymore."""
    ingest, state = _make_ingest(db=None)

    frame = gw_pb2.UplinkFrame()
    frame.tx_info.frequency = 868100000
    frame.tx_info.modulation.lora.spreading_factor = 7
    frame.rx_info.rssi = -70
    frame.phy_payload = bytes([0x40, 0x01, 0x02, 0x03, 0x04, 0x00, 0x01, 0x00])

    ingest._handle_gateway_up(frame.SerializeToString())

    state.process_coex_frame.assert_called_once_with(
        7, 868100000, -70, frame.phy_payload
    )
    state.is_coex_active.assert_not_called()


def test_gateway_up_without_rx_info_defaults_rssi_zero():
    """rx_info is a singular (not repeated) field in chirpstack-api 4.18.0 —
    when absent, HasField(...) must gate the default, not indexing (which
    would raise TypeError)."""
    ingest, state = _make_ingest(db=None)

    frame = gw_pb2.UplinkFrame()
    frame.tx_info.frequency = 868100000
    frame.tx_info.modulation.lora.spreading_factor = 7
    frame.phy_payload = bytes([0x40, 0x01, 0x02, 0x03, 0x04, 0x00, 0x01, 0x00])

    ingest._handle_gateway_up(frame.SerializeToString())

    state.process_coex_frame.assert_called_once_with(
        7, 868100000, 0, frame.phy_payload
    )
