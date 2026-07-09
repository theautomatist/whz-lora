"""scheduler.py — F-0006 Phase B: timed per-device SF-sweep runs.

Pure decision/derivation logic lives here (evaluate_run_schedule,
run_summary_fields, default_sf_schedule, parse_iso, parse_schedule) so it
is unit-testable without an asyncio loop, a database or a gRPC channel.
The async polling loop + ChirpStack/DB glue lives in main.py's
lifespan-managed background task, which calls into this module.

No external imports beyond stdlib — importable without grpc/fastapi.
"""
import datetime
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DURATION_SECONDS = 86400   # 24 h
DEFAULT_INTERVAL_MINUTES = 5
DEFAULT_SF_ORDER = (7, 9, 12)

# How often the background scheduler loop checks all running sweeps.
POLL_INTERVAL_SECONDS = 60


def default_sf_schedule(duration_seconds: int) -> list[dict]:
    """Split *duration_seconds* evenly across SF7 -> SF9 -> SF12.

    The remainder of the integer division goes to the last segment so the
    three segments always sum to exactly duration_seconds.
    """
    third = duration_seconds // 3
    remainder = duration_seconds - 2 * third
    return [
        {"sf": 7, "seconds": third},
        {"sf": 9, "seconds": third},
        {"sf": 12, "seconds": remainder},
    ]


def parse_iso(value: Optional[str]) -> Optional[datetime.datetime]:
    """Parse an ISO-8601 timestamp (as written by db.py's _now()). None-safe."""
    if not value:
        return None
    return datetime.datetime.fromisoformat(value)


def parse_schedule(raw: Optional[str]) -> list[dict]:
    """Decode the run.sf_schedule JSON TEXT column. Empty/None/invalid -> []."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Could not parse sf_schedule JSON: %r", raw)
        return []


def evaluate_run_schedule(
    now: datetime.datetime,
    started_at: datetime.datetime,
    segment_started_at: datetime.datetime,
    segment_index: int,
    schedule: list[dict],
    planned_seconds: Optional[int],
) -> dict:
    """Pure decision for one scheduler tick on one sweep run.

    Returns {"advance": bool, "next_index": Optional[int], "done": bool}:
      - done=True     the run's planned duration has elapsed, or the
                       current (last) segment has elapsed and there is no
                       next segment — the run should be marked
                       status='done', ended_at=now.
      - advance=True   the current segment has elapsed and a next segment
                       exists; next_index is the segment_index to switch to
                       (its SF profile should be applied to the device).
      - both False     nothing to do yet on this tick.

    *schedule* empty/None means "no sweep" (a Phase A fixed run) — always
    returns the all-False/not-done no-op result; the caller should skip
    such runs entirely.
    """
    if not schedule:
        return {"advance": False, "next_index": None, "done": False}

    if planned_seconds is not None:
        elapsed_total = (now - started_at).total_seconds()
        if elapsed_total >= planned_seconds:
            return {"advance": False, "next_index": None, "done": True}

    if segment_index < 0 or segment_index >= len(schedule):
        # Defensive: an out-of-range index (e.g. corrupted/edited data)
        # can't be advanced further — treat the sweep as finished.
        return {"advance": False, "next_index": None, "done": True}

    current = schedule[segment_index]
    elapsed_seg = (now - segment_started_at).total_seconds()
    if elapsed_seg >= current.get("seconds", 0):
        next_index = segment_index + 1
        if next_index < len(schedule):
            return {"advance": True, "next_index": next_index, "done": False}
        return {"advance": False, "next_index": None, "done": True}

    return {"advance": False, "next_index": None, "done": False}


def run_summary_fields(run: dict, now: Optional[datetime.datetime] = None) -> dict:
    """Derive planned_seconds/elapsed_seconds/current_sf/segment_index/
    progress/sf_schedule/done for a run row.

    Works for both sweep runs (sf_schedule set) and Phase A fixed runs
    (sf_schedule NULL) — the latter get current_sf=None, progress=None,
    sf_schedule=[], and done=(status != 'running').

    For a run that is no longer 'running', elapsed/progress are frozen at
    ended_at rather than growing against the caller's *now* — a finished
    run's progress bar should not keep moving in the run history.
    """
    schedule = parse_schedule(run.get("sf_schedule"))
    started_at = parse_iso(run.get("started_at"))
    planned_seconds = run.get("planned_seconds")
    segment_index = run.get("segment_index") or 0

    if run.get("status") == "running":
        reference = now or datetime.datetime.now(datetime.timezone.utc)
    else:
        reference = parse_iso(run.get("ended_at")) or now or datetime.datetime.now(
            datetime.timezone.utc
        )

    elapsed_seconds = None
    if started_at is not None:
        elapsed_seconds = max(0, int((reference - started_at).total_seconds()))

    current_sf = None
    if schedule and 0 <= segment_index < len(schedule):
        current_sf = schedule[segment_index]["sf"]

    progress = None
    if planned_seconds and elapsed_seconds is not None:
        progress = max(0.0, min(1.0, elapsed_seconds / planned_seconds))

    return {
        "planned_seconds": planned_seconds,
        "elapsed_seconds": elapsed_seconds,
        "current_sf": current_sf,
        "segment_index": segment_index if schedule else None,
        "progress": progress,
        "sf_schedule": schedule,
        "done": run.get("status") != "running",
    }
