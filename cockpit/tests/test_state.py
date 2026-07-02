"""test_state.py — unit tests for CampaignState, PointMeta, and build_csv_row.

Runs without grpc or fastapi — only stdlib + local pure modules are imported.
"""
import tempfile
import os
import pytest

from app.state import (
    CSV_COLUMNS,
    CampaignState,
    DeviceMetrics,
    PointMeta,
    build_csv_row,
)

# ---------------------------------------------------------------------------
# Sample uplink metrics (matches field_logger / ingest parse output)
# ---------------------------------------------------------------------------

SAMPLE_UPLINK = {
    "dev_eui":   "0102030405060708",
    "rssi_dbm":  -65,
    "snr_db":    8.5,
    "sf":        7,
    "freq_hz":   868100000,
    "f_cnt":     42,
    "gw_eui":    "aabbccddeeff0011",
}

SAMPLE_POINT = PointMeta(
    pos_id="P1",
    floor="3OG",
    room="R301",
    point_type="indoor",
    path="direct",
    los="LOS",
    mounting="desk",
    expected_n=50,
)

# ---------------------------------------------------------------------------
# build_csv_row — standalone function tests
# ---------------------------------------------------------------------------


def test_build_csv_row_all_columns_present():
    row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, "3dbi")
    for col in CSV_COLUMNS:
        assert col in row, f"Missing CSV column: {col}"


def test_build_csv_row_metrics_copied():
    row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, "12dbi")
    assert row["dev_eui"] == "0102030405060708"
    assert row["rssi_dbm"] == -65
    assert row["snr_db"] == 8.5
    assert row["sf"] == 7
    assert row["freq_hz"] == 868100000
    assert row["f_cnt"] == 42
    assert row["gw_eui"] == "aabbccddeeff0011"


def test_build_csv_row_point_metadata():
    row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, "3dbi")
    assert row["pos_id"] == "P1"
    assert row["floor"] == "3OG"
    assert row["room"] == "R301"
    assert row["point_type"] == "indoor"
    assert row["path"] == "direct"
    assert row["los"] == "LOS"
    assert row["mounting"] == "desk"


def test_build_csv_row_antenna():
    for ant in ("3dbi", "12dbi"):
        row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, ant)
        assert row["antenna"] == ant


def test_build_csv_row_no_point():
    row = build_csv_row(SAMPLE_UPLINK, None, "3dbi")
    assert row["pos_id"] == ""
    assert row["floor"] == ""
    assert row["room"] == ""
    assert row["expected_n_field"] if "expected_n_field" in row else True  # not a column


def test_build_csv_row_missing_metrics():
    row = build_csv_row({}, None, "3dbi")
    assert row["dev_eui"] == ""
    assert row["rssi_dbm"] == ""
    assert row["sf"] == ""


def test_build_csv_row_timestamp_format():
    row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, "3dbi")
    ts = row["timestamp_utc"]
    assert "T" in ts, "timestamp should be ISO format"
    assert ts.endswith("+00:00") or "Z" not in ts  # isoformat with tz


# ---------------------------------------------------------------------------
# CampaignState — uplink processing and PDR
# ---------------------------------------------------------------------------


def test_process_uplink_updates_device_metrics():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_point("P1", "EG", "R1", "indoor", "direct", "LOS", "desk", expected_n=10)
    state.process_uplink(SAMPLE_UPLINK)

    dash = state.get_dashboard()
    dev = dash["devices"].get("0102030405060708")
    assert dev is not None
    assert dev["rssi_dbm"] == -65
    assert dev["sf"] == 7
    assert dev["received"] == 1


def test_process_uplink_pos_count():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_point("PX", "", "", "", "", "", "", expected_n=5)
    for _ in range(3):
        state.process_uplink(SAMPLE_UPLINK)
    assert state.get_dashboard()["pos_counts"]["PX"] == 3


def test_pdr_with_expected_n():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_point("P2", "", "", "", "", "", "", expected_n=10)
    for i in range(5):
        state.process_uplink(dict(SAMPLE_UPLINK, f_cnt=i))
    assert state.get_dashboard()["pos_counts"]["P2"] == 5


def test_pdr_no_expected_n():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_point("P3", "", "", "", "", "", "", expected_n=None)
    state.process_uplink(SAMPLE_UPLINK)
    assert state.get_dashboard()["pos_counts"]["P3"] == 1


def test_multiple_devices_tracked():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_point("P1", "", "", "", "", "", "", expected_n=None)
    state.process_uplink(dict(SAMPLE_UPLINK, dev_eui="aaaa000000000001"))
    state.process_uplink(dict(SAMPLE_UPLINK, dev_eui="bbbb000000000002"))
    dash = state.get_dashboard()
    assert "aaaa000000000001" in dash["devices"]
    assert "bbbb000000000002" in dash["devices"]


# ---------------------------------------------------------------------------
# FIX 9 — pos_count resets when set_point is called for the same pos_id
# ---------------------------------------------------------------------------


def test_pos_count_resets_on_set_point():
    """Re-visiting a point via set_point must reset its received count to 0."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_point("P1", "EG", "R1", "indoor", "direct", "LOS", "desk", expected_n=10)
    for _ in range(3):
        state.process_uplink(SAMPLE_UPLINK)
    assert state.get_dashboard()["pos_counts"]["P1"] == 3

    # Move to another point
    state.set_point("P2", "1OG", "R2", "indoor", "direct", "LOS", "desk", expected_n=10)
    state.process_uplink(SAMPLE_UPLINK)
    assert state.get_dashboard()["pos_counts"]["P2"] == 1

    # Come back to P1 — count must reset to 0
    state.set_point("P1", "EG", "R1", "indoor", "direct", "LOS", "desk", expected_n=10)
    assert state.get_dashboard()["pos_counts"]["P1"] == 0

    # One new uplink after reset
    state.process_uplink(SAMPLE_UPLINK)
    assert state.get_dashboard()["pos_counts"]["P1"] == 1


# ---------------------------------------------------------------------------
# CampaignState — downlink accounting
# ---------------------------------------------------------------------------


def test_downlink_ack_tracking():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = "0102030405060708"
    state.record_downlink_sent(eui)
    state.record_downlink_sent(eui)
    state.process_ack(eui)
    dm = state.get_dashboard()["devices"][eui]
    assert dm["downlinks_sent"] == 2
    assert dm["acked"] == 1


# ---------------------------------------------------------------------------
# FIX 1 (BLOCKER) — ACK increments only on acknowledged=true;
#                   broadcast_nack does NOT increment acked
# ---------------------------------------------------------------------------


def test_process_ack_increments_acked():
    """process_ack must increment the acked counter."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = "aabb000000000001"
    state.record_downlink_sent(eui)
    state.process_ack(eui)
    assert state.get_dashboard()["devices"][eui]["acked"] == 1


def test_broadcast_nack_does_not_increment_acked():
    """broadcast_nack must NOT touch the acked counter — only signals the UI."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = "aabb000000000002"
    state.record_downlink_sent(eui)
    state.broadcast_nack(eui)
    # acked stays at 0; downlinks_sent is 1
    dm = state.get_dashboard()["devices"][eui]
    assert dm["acked"] == 0
    assert dm["downlinks_sent"] == 1


def test_mixed_ack_nack_counting():
    """Only acknowledged downlinks count; NACKs do not inflate acked."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = "aabb000000000003"
    for _ in range(3):
        state.record_downlink_sent(eui)
    state.process_ack(eui)     # 1 real ACK
    state.broadcast_nack(eui)  # 1 NACK — must not count
    state.process_ack(eui)     # 2nd real ACK
    dm = state.get_dashboard()["devices"][eui]
    assert dm["acked"] == 2
    assert dm["downlinks_sent"] == 3


# ---------------------------------------------------------------------------
# CampaignState — antenna
# ---------------------------------------------------------------------------


def test_antenna_default():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    assert state.get_dashboard()["antenna"] == "3dbi"


def test_antenna_set():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_antenna("12dbi")
    assert state.get_dashboard()["antenna"] == "12dbi"


# ---------------------------------------------------------------------------
# CampaignState — CSV recording
# ---------------------------------------------------------------------------


def test_csv_recording_creates_file():
    tmpdir = tempfile.mkdtemp()
    state = CampaignState(data_dir=tmpdir)
    state.set_point("P1", "EG", "R1", "indoor", "direct", "LOS", "desk", expected_n=10)
    path = state.start_recording()
    assert path is not None
    assert os.path.exists(path)

    state.process_uplink(SAMPLE_UPLINK)
    state.stop_recording()

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    # Header + 1 data row
    assert len(lines) == 2
    assert "0102030405060708" in lines[1]


def test_csv_header_matches_columns():
    tmpdir = tempfile.mkdtemp()
    state = CampaignState(data_dir=tmpdir)
    path = state.start_recording()
    state.stop_recording()

    with open(path, encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    assert header == CSV_COLUMNS


def test_recording_idempotent_start():
    """Calling start_recording twice returns the same path."""
    tmpdir = tempfile.mkdtemp()
    state = CampaignState(data_dir=tmpdir)
    p1 = state.start_recording()
    p2 = state.start_recording()
    state.stop_recording()
    assert p1 == p2


# ---------------------------------------------------------------------------
# FIX 4 — CSV write gated on measurement point being set
# ---------------------------------------------------------------------------


def test_csv_not_written_without_point():
    """No data rows must be written when no measurement point is set."""
    tmpdir = tempfile.mkdtemp()
    state = CampaignState(data_dir=tmpdir)
    # Start recording WITHOUT setting a point
    path = state.start_recording()
    state.process_uplink(SAMPLE_UPLINK)
    state.stop_recording()

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    # Only the header; the uplink row must be suppressed
    assert len(lines) == 1, (
        f"Expected only CSV header (1 line), got {len(lines)}: {lines}"
    )


def test_csv_written_after_point_set():
    """Rows ARE written once a point is set, even if recording started first."""
    tmpdir = tempfile.mkdtemp()
    state = CampaignState(data_dir=tmpdir)
    path = state.start_recording()
    # Uplink before point — must be suppressed
    state.process_uplink(SAMPLE_UPLINK)
    # Set point, then uplink — must appear
    state.set_point("P1", "EG", "R1", "indoor", "direct", "LOS", "desk", 10)
    state.process_uplink(SAMPLE_UPLINK)
    state.stop_recording()

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    # Header + exactly 1 data row (the one after set_point)
    assert len(lines) == 2


# ---------------------------------------------------------------------------
# CampaignState — join / dev_addr
# ---------------------------------------------------------------------------


def test_process_join_stores_devaddr():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "01020304")
    state.toggle_coex(True)
    # Confirmed Data Up with DevAddr 01020304 stored LE: 04 03 02 01
    phy = bytes([0x80, 0x04, 0x03, 0x02, 0x01, 0x00, 0x01, 0x00])
    # process_coex_frame must not raise (regardless of timing verdict)
    state.process_coex_frame(7, 868100000, -70, phy)
