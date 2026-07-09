"""test_state.py — unit tests for CampaignState, PointMeta, and build_csv_row.

Runs without grpc or fastapi — only stdlib + local pure modules are imported.
"""
import datetime
import tempfile
import os
import pytest

from app.state import (
    CSV_COLUMNS,
    CampaignState,
    DeviceMetrics,
    PointMeta,
    _median_interval_seconds,
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
# CampaignState — phase / fixed-SF switch
# ---------------------------------------------------------------------------


def test_phase_default():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    assert state.get_dashboard()["phase"] == "adr"


def test_phase_set_sf9():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_phase("sf9")
    assert state.get_dashboard()["phase"] == "sf9"


def test_phase_set_sf12():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_phase("sf12")
    assert state.get_dashboard()["phase"] == "sf12"


def test_phase_roundtrip():
    """Switching phase multiple times always reflects the last value."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    for ph in ("sf9", "sf12", "adr", "sf9"):
        state.set_phase(ph)
    assert state.get_dashboard()["phase"] == "sf9"


def test_phase_in_csv_row():
    """build_csv_row includes the phase field in the output row."""
    row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, "3dbi", "sf12")
    assert row["phase"] == "sf12"


def test_phase_default_in_csv_row():
    """build_csv_row defaults phase to 'adr' when omitted."""
    row = build_csv_row(SAMPLE_UPLINK, SAMPLE_POINT, "3dbi")
    assert row["phase"] == "adr"


def test_phase_written_to_csv():
    """The phase column must appear in a recorded CSV row."""
    tmpdir = tempfile.mkdtemp()
    state = CampaignState(data_dir=tmpdir)
    state.set_point("P1", "EG", "R1", "indoor", "direct", "LOS", "desk", 10)
    state.set_phase("sf9")
    path = state.start_recording()
    state.process_uplink(SAMPLE_UPLINK)
    state.stop_recording()

    import csv as _csv
    with open(path, encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    assert rows[0]["phase"] == "sf9"


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


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" — always-on "Funkumgebung" (coex, Task 1)
# ---------------------------------------------------------------------------


def test_process_coex_frame_without_toggle_still_counts():
    """No toggle_coex(True) call needed anymore — the gateway receives every
    frame in range regardless of any UI toggle, so classification always
    runs."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    phy = bytes([0x40, 0x01, 0x02, 0x03, 0x04, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -70, phy)
    dash = state.get_dashboard()
    assert dash["coex_frames"] == {"ch0_sf7": 1}


def test_coex_active_defaults_true():
    """Reflects the new always-on reality; toggle_coex/is_coex_active are
    kept for API backward-compat but no longer gate anything."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    assert state.get_dashboard()["coex_active"] is True
    assert state.is_coex_active() is True


def test_coex_own_foreign_counts():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "01020304")

    # Own frame: Confirmed Data Up, DevAddr 01020304 stored LE (04 03 02 01)
    own_phy = bytes([0x80, 0x04, 0x03, 0x02, 0x01, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -70, own_phy)

    # Foreign frame: a different DevAddr
    foreign_phy = bytes([0x80, 0xFF, 0xEE, 0xDD, 0xCC, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -70, foreign_phy)

    dash = state.get_dashboard()
    assert dash["coex_own_frames"] == 1
    assert dash["coex_foreign_frames"] == 1
    assert dash["coex_unknown_frames"] == 0


def test_coex_unknown_frames_when_no_known_devaddrs():
    """Without any prior process_join call, ownership cannot be classified
    — the frame must count as unknown, not silently dropped."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    phy = bytes([0x80, 0x04, 0x03, 0x02, 0x01, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -70, phy)
    dash = state.get_dashboard()
    assert dash["coex_unknown_frames"] == 1
    assert dash["coex_own_frames"] == 0
    assert dash["coex_foreign_frames"] == 0


# ---------------------------------------------------------------------------
# F-0006 "Trust & Sichtbarkeit" — device config visibility (Task 2)
# ---------------------------------------------------------------------------


def test_get_device_uplink_stats_unknown_device_returns_nones():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    stats = state.get_device_uplink_stats("0000000000000000")
    assert stats == {
        "last_uplink_at": None,
        "interval_seconds": None,
        "last_downlink_at": None,
    }


def test_get_device_uplink_stats_reflects_last_uplink():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_uplink(SAMPLE_UPLINK)
    stats = state.get_device_uplink_stats(SAMPLE_UPLINK["dev_eui"])
    assert stats["last_uplink_at"] is not None
    assert stats["interval_seconds"] is None  # only one uplink so far


def test_record_downlink_txack_sets_last_downlink_at():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = "aabb000000000009"
    assert state.get_device_uplink_stats(eui)["last_downlink_at"] is None

    state.record_downlink_txack(eui)

    stats = state.get_device_uplink_stats(eui)
    assert stats["last_downlink_at"] is not None
    assert "T" in stats["last_downlink_at"]


def test_record_downlink_txack_does_not_touch_uplink_stats():
    """A downlink-only event must not fabricate an uplink for a device that
    has never sent one."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = "aabb00000000000a"
    state.record_downlink_txack(eui)
    stats = state.get_device_uplink_stats(eui)
    assert stats["last_uplink_at"] is None
    assert stats["last_downlink_at"] is not None


# ---------------------------------------------------------------------------
# _median_interval_seconds — median-of-recent-gaps "Sendeintervall (gemessen)"
# (replaces the old last-two-uplinks-only measurement, which a single missed
# packet could skew, e.g. a steady 5-min device briefly reading as "15 min")
# ---------------------------------------------------------------------------


def _iso_at(base: datetime.datetime, offset_seconds: float) -> str:
    return (base + datetime.timedelta(seconds=offset_seconds)).isoformat()


def test_median_interval_seconds_none_below_two_timestamps():
    assert _median_interval_seconds([]) is None
    assert _median_interval_seconds(["2026-01-01T00:00:00+00:00"]) is None


def test_median_interval_seconds_two_points_is_the_single_gap():
    times = ["2026-01-01T00:00:00+00:00", "2026-01-01T00:05:00+00:00"]
    assert _median_interval_seconds(times) == 300.0


def test_median_interval_seconds_median_over_several_gaps():
    """Six steady 300 s gaps -> median is 300 s."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    times = [_iso_at(base, 300 * i) for i in range(7)]
    assert _median_interval_seconds(times) == 300.0


def test_median_interval_seconds_robust_to_one_outlier_gap():
    """One missed packet doubles a single gap (600 s instead of 300 s) among
    five steady 300 s gaps — the median must stay at 300 s, unlike a plain
    last-two-gap measurement which would read the outlier directly."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    offsets = [0, 300, 600, 1200, 1500, 1800, 2100]  # gaps: 300,300,600,300,300,300
    times = [_iso_at(base, o) for o in offsets]
    assert _median_interval_seconds(times) == 300.0


def test_median_interval_seconds_even_gap_count_averages_middle_two():
    """4 timestamps -> 3 gaps (odd count) is covered above; use 5 timestamps
    -> 4 gaps (even count) to exercise the "average the middle two" branch."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    offsets = [0, 100, 300, 700, 1500]  # gaps: 100, 200, 400, 800 -> median (200+400)/2=300
    times = [_iso_at(base, o) for o in offsets]
    assert _median_interval_seconds(times) == 300.0


def test_median_interval_seconds_ignores_non_positive_gaps():
    """Defensive: an out-of-order/duplicate timestamp (gap <= 0) must not
    crash or be counted — matches the old _interval_seconds' gap > 0 guard."""
    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    times = [_iso_at(base, 0), _iso_at(base, 0), _iso_at(base, 300)]
    assert _median_interval_seconds(times) == 300.0


# ---------------------------------------------------------------------------
# process_uplink / get_dashboard / get_device_uplink_stats integration
# ---------------------------------------------------------------------------


def test_process_uplink_interval_seconds_none_after_first_uplink():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_uplink(SAMPLE_UPLINK)
    dev = state.get_dashboard()["devices"][SAMPLE_UPLINK["dev_eui"]]
    assert dev["interval_seconds"] is None


def test_process_uplink_interval_seconds_reflects_deque_median():
    """Integration: get_dashboard()/get_device_uplink_stats() must compute
    interval_seconds from the SAME retained uplink_times deque that
    process_uplink populates. Seeded with controlled timestamps directly —
    two real-time process_uplink() calls in a fast test run can land within
    the same wall-clock second, which _median_interval_seconds correctly
    treats as a zero gap and ignores (see test_..._ignores_non_positive_gaps
    above), so asserting on real-time gaps here would be flaky."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = SAMPLE_UPLINK["dev_eui"]
    state.process_uplink(SAMPLE_UPLINK)  # creates the DeviceMetrics record

    base = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    dm = state._devices[eui]
    dm.uplink_times.clear()
    dm.uplink_times.extend(_iso_at(base, 300 * i) for i in range(3))

    dev = state.get_dashboard()["devices"][eui]
    assert dev["interval_seconds"] == 300.0

    stats = state.get_device_uplink_stats(eui)
    assert stats["interval_seconds"] == 300.0


def test_process_uplink_uplink_times_capped_at_history_length():
    """The retained timestamp history must stay bounded (maxlen) even after
    many more uplinks than that — "a small bounded history"."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    eui = SAMPLE_UPLINK["dev_eui"]
    for _ in range(10):
        state.process_uplink(SAMPLE_UPLINK)
    dm = state._devices[eui]
    assert len(dm.uplink_times) == 7


# ---------------------------------------------------------------------------
# RF-environment survey (F-0006) — get_rf_environment() / _record_rf_environment_frame
# ---------------------------------------------------------------------------


def test_get_rf_environment_empty_initially():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    env = state.get_rf_environment()
    assert env["foreign_devices"] == {}
    assert env["networks"] == {}
    assert env["vendors"] == {}
    assert env["mtype_counts"] == {"join": 0, "data_up": 0, "data_down": 0, "other": 0}
    assert env["channel_sf_matrix"] == {}
    assert env["frames_per_min"] == 0.0
    assert env["frames_per_min_sparkline"] == [0] * 10
    assert env["own_frames"] == 0
    assert env["foreign_frames"] == 0


def test_process_coex_frame_foreign_data_frame_updates_foreign_devices():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "01020304")  # our own device -> known_addrs non-empty

    # Foreign data frame: DevAddr LE bytes [aa,bb,cc,26] -> BE "26ccbbaa", top byte
    # 0x26 -> The Things Network. Different from our own DevAddr 01020304.
    foreign_phy = bytes([0x40, 0xaa, 0xbb, 0xcc, 0x26, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -80, foreign_phy, -5.0)

    env = state.get_rf_environment()
    assert len(env["foreign_devices"]) == 1
    dev_addr = next(iter(env["foreign_devices"]))
    assert dev_addr == "26ccbbaa"
    entry = env["foreign_devices"][dev_addr]
    assert entry["frames"] == 1
    assert entry["last_rssi"] == -80
    assert entry["last_snr"] == -5.0
    assert entry["last_sf"] == 7
    assert entry["last_channel"] == 0
    assert entry["network"] == "The Things Network"

    assert env["networks"] == {"The Things Network": {"devices": 1, "frames": 1}}
    assert env["channel_sf_matrix"] == {"ch0_sf7": 1}
    assert env["mtype_counts"]["data_up"] == 1


def test_process_coex_frame_snr_defaults_to_none():
    """snr is optional — existing callers/tests that predate the RF-
    environment survey must keep working unchanged."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "01020304")
    foreign_phy = bytes([0x40, 0xaa, 0xbb, 0xcc, 0x26, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -80, foreign_phy)  # no snr arg

    env = state.get_rf_environment()
    dev_addr = next(iter(env["foreign_devices"]))
    assert env["foreign_devices"][dev_addr]["last_snr"] is None


def test_process_coex_frame_own_data_frame_not_added_to_foreign_devices():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "01020304")
    # Confirmed Data Up with DevAddr 01020304 stored LE: 04 03 02 01 — ours.
    own_phy = bytes([0x80, 0x04, 0x03, 0x02, 0x01, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -70, own_phy)

    env = state.get_rf_environment()
    assert env["foreign_devices"] == {}
    assert env["networks"] == {}


def test_process_coex_frame_unclassifiable_data_frame_not_added_to_foreign_devices():
    """Without ANY known own DevAddr yet, ownership can't be ruled out —
    conservative: not counted as foreign either (mirrors _coex_unknown_frames)."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    phy = bytes([0x40, 0xaa, 0xbb, 0xcc, 0x26, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -80, phy)

    env = state.get_rf_environment()
    assert env["foreign_devices"] == {}
    assert env["mtype_counts"]["data_up"] == 1  # MType tally still happens regardless


def test_process_coex_frame_join_request_updates_vendors():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    join_eui_le = bytes(8)
    dev_eui_be = "a84041aabbccddee"  # OUI a84041 -> Dragino
    dev_eui_le = bytes.fromhex(dev_eui_be)[::-1]
    phy = bytes([0x00]) + join_eui_le + dev_eui_le + bytes([0x00, 0x01]) + bytes(4)
    assert len(phy) == 23

    state.process_coex_frame(7, 868100000, -90, phy)

    env = state.get_rf_environment()
    assert env["mtype_counts"]["join"] == 1
    assert env["vendors"] == {"a84041": {"name": "Dragino", "joins": 1}}


def test_process_coex_frame_own_join_request_excluded_from_vendors():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    dev_eui_be = "aabbccdd00000001"
    state.process_join(dev_eui_be, "01020304")  # register as one of OUR devices

    join_eui_le = bytes(8)
    dev_eui_le = bytes.fromhex(dev_eui_be)[::-1]
    phy = bytes([0x00]) + join_eui_le + dev_eui_le + bytes([0x00, 0x01]) + bytes(4)

    state.process_coex_frame(7, 868100000, -90, phy)

    env = state.get_rf_environment()
    assert env["vendors"] == {}
    assert env["mtype_counts"]["join"] == 1  # still counted in the overall tally


def test_process_coex_frame_malformed_join_request_does_not_crash():
    """A join-request MType with a truncated payload must not raise —
    parse_join_request returns None, mtype_counts still increments."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    short_phy = bytes([0x00, 0x01, 0x02])  # MType 0, but far too short to parse

    state.process_coex_frame(7, 868100000, -90, short_phy)  # must not raise

    env = state.get_rf_environment()
    assert env["mtype_counts"]["join"] == 1
    assert env["vendors"] == {}


def test_foreign_devices_bounded_evicts_oldest(monkeypatch):
    from app import state as state_mod
    monkeypatch.setattr(state_mod, "_MAX_FOREIGN_DEVICES", 3)

    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "ffffffff")  # own device, distinct from all test DevAddrs

    for i in range(5):
        phy = bytes([0x40, i, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00])
        state.process_coex_frame(7, 868100000, -80, phy)

    env = state.get_rf_environment()
    assert len(env["foreign_devices"]) == 3


def test_vendors_bounded_evicts_oldest(monkeypatch):
    from app import state as state_mod
    monkeypatch.setattr(state_mod, "_MAX_VENDORS", 2)

    state = CampaignState(data_dir=tempfile.mkdtemp())
    join_eui_le = bytes(8)
    for i in range(4):
        dev_eui_be = f"{i:02x}0000aabbccddee"
        dev_eui_le = bytes.fromhex(dev_eui_be)[::-1]
        phy = bytes([0x00]) + join_eui_le + dev_eui_le + bytes([0x00, 0x01]) + bytes(4)
        state.process_coex_frame(7, 868100000, -90, phy)

    env = state.get_rf_environment()
    assert len(env["vendors"]) == 2


def test_frames_per_min_and_sparkline_reflect_recent_foreign_frames():
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "ffffffff")
    for i in range(3):
        phy = bytes([0x40, i, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00])
        state.process_coex_frame(7, 868100000, -80, phy)

    env = state.get_rf_environment()
    assert env["frames_per_min"] > 0
    assert len(env["frames_per_min_sparkline"]) == 10
    assert sum(env["frames_per_min_sparkline"]) == 3
    assert env["frames_per_min_sparkline"][-1] == 3  # all just happened -> most-recent bucket


def test_get_rf_environment_own_foreign_totals_match_coex_counters():
    """own_frames/foreign_frames in the survey snapshot must be the SAME
    totals already exposed via get_dashboard()'s coex_own_frames/
    coex_foreign_frames — one source of truth, no drift."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.process_join("aabbccdd00000001", "01020304")
    own_phy = bytes([0x80, 0x04, 0x03, 0x02, 0x01, 0x00, 0x01, 0x00])
    foreign_phy = bytes([0x40, 0xaa, 0xbb, 0xcc, 0x26, 0x00, 0x01, 0x00])
    state.process_coex_frame(7, 868100000, -70, own_phy)
    state.process_coex_frame(7, 868100000, -80, foreign_phy)

    env = state.get_rf_environment()
    dash = state.get_dashboard()
    assert env["own_frames"] == dash["coex_own_frames"] == 1
    assert env["foreign_frames"] == dash["coex_foreign_frames"] == 1
