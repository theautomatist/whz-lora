"""test_migration.py — schema migration against a synthetic legacy database
with the same id-gap pattern as the real field data.

Per docs/developer/design/cockpit-redesign-spec.md §15: the real
`cockpit-data/cockpit.db` has `placement` starting at id 7, `run` at id 4,
`photo` at id 2, with `sqlite_sequence` higher still — rows were deleted
outside the application (SQLite's AUTOINCREMENT never reuses an id once
used, deleted or not), the files stayed, nothing was actually lost. This
file builds a from-scratch database with that same gap shape (pre-Phase-B,
pre-F-0008 schema — no sf_schedule/segment_index/floorplan_id/map_x/map_y
columns) and checks that today's `Database.init_schema()` — the additive
`_migrate_run_columns`/`_migrate_placement_columns` guarded ALTER TABLEs —
runs cleanly against it, is idempotent, and loses nothing. This is the
scaffold Stage 1's own (event-table) migration builds on.

Existing, narrower coverage of the same migration functions already lives
in test_db.py (`test_migration_adds_missing_columns_to_existing_db`,
`test_init_schema_migration_is_idempotent`) against a *contiguous*,
gap-free legacy schema; this file adds the id-gap dimension specifically.

Stage 1 (event table) additions below: the id-gap fixture above doubles as
the "one still-running run" backfill case (only run_started, no
run_stopped, node/run ids from the same fixture), and a second fixture
(`_build_legacy_db_with_seven_finished_runs`) mirrors the shape of the real
7-run snapshot (6x reason='schedule-complete' + 1x NULL, all finished) to
pin the backfill's exact output — see docs/developer/design/
cockpit-redesign-spec.md §15.
"""
import json
import sqlite3

import pytest

from app.db import Database

# Deliberately the pre-Phase-B / pre-F-0008 table shapes (no
# planned_seconds/sf_schedule/interval_minutes/segment_index/
# segment_started_at/downlink_test/dl_counts on `run`; no
# floorplan_id/map_x/map_y on `placement`) — everything init_schema()'s
# migrations are supposed to add on top, guarded and no-op once present.
_LEGACY_SCHEMA = """
CREATE TABLE node (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    eui        TEXT UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE placement (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id      INTEGER NOT NULL REFERENCES node(id),
    floor        TEXT NOT NULL DEFAULT '',
    room         TEXT NOT NULL DEFAULT '',
    description  TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    antenna      TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    ended_at     TEXT
);

CREATE TABLE photo (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    placement_id INTEGER NOT NULL REFERENCES placement(id),
    filename     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE run (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    device_node_id        INTEGER NOT NULL REFERENCES node(id),
    device_placement_id   INTEGER NOT NULL REFERENCES placement(id),
    gateway_placement_id  INTEGER NOT NULL REFERENCES placement(id),
    phase                 TEXT NOT NULL,
    csv_path              TEXT NOT NULL DEFAULT '',
    started_at            TEXT NOT NULL,
    ended_at              TEXT,
    status                TEXT NOT NULL,
    reason                TEXT,
    packets               INTEGER NOT NULL DEFAULT 0
);
"""


def _build_legacy_db(path: str) -> None:
    """Create a pre-Phase-B/pre-F-0008 database with the same id-gap
    pattern seen in the real field data: early rows deleted (placement
    from 7, run from 4, photo from 2) *and* a later row also inserted and
    deleted at each table's top end, so `sqlite_sequence` sits strictly
    higher than any surviving id — not just equal to the last one, mirroring
    §15's "sqlite_sequence steht höher als die vorhandenen IDs"."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_LEGACY_SCHEMA)

    conn.execute(
        "INSERT INTO node (id, kind, name, eui, created_at) VALUES "
        "(1, 'gateway', 'whz-kerlink-ifevo', '7076ff0064071a3d', "
        "'2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO node (id, kind, name, eui, created_at) VALUES "
        "(2, 'device', 'thermostat-katia', '0011223344556677', "
        "'2026-01-01T00:00:00+00:00')"
    )

    # placement: dummy 1-6 (deleted), real 7 (gateway) + 8 (device, active),
    # dummy 9 (deleted) — surviving ids are {7, 8}, sequence ends at 9.
    for i in range(1, 7):
        conn.execute(
            "INSERT INTO placement (id, node_id, started_at, ended_at) "
            "VALUES (?, 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01+00:00')",
            (i,),
        )
    conn.execute("DELETE FROM placement WHERE id BETWEEN 1 AND 6")
    conn.execute(
        "INSERT INTO placement (id, node_id, floor, room, started_at, ended_at) "
        "VALUES (7, 1, '0', '', '2026-07-08T09:00:00+00:00', NULL)"
    )
    conn.execute(
        "INSERT INTO placement (id, node_id, floor, room, started_at, ended_at) "
        "VALUES (8, 2, '3', '', '2026-07-23T10:00:00+00:00', NULL)"
    )
    conn.execute(
        "INSERT INTO placement (id, node_id, started_at, ended_at) "
        "VALUES (9, 1, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:01+00:00')"
    )
    conn.execute("DELETE FROM placement WHERE id = 9")

    # run: dummy 1-3 (deleted), real 4 (running, survives), dummy 5 (deleted)
    for i in range(1, 4):
        conn.execute(
            "INSERT INTO run (id, device_node_id, device_placement_id, "
            "gateway_placement_id, phase, started_at, status, packets) "
            "VALUES (?, 2, 8, 7, 'adr', '2026-01-01T00:00:00+00:00', 'aborted', 0)",
            (i,),
        )
    conn.execute("DELETE FROM run WHERE id BETWEEN 1 AND 3")
    conn.execute(
        "INSERT INTO run (id, device_node_id, device_placement_id, "
        "gateway_placement_id, phase, started_at, status, packets) "
        "VALUES (4, 2, 8, 7, 'adr', '2026-07-23T10:05:00+00:00', 'running', 0)"
    )
    conn.execute(
        "INSERT INTO run (id, device_node_id, device_placement_id, "
        "gateway_placement_id, phase, started_at, status, packets) "
        "VALUES (5, 2, 8, 7, 'adr', '2026-01-01T00:00:00+00:00', 'aborted', 0)"
    )
    conn.execute("DELETE FROM run WHERE id = 5")

    # photo: dummy 1 (deleted), real 2 (survives), dummy 3 (deleted)
    conn.execute(
        "INSERT INTO photo (id, placement_id, filename, created_at) "
        "VALUES (1, 8, 'dummy.jpg', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute("DELETE FROM photo WHERE id = 1")
    conn.execute(
        "INSERT INTO photo (id, placement_id, filename, created_at) "
        "VALUES (2, 8, '1.jpg', '2026-07-23T10:01:00+00:00')"
    )
    conn.execute(
        "INSERT INTO photo (id, placement_id, filename, created_at) "
        "VALUES (3, 8, 'dummy.jpg', '2026-01-01T00:00:00+00:00')"
    )
    conn.execute("DELETE FROM photo WHERE id = 3")

    conn.commit()
    conn.close()


def _sequence(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
    ).fetchone()
    return row[0] if row else 0


@pytest.fixture
def legacy_db_path(tmp_path) -> str:
    path = str(tmp_path / "legacy.db")
    _build_legacy_db(path)
    return path


def test_legacy_fixture_has_the_expected_gap_pattern(legacy_db_path):
    """Sanity-check the fixture itself before trusting the migration
    assertions built on top of it — mirrors the real snapshot's shape."""
    conn = sqlite3.connect(legacy_db_path)
    try:
        assert [r[0] for r in conn.execute("SELECT id FROM placement ORDER BY id")] == [7, 8]
        assert [r[0] for r in conn.execute("SELECT id FROM run ORDER BY id")] == [4]
        assert [r[0] for r in conn.execute("SELECT id FROM photo ORDER BY id")] == [2]
        assert _sequence(conn, "placement") > 8
        assert _sequence(conn, "run") > 4
        assert _sequence(conn, "photo") > 2
    finally:
        conn.close()


def test_init_schema_migrates_legacy_db_without_raising(legacy_db_path):
    db = Database(legacy_db_path)
    try:
        db.init_schema()
    finally:
        db.close()


def test_init_schema_migration_is_idempotent_on_legacy_db(legacy_db_path):
    """Calling init_schema() (and therefore the migration) more than once —
    e.g. two container restarts — must not raise 'duplicate column'."""
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        db.init_schema()
        cols = [row["name"] for row in db._conn.execute("PRAGMA table_info(run)").fetchall()]
        assert cols.count("segment_index") == 1
    finally:
        db.close()


def test_migration_adds_run_columns_with_documented_defaults(legacy_db_path):
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        cols = {
            row["name"]
            for row in db._conn.execute("PRAGMA table_info(run)").fetchall()
        }
        for name in (
            "planned_seconds", "sf_schedule", "interval_minutes",
            "segment_index", "segment_started_at", "downlink_test", "dl_counts",
        ):
            assert name in cols, f"missing migrated column: {name}"

        row = db._conn.execute("SELECT * FROM run WHERE id = 4").fetchone()
        assert row["segment_index"] == 0  # declared NOT NULL DEFAULT 0
        assert row["downlink_test"] == 1  # declared NOT NULL DEFAULT 1
        assert row["planned_seconds"] is None  # no default -> NULL for old rows
        assert row["sf_schedule"] is None
        assert row["interval_minutes"] is None
        assert row["segment_started_at"] is None
        assert row["dl_counts"] is None
    finally:
        db.close()


def test_migration_adds_placement_columns_as_null_for_existing_rows(legacy_db_path):
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        cols = {
            row["name"]
            for row in db._conn.execute("PRAGMA table_info(placement)").fetchall()
        }
        assert {"floorplan_id", "map_x", "map_y"} <= cols

        for pid in (7, 8):
            row = db._conn.execute(
                "SELECT * FROM placement WHERE id = ?", (pid,)
            ).fetchone()
            assert row["floorplan_id"] is None
            assert row["map_x"] is None
            assert row["map_y"] is None
    finally:
        db.close()


def test_migration_preserves_existing_rows_and_ids(legacy_db_path):
    """No DROP, no renumbering — additive only, per spec §15."""
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        conn = db._conn
        assert [r["id"] for r in conn.execute("SELECT id FROM placement ORDER BY id")] == [7, 8]
        assert [r["id"] for r in conn.execute("SELECT id FROM run ORDER BY id")] == [4]
        assert [r["id"] for r in conn.execute("SELECT id FROM photo ORDER BY id")] == [2]

        gw_placement = conn.execute("SELECT * FROM placement WHERE id = 7").fetchone()
        assert gw_placement["node_id"] == 1
        assert gw_placement["floor"] == "0"

        dev_placement = conn.execute("SELECT * FROM placement WHERE id = 8").fetchone()
        assert dev_placement["node_id"] == 2
        assert dev_placement["floor"] == "3"

        run = conn.execute("SELECT * FROM run WHERE id = 4").fetchone()
        assert run["device_node_id"] == 2
        assert run["device_placement_id"] == 8
        assert run["gateway_placement_id"] == 7
        assert run["status"] == "running"

        photo = conn.execute("SELECT * FROM photo WHERE id = 2").fetchone()
        assert photo["placement_id"] == 8
        assert photo["filename"] == "1.jpg"
    finally:
        db.close()


def test_migration_does_not_reset_sqlite_sequence(legacy_db_path):
    """A later insert must continue past the highest id ever used, not
    reuse a deleted one — the migration must leave autoincrement
    bookkeeping alone."""
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        conn = db._conn
        assert _sequence(conn, "placement") >= 9
        assert _sequence(conn, "run") >= 5
        assert _sequence(conn, "photo") >= 3

        new_node_id, _ = db.upsert_node("device", "new-device", "aabbccddeeff0011")
        new_placement_id = db.create_placement(
            new_node_id, "1", "101", "", "", ""
        )
        assert new_placement_id > 9
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Stage 1 — event table + backfill (spec §14/§15), against the id-gap
# fixture above: run #4 is still 'running' (no ended_at), so only
# run_started should be backfilled.
# ---------------------------------------------------------------------------


def test_migration_backfills_run_started_only_for_still_running_run(legacy_db_path):
    """run #4 has no ended_at — only its run_started should be backfilled,
    never a run_stopped for a run that (as far as the data shows) never
    stopped."""
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        events = db._conn.execute(
            "SELECT type, node_id, run_id, source FROM event ORDER BY id"
        ).fetchall()
        assert len(events) == 1
        assert events[0]["type"] == "run_started"
        assert events[0]["node_id"] == 2  # thermostat-katia
        assert events[0]["run_id"] == 4
        assert events[0]["source"] == "backfill"
    finally:
        db.close()


def test_migration_never_backfills_relocated_gateway_moved_or_join(legacy_db_path):
    """Per spec §15: zero source rows exist for gateway_moved (the gateway
    was never moved) and relocated (placement gaps in the real data are
    form corrections, not moves); join/ack/nack were simply never
    persisted before this table existed. None of these must ever appear
    just because a migration ran."""
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        types = {
            row["type"] for row in db._conn.execute("SELECT DISTINCT type FROM event").fetchall()
        }
        assert types == {"run_started"}
    finally:
        db.close()


def test_migration_sets_user_version_on_legacy_db(legacy_db_path):
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        version = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 1
    finally:
        db.close()


def test_migration_backfill_is_idempotent_does_not_duplicate_events(legacy_db_path):
    """Calling init_schema() twice (two container restarts) must not
    double-insert the backfilled events — see _run_migrations' PRAGMA
    user_version gate."""
    db = Database(legacy_db_path)
    try:
        db.init_schema()
        db.init_schema()
        count = db._conn.execute("SELECT COUNT(*) AS c FROM event").fetchone()["c"]
        assert count == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Stage 1 — backfill against a 7-run fixture shaped like the real snapshot
# (docs/developer/design/cockpit-redesign-spec.md §15: 6x
# reason='schedule-complete' + 1x NULL, all 7 finished) — pins the exact
# backfill output the build report cites.
# ---------------------------------------------------------------------------

_SEVEN_RUNS = [
    # (run_id, device_node_id, reason, started_at, ended_at)
    (4, 2, "schedule-complete", "2026-07-08T14:15:49+00:00", "2026-07-09T14:16:21+00:00"),
    (5, 5, "schedule-complete", "2026-07-08T14:16:08+00:00", "2026-07-09T14:16:21+00:00"),
    (6, 4, "schedule-complete", "2026-07-08T14:16:17+00:00", "2026-07-09T14:16:21+00:00"),
    (7, 3, None, "2026-07-09T11:10:24+00:00", "2026-07-09T15:12:13+00:00"),
    (8, 5, "schedule-complete", "2026-07-10T11:47:50+00:00", "2026-07-11T11:48:36+00:00"),
    (9, 4, "schedule-complete", "2026-07-10T11:55:22+00:00", "2026-07-11T11:55:36+00:00"),
    (10, 2, "schedule-complete", "2026-07-10T13:17:05+00:00", "2026-07-11T13:17:36+00:00"),
]


def _build_legacy_db_with_seven_finished_runs(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_LEGACY_SCHEMA)

    conn.execute(
        "INSERT INTO node (id, kind, name, eui, created_at) VALUES "
        "(1, 'gateway', 'whz-kerlink-ifevo', '7076ff0064071a3d', '2026-01-01T00:00:00+00:00')"
    )
    for node_id, name in ((2, "EVA"), (3, "HomeMatic - DNT"), (4, "thermostat-katia"), (5, "thermostat-maurice")):
        conn.execute(
            "INSERT INTO node (id, kind, name, eui, created_at) VALUES (?, 'device', ?, ?, "
            "'2026-01-01T00:00:00+00:00')",
            (node_id, name, f"{node_id:016x}"),
        )
    for node_id in (1, 2, 3, 4, 5):
        conn.execute(
            "INSERT INTO placement (id, node_id, started_at, ended_at) VALUES "
            "(?, ?, '2026-01-01T00:00:00+00:00', NULL)",
            (node_id, node_id),
        )
    for run_id, device_node_id, reason, started_at, ended_at in _SEVEN_RUNS:
        conn.execute(
            "INSERT INTO run (id, device_node_id, device_placement_id, gateway_placement_id, "
            "phase, started_at, ended_at, status, reason, packets) "
            "VALUES (?, ?, ?, 1, 'adr', ?, ?, 'done', ?, 10)",
            (run_id, device_node_id, device_node_id, started_at, ended_at, reason),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def seven_run_db_path(tmp_path) -> str:
    path = str(tmp_path / "seven_runs.db")
    _build_legacy_db_with_seven_finished_runs(path)
    return path


def test_backfill_produces_run_started_and_run_stopped_for_every_run(seven_run_db_path):
    """Pins spec §15's exact numbers: 7 run_started + 7 run_stopped (every
    run finished), nothing else — no gateway_moved/relocated/join/ack/nack —
    and every row source='backfill'."""
    db = Database(seven_run_db_path)
    try:
        db.init_schema()
        events = db._conn.execute(
            "SELECT type, source, payload FROM event ORDER BY id"
        ).fetchall()
        assert len(events) == 14
        assert all(e["source"] == "backfill" for e in events)
        started = [e for e in events if e["type"] == "run_started"]
        stopped = [e for e in events if e["type"] == "run_stopped"]
        assert len(started) == 7
        assert len(stopped) == 7
        other_types = {e["type"] for e in events} - {"run_started", "run_stopped"}
        assert other_types == set()
    finally:
        db.close()


def test_backfill_uses_the_stored_reason_or_unknown(seven_run_db_path):
    """6 runs have reason='schedule-complete'; the one with a NULL reason
    (run #7, matching the real snapshot) becomes 'unknown' — never NULL,
    never fabricated as something more specific."""
    db = Database(seven_run_db_path)
    try:
        db.init_schema()
        stopped = db._conn.execute(
            "SELECT run_id, payload FROM event WHERE type = 'run_stopped' ORDER BY run_id"
        ).fetchall()
        reasons = {row["run_id"]: json.loads(row["payload"])["reason"] for row in stopped}
        assert reasons[7] == "unknown"
        for run_id in (4, 5, 6, 8, 9, 10):
            assert reasons[run_id] == "schedule-complete"
    finally:
        db.close()


def test_backfill_event_ts_is_the_runs_own_timestamp_not_migration_time(seven_run_db_path):
    """The backfilled ts must be the run's actual started_at/ended_at — the
    historical moment — not "now" when the migration happens to run."""
    db = Database(seven_run_db_path)
    try:
        db.init_schema()
        started = db._conn.execute(
            "SELECT ts FROM event WHERE type = 'run_started' AND run_id = 4"
        ).fetchone()
        stopped = db._conn.execute(
            "SELECT ts FROM event WHERE type = 'run_stopped' AND run_id = 4"
        ).fetchone()
        assert started["ts"] == "2026-07-08T14:15:49+00:00"
        assert stopped["ts"] == "2026-07-09T14:16:21+00:00"
    finally:
        db.close()


def test_backfill_on_seven_run_db_is_idempotent(seven_run_db_path):
    db = Database(seven_run_db_path)
    try:
        db.init_schema()
        db.init_schema()
        count = db._conn.execute("SELECT COUNT(*) AS c FROM event").fetchone()["c"]
        assert count == 14
    finally:
        db.close()
