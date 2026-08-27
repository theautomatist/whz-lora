"""test_run_stats_golden.py — golden test pinning `_compute_run_stats`'s
current per-SF PDR/RSSI/SNR aggregation to exact numbers (spec §16 Stage 0:
"a golden test pinning _compute_run_stats to today's exact numbers, so the
aggregate change is provably identical"). Stage 3 moves this computation
onto stored counters (`rssi_n`/`snr_n`, reconciled at stop_run) instead of
re-reading the CSV on every request — this test is the proof the numbers
must not move when that happens.

The fixture CSV (`fixtures/golden_run_stats.csv`, checked in, 9 data rows)
deliberately carries the two real-data quirks the spec calls out:
multiple SF segments (three, back-to-back — SF7/SF9/SF12), and at least one
row with an empty rssi_dbm/snr_db pair (row 3, an uplink whose rxInfo was
empty at ingest time — see ingest.py:49-50) that must be excluded from the
rssi_avg/snr_avg averages but still counted in `received`.

Expected numbers below are the *actual* output of today's
`_compute_run_stats` against that fixture (verified by running it, not
hand-derived) — this file only asserts them, so a silent change in the
aggregation shows up as a diff here.
"""
import json
import os

from app import main

_FIXTURE_CSV = os.path.join(os.path.dirname(__file__), "fixtures", "golden_run_stats.csv")

_SCHEDULE = json.dumps([
    {"sf": 7, "seconds": 3600},
    {"sf": 9, "seconds": 3600},
    {"sf": 12, "seconds": 3600},
])

_DL_COUNTS = json.dumps({
    "by_sf": {
        "7": {"sent": 5, "acked": 4},
        "9": {"sent": 3, "acked": 3},
        "12": {"sent": 2, "acked": 1},
    },
    "pending_sf": None,
})


def _sweep_run(**overrides) -> dict:
    run = {
        "sf_schedule": _SCHEDULE,
        "started_at": "2026-07-08T09:00:00+00:00",
        "interval_minutes": 5,
        "csv_path": _FIXTURE_CSV,
        "dl_counts": _DL_COUNTS,
        "status": "done",
        "ended_at": "2026-07-08T11:30:00+00:00",  # 9000 s after started_at
    }
    run.update(overrides)
    return run


def test_golden_sweep_run_per_sf_stats_are_pinned():
    """SF7/SF9/SF12 segments, each 3600 s, interval_minutes=5 (300 s/slot),
    run ended 9000 s after start: SF7 and SF9 each get their full 3600 s
    (expected=12), SF12 only got 1800 s of the 9000 s elapsed before the
    run ended (expected=6)."""
    stats = main._compute_run_stats(_sweep_run())

    assert stats["sf_stats"] == [
        {
            "sf": 7, "expected": 12, "received": 4, "pdr": 0.3333,
            "rssi_avg": -84.7, "snr_avg": 2.3,
            "dl_sent": 5, "dl_acked": 4, "dl_pdr": 0.8,
        },
        {
            "sf": 9, "expected": 12, "received": 3, "pdr": 0.25,
            "rssi_avg": -97.0, "snr_avg": -6.2,
            "dl_sent": 3, "dl_acked": 3, "dl_pdr": 1.0,
        },
        {
            "sf": 12, "expected": 6, "received": 2, "pdr": 0.3333,
            "rssi_avg": -109.0, "snr_avg": -11.5,
            "dl_sent": 2, "dl_acked": 1, "dl_pdr": 0.5,
        },
    ]


def test_golden_sweep_run_overall_stats_are_pinned():
    """9 received rows total (one has an empty rssi/snr pair, still
    counted here) against 30 expected across all three segments."""
    stats = main._compute_run_stats(_sweep_run())

    assert stats["overall"] == {
        "sf": None, "expected": 30, "received": 9, "pdr": 0.3,
        "rssi_avg": -95.4, "snr_avg": -4.3,
        "dl_sent": 10, "dl_acked": 8, "dl_pdr": 0.8,
    }


def test_golden_sweep_run_excludes_the_empty_rssi_snr_row_from_averages():
    """Row 3 (09:25:00, SF7 segment) has empty rssi_dbm/snr_db — the exact
    case ingest.py writes when rxInfo is empty. It must still count toward
    `received` (4 rows in the SF7 segment) but be excluded from
    rssi_avg/snr_avg (averaged over the other 3 SF7 rows only)."""
    stats = main._compute_run_stats(_sweep_run())
    sf7 = stats["sf_stats"][0]
    assert sf7["received"] == 4  # all four SF7 rows, including the empty one
    assert sf7["rssi_avg"] == -84.7  # avg(-80, -84, -90) — the empty row excluded
    assert sf7["snr_avg"] == 2.3     # avg(5.0, 3.0, -1.0) — the empty row excluded


def test_golden_phase_a_fixed_run_has_no_sf_segments():
    """A Phase A fixed run (no sf_schedule/interval_minutes) takes the
    other branch entirely: no per-SF breakdown, no "expected" concept —
    just an overall row over every CSV row."""
    run = _sweep_run(sf_schedule=None, interval_minutes=None, dl_counts=None)
    stats = main._compute_run_stats(run)

    assert stats["sf_stats"] == []
    assert stats["overall"] == {
        "sf": None, "expected": None, "received": 9, "pdr": None,
        "rssi_avg": -95.4, "snr_avg": -4.3,
        "dl_sent": 0, "dl_acked": 0, "dl_pdr": None,
    }
