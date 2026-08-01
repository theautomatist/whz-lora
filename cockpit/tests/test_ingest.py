"""test_ingest.py — unit tests for the F-0006 per-run recording hook in
ingest.py: on every 'up' event, MQTTIngest must call
db.record_uplink_for_run(dev_eui, metrics) in addition to the existing
state.process_uplink(metrics) — and must not crash the ingest loop if that
call raises.

Also covers F-0006 "Trust & Sichtbarkeit": the always-on gateway-frame path
(_handle_gateway_up, Task 1), the txack/ack downlink-visibility hooks
(Task 2), and the per-SF confirmed-downlink reliability test wiring (every
uplink -> db.maybe_trigger_downlink_test -> cs.enqueue_downlink; every ack
-> db.record_downlink_test_ack).

No real MQTT broker or ChirpStack server involved — _handle_app_event is
called directly with a JSON payload matching ChirpStack v4's event/up shape.
"""
import json
from unittest.mock import MagicMock, patch

import grpc
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


def _make_ingest(db=None, grpc_channel=None, grpc_token=None):
    state = MagicMock()
    return MQTTIngest(state, "app-id", db, grpc_channel, grpc_token), state


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
    frame.rx_info.snr = 7.5
    frame.phy_payload = bytes([0x40, 0x01, 0x02, 0x03, 0x04, 0x00, 0x01, 0x00])

    ingest._handle_gateway_up(frame.SerializeToString())

    state.process_coex_frame.assert_called_once_with(
        7, 868100000, -70, frame.phy_payload, 7.5
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
        7, 868100000, 0, frame.phy_payload, 0.0
    )


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" — per-SF confirmed-downlink reliability test
# ---------------------------------------------------------------------------


def test_up_event_triggers_downlink_test_when_grpc_ready():
    db = MagicMock()
    db.record_uplink_for_run.return_value = 3
    db.maybe_trigger_downlink_test.return_value = {
        "dev_eui": "aaaa000000000001", "f_port": 1, "data_hex": "04",
        "run_id": 1, "sf": 7,
    }
    channel = MagicMock()
    ingest, state = _make_ingest(db=db, grpc_channel=channel, grpc_token="tok")

    with patch("app.ingest.cs.enqueue_downlink") as mock_enqueue, patch(
        "app.ingest.cs.get_token", return_value="fresh-tok"
    ) as mock_get_token:
        ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))

    db.maybe_trigger_downlink_test.assert_called_once_with("aaaa000000000001", 3)
    # The token is fetched per call rather than reused from construction: this
    # thread outlives the JWT's 24 h lifetime, and a stale one silently
    # disabled every ChirpStack call for days (finding B-1).
    mock_get_token.assert_called_once_with(channel)
    mock_enqueue.assert_called_once_with(
        channel, "fresh-tok", "aaaa000000000001", 1, "04"
    )


def test_up_event_no_downlink_test_without_grpc():
    """db present but no gRPC channel/token — maybe_trigger_downlink_test
    must not even be called (best-effort degrade, matches every other gRPC-
    dependent path in this codebase)."""
    db = MagicMock()
    db.record_uplink_for_run.return_value = 3
    ingest, state = _make_ingest(db=db, grpc_channel=None, grpc_token=None)

    with patch("app.ingest.cs.enqueue_downlink") as mock_enqueue:
        ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))

    db.maybe_trigger_downlink_test.assert_not_called()
    mock_enqueue.assert_not_called()


def test_up_event_downlink_test_none_result_does_not_enqueue():
    db = MagicMock()
    db.record_uplink_for_run.return_value = 3
    db.maybe_trigger_downlink_test.return_value = None
    ingest, state = _make_ingest(db=db, grpc_channel=MagicMock(), grpc_token="tok")

    with patch("app.ingest.cs.enqueue_downlink") as mock_enqueue:
        ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))

    mock_enqueue.assert_not_called()


def test_up_event_downlink_test_exception_is_swallowed():
    db = MagicMock()
    db.record_uplink_for_run.return_value = 3
    db.maybe_trigger_downlink_test.side_effect = RuntimeError("db locked")
    ingest, state = _make_ingest(db=db, grpc_channel=MagicMock(), grpc_token="tok")

    # Must not raise
    ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))
    state.process_uplink.assert_called_once()


def test_up_event_enqueue_rpc_error_is_swallowed():
    db = MagicMock()
    db.record_uplink_for_run.return_value = 3
    db.maybe_trigger_downlink_test.return_value = {
        "dev_eui": "aaaa000000000001", "f_port": 1, "data_hex": "04", "run_id": 1, "sf": 7,
    }
    ingest, state = _make_ingest(db=db, grpc_channel=MagicMock(), grpc_token="tok")

    class _Err(grpc.RpcError):
        def details(self):
            return "unavailable"

    with patch("app.ingest.cs.enqueue_downlink", side_effect=_Err()):
        ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))  # must not raise


def test_up_event_no_active_run_skips_downlink_test():
    """record_uplink_for_run returning None (no active run for the device)
    must skip the downlink-test check entirely — nothing to attribute an
    SF-segment test to."""
    db = MagicMock()
    db.record_uplink_for_run.return_value = None
    ingest, state = _make_ingest(db=db, grpc_channel=MagicMock(), grpc_token="tok")

    ingest._handle_app_event("up", json.dumps(SAMPLE_UP_EVENT).encode("utf-8"))

    db.maybe_trigger_downlink_test.assert_not_called()


def test_ack_event_calls_record_downlink_test_ack_acknowledged():
    db = MagicMock()
    ingest, state = _make_ingest(db=db)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "acknowledged": True}
    ingest._handle_app_event("ack", json.dumps(evt).encode("utf-8"))
    db.record_downlink_test_ack.assert_called_once_with("aaaa000000000001", True)


def test_ack_event_calls_record_downlink_test_ack_nack():
    db = MagicMock()
    ingest, state = _make_ingest(db=db)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "acknowledged": False}
    ingest._handle_app_event("ack", json.dumps(evt).encode("utf-8"))
    db.record_downlink_test_ack.assert_called_once_with("aaaa000000000001", False)


def test_ack_event_record_downlink_test_ack_exception_is_swallowed():
    db = MagicMock()
    db.record_downlink_test_ack.side_effect = RuntimeError("db locked")
    ingest, state = _make_ingest(db=db)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "acknowledged": True}

    # Must not raise
    ingest._handle_app_event("ack", json.dumps(evt).encode("utf-8"))
    state.process_ack.assert_called_once_with("aaaa000000000001")


def test_ack_event_no_db_does_not_crash():
    ingest, state = _make_ingest(db=None)
    evt = {"deviceInfo": {"devEui": "aaaa000000000001"}, "acknowledged": True}
    ingest._handle_app_event("ack", json.dumps(evt).encode("utf-8"))  # must not raise
    state.process_ack.assert_called_once_with("aaaa000000000001")
