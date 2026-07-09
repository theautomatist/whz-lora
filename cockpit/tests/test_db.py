"""test_db.py — unit tests for db.py (F-0006 Feldmess-Workflow persistence).

Every test gets its own temp SQLite file — no shared state, no /data
dependency, no ChirpStack/MQTT involved.
"""
import csv
import os
import tempfile

import pytest

from app.db import MAX_PHOTOS_PER_PLACEMENT, Database


def _new_db() -> Database:
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    d = Database(path)
    d.init_schema()
    return d


# ---------------------------------------------------------------------------
# node
# ---------------------------------------------------------------------------


def test_upsert_node_creates():
    d = _new_db()
    node_id, created = d.upsert_node("device", "sensor-01", "aaaa000000000001")
    assert created is True
    node = d.get_node(node_id)
    assert node["kind"] == "device"
    assert node["name"] == "sensor-01"
    assert node["eui"] == "aaaa000000000001"


def test_upsert_node_idempotent_by_eui():
    d = _new_db()
    id1, created1 = d.upsert_node("device", "sensor-01", "aaaa000000000001")
    id2, created2 = d.upsert_node("device", "sensor-01", "aaaa000000000001")
    assert created1 is True
    assert created2 is False
    assert id1 == id2


def test_upsert_node_updates_name_on_rename():
    d = _new_db()
    id1, _ = d.upsert_node("device", "old-name", "aaaa000000000001")
    id2, created = d.upsert_node("device", "new-name", "aaaa000000000001")
    assert created is False
    assert id1 == id2
    assert d.get_node(id1)["name"] == "new-name"


def test_list_nodes_filters_by_kind():
    d = _new_db()
    d.upsert_node("device", "d1", "aaaa000000000001")
    d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    devices = d.list_nodes("device")
    gateways = d.list_nodes("gateway")
    assert len(devices) == 1
    assert len(gateways) == 1
    assert devices[0]["eui"] == "aaaa000000000001"


def test_get_node_by_eui_not_found_returns_none():
    d = _new_db()
    assert d.get_node_by_eui("nonexistent") is None


# ---------------------------------------------------------------------------
# placement — create closes previous active placement
# ---------------------------------------------------------------------------


def test_no_active_placement_initially():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    assert d.get_active_placement(node_id) is None


def test_create_placement_becomes_active():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    placement_id = d.create_placement(node_id, "3OG", "R301", "desk", "", "3dbi")
    active = d.get_active_placement(node_id)
    assert active is not None
    assert active["id"] == placement_id
    assert active["ended_at"] is None
    assert active["floor"] == "3OG"
    assert active["room"] == "R301"


def test_create_placement_closes_previous():
    """A second placement for the same node must close the first (ended_at set)."""
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    p1 = d.create_placement(node_id, "EG", "R1", "first", "", "3dbi")
    p2 = d.create_placement(node_id, "1OG", "R2", "second", "", "12dbi")

    assert p1 != p2
    old = d.get_placement(p1)
    assert old["ended_at"] is not None  # closed

    active = d.get_active_placement(node_id)
    assert active["id"] == p2
    assert active["description"] == "second"


def test_create_placement_does_not_affect_other_nodes():
    d = _new_db()
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    n2, _ = d.upsert_node("device", "d2", "bbbb000000000002")
    d.create_placement(n1, "EG", "R1", "d1 spot", "", "3dbi")
    d.create_placement(n2, "1OG", "R2", "d2 spot", "", "3dbi")

    assert d.get_active_placement(n1)["description"] == "d1 spot"
    assert d.get_active_placement(n2)["description"] == "d2 spot"


# ---------------------------------------------------------------------------
# photo — max 3 per placement enforced
# ---------------------------------------------------------------------------


def test_photo_count_starts_at_zero():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    placement_id = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    assert d.count_photos(placement_id) == 0


def test_add_photo_up_to_max():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    placement_id = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")

    for i in range(MAX_PHOTOS_PER_PLACEMENT):
        photo_id = d.add_photo(placement_id, f"{i + 1}.jpg")
        assert photo_id is not None

    assert d.count_photos(placement_id) == MAX_PHOTOS_PER_PLACEMENT


def test_photo_max_three_enforced():
    """The 4th photo on the same placement must raise ValueError."""
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    placement_id = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")

    for i in range(MAX_PHOTOS_PER_PLACEMENT):
        d.add_photo(placement_id, f"{i + 1}.jpg")

    with pytest.raises(ValueError):
        d.add_photo(placement_id, "4.jpg")

    # Count must stay at the max, not 4
    assert d.count_photos(placement_id) == MAX_PHOTOS_PER_PLACEMENT


def test_photo_scoped_per_placement():
    """MAX_PHOTOS_PER_PLACEMENT is per placement, not per node."""
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    p1 = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    for i in range(MAX_PHOTOS_PER_PLACEMENT):
        d.add_photo(p1, f"{i + 1}.jpg")

    p2 = d.create_placement(node_id, "1OG", "R2", "", "", "3dbi")
    # New placement starts fresh — must accept photos again
    photo_id = d.add_photo(p2, "1.jpg")
    assert photo_id is not None
    assert d.count_photos(p2) == 1


def test_get_photo_and_list_photos():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    placement_id = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    photo_id = d.add_photo(placement_id, "1.jpg")

    photo = d.get_photo(photo_id)
    assert photo["filename"] == "1.jpg"
    assert photo["placement_id"] == placement_id

    photos = d.list_photos(placement_id)
    assert len(photos) == 1
    assert photos[0]["id"] == photo_id


# ---------------------------------------------------------------------------
# run — start requires placements are pre-existing (caller's job); lifecycle
# ---------------------------------------------------------------------------


def test_get_active_run_none_initially():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    assert d.get_active_run(node_id) is None


def test_start_run_creates_csv_with_header():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "desk", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "hallway", "", "")

    data_dir = tempfile.mkdtemp()
    run = d.start_run(node_id, dp, gp, "sf9", data_dir, "aaaa000000000001")

    assert run["status"] == "running"
    assert run["ended_at"] is None
    assert run["packets"] == 0
    assert os.path.exists(run["csv_path"])
    assert f"run_{run['id']}_" in os.path.basename(run["csv_path"])

    with open(run["csv_path"], encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    from app.db import CSV_COLUMNS
    assert header == CSV_COLUMNS


def test_start_run_becomes_active_run():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()

    run = d.start_run(node_id, dp, gp, "adr", data_dir, "aaaa000000000001")
    active = d.get_active_run(node_id)
    assert active is not None
    assert active["id"] == run["id"]


def test_stop_run_sets_done():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()
    run = d.start_run(node_id, dp, gp, "adr", data_dir, "aaaa000000000001")

    stopped_id = d.stop_active_run_for_device(node_id, status="done", reason="manual")
    assert stopped_id == run["id"]

    updated = d.get_run(run["id"])
    assert updated["status"] == "done"
    assert updated["reason"] == "manual"
    assert updated["ended_at"] is not None
    assert d.get_active_run(node_id) is None


def test_stop_active_run_for_device_none_when_no_run():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    assert d.stop_active_run_for_device(node_id) is None


def test_increment_run_packets():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()
    run = d.start_run(node_id, dp, gp, "adr", data_dir, "aaaa000000000001")

    assert d.increment_run_packets(run["id"]) == 1
    assert d.increment_run_packets(run["id"]) == 2
    assert d.get_run(run["id"])["packets"] == 2


# ---------------------------------------------------------------------------
# gateway-move guard primitives — list_running_runs / abort_running_runs
# ---------------------------------------------------------------------------


def test_list_running_runs_empty_initially():
    d = _new_db()
    assert d.list_running_runs() == []


def test_list_running_runs_only_running():
    d = _new_db()
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    n2, _ = d.upsert_node("device", "d2", "bbbb000000000002")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()

    dp1 = d.create_placement(n1, "EG", "R1", "", "", "3dbi")
    run1 = d.start_run(n1, dp1, gp, "adr", data_dir, "aaaa000000000001")

    dp2 = d.create_placement(n2, "1OG", "R2", "", "", "3dbi")
    run2 = d.start_run(n2, dp2, gp, "adr", data_dir, "bbbb000000000002")
    d.stop_run(run2["id"], status="done")  # this one finished

    running = d.list_running_runs()
    assert len(running) == 1
    assert running[0]["id"] == run1["id"]
    assert running[0]["device_name"] == "d1"


def test_abort_running_runs_sets_aborted_and_keeps_data():
    """gateway/move/force: running runs become 'aborted' with a reason;
    the run row (and its CSV data) is otherwise untouched."""
    d = _new_db()
    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    dp1 = d.create_placement(n1, "EG", "R1", "", "", "3dbi")
    data_dir = tempfile.mkdtemp()
    run1 = d.start_run(n1, dp1, gp, "adr", data_dir, "aaaa000000000001")
    d.increment_run_packets(run1["id"])
    d.increment_run_packets(run1["id"])

    aborted = d.abort_running_runs(reason="gateway-move")
    assert len(aborted) == 1
    assert aborted[0]["id"] == run1["id"]

    updated = d.get_run(run1["id"])
    assert updated["status"] == "aborted"
    assert updated["reason"] == "gateway-move"
    assert updated["packets"] == 2  # data kept
    assert os.path.exists(updated["csv_path"])  # CSV file kept

    # Guard is now clear
    assert d.list_running_runs() == []


def test_abort_running_runs_empty_is_noop():
    d = _new_db()
    assert d.abort_running_runs(reason="gateway-move") == []


# ---------------------------------------------------------------------------
# run history — list_runs_for_node joins placement + gateway description
# ---------------------------------------------------------------------------


def test_list_runs_for_node_includes_placement_metadata():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "hallway spot", "", "")
    dp = d.create_placement(node_id, "3OG", "R301", "desk", "", "3dbi")
    data_dir = tempfile.mkdtemp()
    run = d.start_run(node_id, dp, gp, "sf9", data_dir, "aaaa000000000001")

    runs = d.list_runs_for_node(node_id)
    assert len(runs) == 1
    r = runs[0]
    assert r["id"] == run["id"]
    assert r["d_floor"] == "3OG"
    assert r["d_room"] == "R301"
    assert r["d_description"] == "desk"
    assert r["g_description"] == "hallway spot"


def test_list_runs_for_node_newest_first():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()

    dp1 = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    run1 = d.start_run(node_id, dp1, gp, "adr", data_dir, "aaaa000000000001")
    d.stop_run(run1["id"])

    dp2 = d.create_placement(node_id, "1OG", "R2", "", "", "3dbi")
    run2 = d.start_run(node_id, dp2, gp, "sf9", data_dir, "aaaa000000000001")

    runs = d.list_runs_for_node(node_id)
    assert runs[0]["id"] == run2["id"]
    assert runs[1]["id"] == run1["id"]


# ---------------------------------------------------------------------------
# record_uplink_for_run — CSV row built with placement + gateway metadata
# ---------------------------------------------------------------------------


SAMPLE_METRICS = {
    "dev_eui":  "aaaa000000000001",
    "rssi_dbm": -72,
    "snr_db":   6.5,
    "sf":       9,
    "freq_hz":  868300000,
    "f_cnt":    17,
    "gw_eui":   "7076ff0064071a3d",
}


def _setup_active_run(d: Database, data_dir: str):
    node_id, _ = d.upsert_node("device", "sensor-01", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "3OG", "R301", "near window", "note", "12dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "hallway ceiling", "", "")
    run = d.start_run(node_id, dp, gp, "sf9", data_dir, "aaaa000000000001")
    return node_id, run


def test_record_uplink_for_run_returns_none_without_active_run():
    d = _new_db()
    d.upsert_node("device", "sensor-01", "aaaa000000000001")
    result = d.record_uplink_for_run("aaaa000000000001", SAMPLE_METRICS)
    assert result is None


def test_record_uplink_for_run_returns_none_for_unknown_device():
    d = _new_db()
    result = d.record_uplink_for_run("ffffffffffffffff", SAMPLE_METRICS)
    assert result is None


def test_record_uplink_for_run_increments_packets():
    d = _new_db()
    data_dir = tempfile.mkdtemp()
    _setup_active_run(d, data_dir)

    assert d.record_uplink_for_run("aaaa000000000001", SAMPLE_METRICS) == 1
    assert d.record_uplink_for_run("aaaa000000000001", SAMPLE_METRICS) == 2


def test_record_uplink_for_run_csv_row_has_placement_and_gateway_metadata():
    d = _new_db()
    data_dir = tempfile.mkdtemp()
    node_id, run = _setup_active_run(d, data_dir)

    d.record_uplink_for_run("aaaa000000000001", SAMPLE_METRICS)

    with open(run["csv_path"], encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    row = rows[0]
    assert row["dev_eui"] == "aaaa000000000001"
    assert row["run_id"] == str(run["id"])
    assert row["node_name"] == "sensor-01"
    assert row["floor"] == "3OG"
    assert row["room"] == "R301"
    assert row["description"] == "near window"
    assert row["antenna"] == "12dbi"
    assert row["phase"] == "sf9"
    assert row["gateway_desc"] == "hallway ceiling"
    assert row["rssi_dbm"] == "-72"
    assert row["snr_db"] == "6.5"
    assert row["sf"] == "9"
    assert row["freq_hz"] == "868300000"
    assert row["f_cnt"] == "17"
    assert row["gw_eui"] == "7076ff0064071a3d"


def test_record_uplink_for_run_no_row_after_run_stopped():
    d = _new_db()
    data_dir = tempfile.mkdtemp()
    node_id, run = _setup_active_run(d, data_dir)
    d.stop_run(run["id"])

    result = d.record_uplink_for_run("aaaa000000000001", SAMPLE_METRICS)
    assert result is None

    with open(run["csv_path"], encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1  # header only


# ---------------------------------------------------------------------------
# Phase B — SF-sweep columns: migration, start_run(sf_schedule=...),
# advance_run_segment, get_last_run
# ---------------------------------------------------------------------------


def test_fresh_db_has_sweep_columns():
    """_SCHEMA already declares the Phase B columns on a brand-new database
    (the ALTER-based migration is a no-op there)."""
    d = _new_db()
    cols = {row["name"] for row in d._conn.execute("PRAGMA table_info(run)").fetchall()}
    assert {
        "planned_seconds", "sf_schedule", "interval_minutes",
        "segment_index", "segment_started_at",
    } <= cols


def test_migration_adds_missing_columns_to_existing_db():
    """Simulate a pre-Phase-B database: drop back to the original run table
    shape, then confirm init_schema() adds the new columns via ALTER TABLE
    without touching existing data."""
    path = os.path.join(tempfile.mkdtemp(), "legacy.db")
    d = Database(path)
    d._conn.executescript(
        """
        CREATE TABLE node (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
            name TEXT NOT NULL, eui TEXT UNIQUE, created_at TEXT NOT NULL
        );
        CREATE TABLE placement (
            id INTEGER PRIMARY KEY AUTOINCREMENT, node_id INTEGER NOT NULL,
            floor TEXT DEFAULT '', room TEXT DEFAULT '', description TEXT DEFAULT '',
            note TEXT DEFAULT '', antenna TEXT DEFAULT '',
            started_at TEXT NOT NULL, ended_at TEXT
        );
        CREATE TABLE photo (
            id INTEGER PRIMARY KEY AUTOINCREMENT, placement_id INTEGER NOT NULL,
            filename TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE run (
            id INTEGER PRIMARY KEY AUTOINCREMENT, device_node_id INTEGER NOT NULL,
            device_placement_id INTEGER NOT NULL, gateway_placement_id INTEGER NOT NULL,
            phase TEXT NOT NULL, csv_path TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL,
            reason TEXT, packets INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    d._conn.execute(
        "INSERT INTO run (device_node_id, device_placement_id, gateway_placement_id, "
        "phase, started_at, status, packets) VALUES (1, 1, 1, 'adr', '2026-01-01T00:00:00+00:00', 'done', 7)"
    )
    d._conn.commit()

    d.init_schema()  # runs the migration

    cols = {row["name"] for row in d._conn.execute("PRAGMA table_info(run)").fetchall()}
    assert {"planned_seconds", "sf_schedule", "interval_minutes", "segment_index", "segment_started_at"} <= cols

    row = d.get_run(1)
    assert row["packets"] == 7  # pre-existing data untouched
    assert row["segment_index"] == 0  # NOT NULL DEFAULT 0 applied
    assert row["sf_schedule"] is None


def test_init_schema_migration_is_idempotent():
    """Calling init_schema() (and therefore the migration) more than once
    must not raise 'duplicate column' errors."""
    d = _new_db()
    d.init_schema()
    d.init_schema()
    cols = [row["name"] for row in d._conn.execute("PRAGMA table_info(run)").fetchall()]
    assert cols.count("segment_index") == 1


def test_start_run_with_sweep_stores_schedule_and_segment():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()
    schedule = [{"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}, {"sf": 12, "seconds": 100}]

    run = d.start_run(
        node_id, dp, gp, "adr", data_dir, "aaaa000000000001",
        planned_seconds=300, sf_schedule=schedule, interval_minutes=5,
    )

    assert run["planned_seconds"] == 300
    assert run["interval_minutes"] == 5
    assert run["segment_index"] == 0
    assert run["segment_started_at"] is not None
    import json as _json
    assert _json.loads(run["sf_schedule"]) == schedule


def test_start_run_without_sweep_leaves_columns_null():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()

    run = d.start_run(node_id, dp, gp, "adr", data_dir, "aaaa000000000001")

    assert run["planned_seconds"] is None
    assert run["sf_schedule"] is None
    assert run["interval_minutes"] is None
    assert run["segment_index"] == 0
    assert run["segment_started_at"] is None


def test_advance_run_segment_updates_index_and_timestamp():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()
    run = d.start_run(
        node_id, dp, gp, "adr", data_dir, "aaaa000000000001",
        planned_seconds=300, sf_schedule=[{"sf": 7, "seconds": 100}], interval_minutes=5,
    )

    d.advance_run_segment(run["id"], 1, "2026-01-01T13:00:00+00:00")

    updated = d.get_run(run["id"])
    assert updated["segment_index"] == 1
    assert updated["segment_started_at"] == "2026-01-01T13:00:00+00:00"


def test_get_last_run_none_when_never_run():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    assert d.get_last_run(node_id) is None


def test_get_last_run_returns_most_recent_regardless_of_status():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()

    dp1 = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    run1 = d.start_run(node_id, dp1, gp, "adr", data_dir, "aaaa000000000001")
    d.stop_run(run1["id"], status="done")

    assert d.get_last_run(node_id)["id"] == run1["id"]

    dp2 = d.create_placement(node_id, "1OG", "R2", "", "", "3dbi")
    run2 = d.start_run(node_id, dp2, gp, "adr", data_dir, "aaaa000000000001")

    assert d.get_last_run(node_id)["id"] == run2["id"]
    assert d.get_last_run(node_id)["status"] == "running"
