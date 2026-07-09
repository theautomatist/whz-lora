"""test_scheduler.py — unit tests for the pure Phase B SF-sweep decision
logic in scheduler.py (evaluate_run_schedule, run_summary_fields,
default_sf_schedule, parse_iso, parse_schedule).

No database, no gRPC, no asyncio loop — everything here is pure functions
over plain dicts/datetimes.
"""
import datetime

from app import scheduler

UTC = datetime.timezone.utc


def _dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s)


SCHEDULE = [
    {"sf": 7, "seconds": 100},
    {"sf": 9, "seconds": 100},
    {"sf": 12, "seconds": 100},
]

# ---------------------------------------------------------------------------
# default_sf_schedule
# ---------------------------------------------------------------------------


def test_default_sf_schedule_splits_evenly():
    sched = scheduler.default_sf_schedule(300)
    assert sched == [
        {"sf": 7, "seconds": 100},
        {"sf": 9, "seconds": 100},
        {"sf": 12, "seconds": 100},
    ]


def test_default_sf_schedule_remainder_goes_to_last_segment():
    sched = scheduler.default_sf_schedule(100)  # 100 // 3 == 33, remainder 34
    assert [s["sf"] for s in sched] == [7, 9, 12]
    assert sched[0]["seconds"] == 33
    assert sched[1]["seconds"] == 33
    assert sched[2]["seconds"] == 34
    assert sum(s["seconds"] for s in sched) == 100


def test_default_sf_schedule_24h():
    sched = scheduler.default_sf_schedule(86400)
    assert sum(s["seconds"] for s in sched) == 86400
    assert sched[0]["seconds"] == 28800  # 8 h


# ---------------------------------------------------------------------------
# parse_iso / parse_schedule
# ---------------------------------------------------------------------------


def test_parse_iso_none():
    assert scheduler.parse_iso(None) is None
    assert scheduler.parse_iso("") is None


def test_parse_iso_roundtrip():
    now = datetime.datetime.now(UTC).isoformat(timespec="seconds")
    parsed = scheduler.parse_iso(now)
    assert parsed.isoformat(timespec="seconds") == now


def test_parse_schedule_none_or_empty():
    assert scheduler.parse_schedule(None) == []
    assert scheduler.parse_schedule("") == []


def test_parse_schedule_valid_json():
    raw = '[{"sf": 7, "seconds": 100}]'
    assert scheduler.parse_schedule(raw) == [{"sf": 7, "seconds": 100}]


def test_parse_schedule_invalid_json_returns_empty():
    assert scheduler.parse_schedule("{not json") == []


# ---------------------------------------------------------------------------
# evaluate_run_schedule — no schedule (Phase A passthrough)
# ---------------------------------------------------------------------------


def test_evaluate_no_schedule_is_noop():
    now = _dt("2026-01-01T12:00:00+00:00")
    result = scheduler.evaluate_run_schedule(now, now, now, 0, [], None)
    assert result == {"advance": False, "next_index": None, "done": False}


def test_evaluate_empty_schedule_list_is_noop():
    now = _dt("2026-01-01T12:00:00+00:00")
    started = _dt("2026-01-01T10:00:00+00:00")
    result = scheduler.evaluate_run_schedule(now, started, started, 0, None, 300)
    assert result["advance"] is False
    assert result["done"] is False


# ---------------------------------------------------------------------------
# evaluate_run_schedule — segment advance at the boundary
# ---------------------------------------------------------------------------


def test_evaluate_before_segment_boundary_no_change():
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=50)  # segment 0 needs 100 s
    result = scheduler.evaluate_run_schedule(now, started, started, 0, SCHEDULE, 300)
    assert result == {"advance": False, "next_index": None, "done": False}


def test_evaluate_exactly_at_segment_boundary_advances():
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=100)  # exactly the segment length
    result = scheduler.evaluate_run_schedule(now, started, started, 0, SCHEDULE, 300)
    assert result == {"advance": True, "next_index": 1, "done": False}


def test_evaluate_past_segment_boundary_advances():
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=150)
    result = scheduler.evaluate_run_schedule(now, started, started, 0, SCHEDULE, 300)
    assert result["advance"] is True
    assert result["next_index"] == 1


def test_evaluate_advance_uses_segment_started_at_not_run_started_at():
    """elapsed_seg must be measured from segment_started_at (the segment's
    own start), not from the run's overall started_at."""
    started = _dt("2026-01-01T12:00:00+00:00")
    segment_started = _dt("2026-01-01T13:30:00+00:00")  # already in segment 1
    now = segment_started + datetime.timedelta(seconds=100)  # segment 1 (index 1) done
    # planned_seconds large enough that the overall-duration check (elapsed
    # since *started*, ~5500 s here) doesn't fire first.
    result = scheduler.evaluate_run_schedule(now, started, segment_started, 1, SCHEDULE, 100_000)
    assert result == {"advance": True, "next_index": 2, "done": False}


def test_evaluate_last_segment_elapsed_marks_done_not_advance():
    started = _dt("2026-01-01T12:00:00+00:00")
    segment_started = _dt("2026-01-01T14:00:00+00:00")  # segment 2 (last, index 2)
    now = segment_started + datetime.timedelta(seconds=100)
    # planned_seconds large enough that this exercises the "no next segment"
    # branch specifically, not the overall-duration-elapsed branch.
    result = scheduler.evaluate_run_schedule(now, started, segment_started, 2, SCHEDULE, 100_000)
    assert result == {"advance": False, "next_index": None, "done": True}


# ---------------------------------------------------------------------------
# evaluate_run_schedule — overall done via planned_seconds
# ---------------------------------------------------------------------------


def test_evaluate_done_when_planned_seconds_elapsed():
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=300)  # == planned_seconds
    result = scheduler.evaluate_run_schedule(now, started, started, 0, SCHEDULE, 300)
    assert result == {"advance": False, "next_index": None, "done": True}


def test_evaluate_done_overrides_pending_segment_advance():
    """planned_seconds elapsed takes priority even if the current segment
    itself hasn't technically finished (e.g. duration_seconds was shortened
    after the schedule was built)."""
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=250)
    result = scheduler.evaluate_run_schedule(now, started, started, 0, SCHEDULE, 250)
    assert result["done"] is True
    assert result["advance"] is False


def test_evaluate_no_planned_seconds_only_segment_logic_applies():
    """planned_seconds=None means never force-done via the overall clock —
    only per-segment / end-of-schedule logic decides."""
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=10_000)  # way past any segment
    result = scheduler.evaluate_run_schedule(now, started, started, 0, SCHEDULE, None)
    # Segment 0 (100 s) is long elapsed -> advances to segment 1 first.
    assert result == {"advance": True, "next_index": 1, "done": False}


def test_evaluate_out_of_range_segment_index_is_done():
    started = _dt("2026-01-01T12:00:00+00:00")
    now = started + datetime.timedelta(seconds=10)
    result = scheduler.evaluate_run_schedule(now, started, started, 99, SCHEDULE, None)
    assert result == {"advance": False, "next_index": None, "done": True}


# ---------------------------------------------------------------------------
# run_summary_fields
# ---------------------------------------------------------------------------


def test_run_summary_no_sweep_run():
    run = {
        "status": "running",
        "started_at": "2026-01-01T12:00:00+00:00",
        "ended_at": None,
        "planned_seconds": None,
        "sf_schedule": None,
        "segment_index": 0,
    }
    now = _dt("2026-01-01T12:05:00+00:00")
    summary = scheduler.run_summary_fields(run, now=now)
    assert summary["planned_seconds"] is None
    assert summary["current_sf"] is None
    assert summary["segment_index"] is None
    assert summary["progress"] is None
    assert summary["sf_schedule"] == []
    assert summary["done"] is False
    assert summary["elapsed_seconds"] == 300


def test_run_summary_running_sweep_progress():
    run = {
        "status": "running",
        "started_at": "2026-01-01T12:00:00+00:00",
        "ended_at": None,
        "planned_seconds": 300,
        "sf_schedule": '[{"sf":7,"seconds":100},{"sf":9,"seconds":100},{"sf":12,"seconds":100}]',
        "segment_index": 1,
    }
    now = _dt("2026-01-01T12:02:30+00:00")  # 150 s elapsed
    summary = scheduler.run_summary_fields(run, now=now)
    assert summary["elapsed_seconds"] == 150
    assert summary["progress"] == 0.5
    assert summary["current_sf"] == 9
    assert summary["segment_index"] == 1
    assert summary["done"] is False


def test_run_summary_progress_clamped_to_one():
    run = {
        "status": "running",
        "started_at": "2026-01-01T12:00:00+00:00",
        "ended_at": None,
        "planned_seconds": 100,
        "sf_schedule": None,
        "segment_index": 0,
    }
    now = _dt("2026-01-01T13:00:00+00:00")  # way past planned_seconds
    summary = scheduler.run_summary_fields(run, now=now)
    assert summary["progress"] == 1.0


def test_run_summary_done_run_frozen_at_ended_at():
    """A finished run's elapsed/progress must not keep growing against a
    later 'now' — they freeze at ended_at."""
    run = {
        "status": "done",
        "started_at": "2026-01-01T12:00:00+00:00",
        "ended_at": "2026-01-01T12:05:00+00:00",  # 300 s run
        "planned_seconds": 300,
        "sf_schedule": None,
        "segment_index": 0,
    }
    much_later = _dt("2026-01-02T12:00:00+00:00")
    summary = scheduler.run_summary_fields(run, now=much_later)
    assert summary["elapsed_seconds"] == 300
    assert summary["progress"] == 1.0
    assert summary["done"] is True


def test_run_summary_done_true_for_aborted():
    run = {
        "status": "aborted",
        "started_at": "2026-01-01T12:00:00+00:00",
        "ended_at": "2026-01-01T12:01:00+00:00",
        "planned_seconds": None,
        "sf_schedule": None,
        "segment_index": 0,
    }
    summary = scheduler.run_summary_fields(run)
    assert summary["done"] is True


def test_run_summary_current_sf_last_segment_when_schedule_complete():
    run = {
        "status": "done",
        "started_at": "2026-01-01T12:00:00+00:00",
        "ended_at": "2026-01-01T15:00:00+00:00",
        "planned_seconds": 300,
        "sf_schedule": '[{"sf":7,"seconds":100},{"sf":9,"seconds":100},{"sf":12,"seconds":100}]',
        "segment_index": 2,
    }
    summary = scheduler.run_summary_fields(run)
    assert summary["current_sf"] == 12
    assert summary["done"] is True
