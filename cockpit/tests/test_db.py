"""test_db.py — unit tests for db.py (F-0006 Feldmess-Workflow persistence).

Every test gets its own temp SQLite file — no shared state, no /data
dependency, no ChirpStack/MQTT involved.
"""
import csv
import datetime
import os
import tempfile

import pytest

from app.db import (
    MAX_PHOTOS_PER_PLACEMENT,
    RF_FRAME_COLUMNS,
    RF_FRAME_RETENTION_MAX,
    RF_RECENT_FRAMES_LIMIT,
    RF_TIMELINE_HOURS,
    Database,
    parse_dl_counts,
)


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
# run history — list_runs joins placement + device/gateway metadata;
# node_id=None (F-0007 History view) returns every device's runs
# ---------------------------------------------------------------------------


def test_list_runs_includes_placement_metadata():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "hallway spot", "", "")
    dp = d.create_placement(node_id, "3OG", "R301", "desk", "", "3dbi")
    data_dir = tempfile.mkdtemp()
    run = d.start_run(node_id, dp, gp, "sf9", data_dir, "aaaa000000000001")

    runs = d.list_runs(node_id)
    assert len(runs) == 1
    r = runs[0]
    assert r["id"] == run["id"]
    assert r["device_name"] == "d1"
    assert r["device_eui"] == "aaaa000000000001"
    assert r["d_floor"] == "3OG"
    assert r["d_room"] == "R301"
    assert r["d_description"] == "desk"
    assert r["g_floor"] == "EG"
    assert r["g_room"] == "flur"
    assert r["g_description"] == "hallway spot"


def test_list_runs_newest_first():
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

    runs = d.list_runs(node_id)
    assert runs[0]["id"] == run2["id"]
    assert runs[1]["id"] == run1["id"]


def test_list_runs_without_node_id_returns_every_device():
    d = _new_db()
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()

    n1, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    dp1 = d.create_placement(n1, "EG", "R1", "", "", "3dbi")
    run1 = d.start_run(n1, dp1, gp, "sf9", data_dir, "aaaa000000000001")

    n2, _ = d.upsert_node("device", "d2", "bbbb000000000002")
    dp2 = d.create_placement(n2, "1OG", "R2", "", "", "3dbi")
    run2 = d.start_run(n2, dp2, gp, "sf9", data_dir, "bbbb000000000002")

    runs = d.list_runs()
    assert {r["id"] for r in runs} == {run1["id"], run2["id"]}
    # newest first regardless of device
    assert runs[0]["id"] == run2["id"]
    assert runs[1]["id"] == run1["id"]


def test_list_runs_without_node_id_empty_when_no_runs():
    d = _new_db()
    assert d.list_runs() == []


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


# ---------------------------------------------------------------------------
# "Trust & Sichtbarkeit" — downlink_test flag + per-SF confirmed-downlink
# reliability test (maybe_trigger_downlink_test / record_downlink_test_ack)
# ---------------------------------------------------------------------------


def _new_sweep_run(interval_minutes=5, downlink_test=True, schedule=None):
    """A fresh DB with one device, both placements, and a running SF-sweep
    (default SF7->SF9->SF12, 100 s each) — the setup every downlink-test
    test below needs."""
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    data_dir = tempfile.mkdtemp()
    schedule = schedule if schedule is not None else [
        {"sf": 7, "seconds": 100}, {"sf": 9, "seconds": 100}, {"sf": 12, "seconds": 100},
    ]
    run = d.start_run(
        node_id, dp, gp, "adr", data_dir, "aaaa000000000001",
        planned_seconds=sum(s["seconds"] for s in schedule),
        sf_schedule=schedule, interval_minutes=interval_minutes,
        downlink_test=downlink_test,
    )
    return d, node_id, run


def test_fresh_db_has_downlink_test_columns():
    d = _new_db()
    cols = {row["name"] for row in d._conn.execute("PRAGMA table_info(run)").fetchall()}
    assert {"downlink_test", "dl_counts"} <= cols


def test_start_run_downlink_test_defaults_true():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    run = d.start_run(node_id, dp, gp, "adr", tempfile.mkdtemp(), "aaaa000000000001")
    assert run["downlink_test"] == 1
    assert run["dl_counts"] is None


def test_start_run_downlink_test_can_be_disabled():
    d, node_id, run = _new_sweep_run(downlink_test=False)
    assert run["downlink_test"] == 0


def test_parse_dl_counts_defaults_for_empty_or_invalid():
    assert parse_dl_counts(None) == {"by_sf": {}, "pending_sf": None}
    assert parse_dl_counts("") == {"by_sf": {}, "pending_sf": None}
    assert parse_dl_counts("not json") == {"by_sf": {}, "pending_sf": None}
    assert parse_dl_counts("42") == {"by_sf": {}, "pending_sf": None}  # valid JSON, not a dict


def test_parse_dl_counts_roundtrip():
    raw = '{"by_sf": {"7": {"sent": 2, "acked": 1}}, "pending_sf": 9}'
    assert parse_dl_counts(raw) == {"by_sf": {"7": {"sent": 2, "acked": 1}}, "pending_sf": 9}


# --- maybe_trigger_downlink_test ---------------------------------------


def test_maybe_trigger_unknown_device_returns_none():
    d = _new_db()
    assert d.maybe_trigger_downlink_test("ffffffffffffffff", 3) is None


def test_maybe_trigger_no_active_run_returns_none():
    d = _new_db()
    d.upsert_node("device", "d1", "aaaa000000000001")
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 3) is None


def test_maybe_trigger_disabled_returns_none():
    d, node_id, run = _new_sweep_run(downlink_test=False)
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 15) is None


def test_maybe_trigger_no_interval_minutes_returns_none():
    """A Phase A fixed run (no commanded interval) has no rate to derive K
    from, and no SF to attribute a test to."""
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    d.start_run(node_id, dp, gp, "adr", tempfile.mkdtemp(), "aaaa000000000001")
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 3) is None


def test_maybe_trigger_no_schedule_returns_none():
    """Defensive: interval_minutes set but no sf_schedule (not reachable via
    the API, main._resolve_schedule always sets both or neither) — no SF to
    attribute a test to."""
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dp = d.create_placement(node_id, "EG", "R1", "", "", "3dbi")
    gp = d.create_placement(gw_id, "EG", "flur", "", "", "")
    d.start_run(node_id, dp, gp, "adr", tempfile.mkdtemp(), "aaaa000000000001", interval_minutes=5)
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 3) is None


def test_maybe_trigger_fires_on_kth_uplink():
    """interval_minutes=5 -> K = max(1, round(15/5)) = 3."""
    d, node_id, run = _new_sweep_run(interval_minutes=5)
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 1) is None
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 2) is None
    dl = d.maybe_trigger_downlink_test("aaaa000000000001", 3)
    assert dl == {
        "dev_eui": "aaaa000000000001", "f_port": 1, "data_hex": "04",
        "run_id": run["id"], "sf": 7,
    }


def test_maybe_trigger_k_scales_with_interval():
    """interval_minutes=15 -> K = max(1, round(15/15)) = 1 -> every uplink."""
    d, node_id, run = _new_sweep_run(interval_minutes=15)
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 1) is not None


def test_maybe_trigger_k_never_below_one():
    """A very short interval must not push K below 1 (would divide by
    ~0/negative or fire more than once per uplink)."""
    d, node_id, run = _new_sweep_run(interval_minutes=255)  # 15/255 rounds to 0
    dl = d.maybe_trigger_downlink_test("aaaa000000000001", 1)
    assert dl is not None  # K clamped to max(1, ...) == 1


def test_maybe_trigger_never_piles_up_while_pending():
    d, node_id, run = _new_sweep_run(interval_minutes=15)  # K=1
    first = d.maybe_trigger_downlink_test("aaaa000000000001", 1)
    assert first is not None
    second = d.maybe_trigger_downlink_test("aaaa000000000001", 2)
    assert second is None  # still pending — no ack yet


def test_maybe_trigger_records_sent_count_by_sf():
    d, node_id, run = _new_sweep_run(interval_minutes=15)  # K=1, current sf=7
    d.maybe_trigger_downlink_test("aaaa000000000001", 1)
    counts = parse_dl_counts(d.get_run(run["id"])["dl_counts"])
    assert counts["by_sf"]["7"]["sent"] == 1
    assert counts["pending_sf"] == 7


def test_maybe_trigger_attributes_to_current_segment_sf():
    d, node_id, run = _new_sweep_run(interval_minutes=15)
    d.advance_run_segment(run["id"], 1, "2026-01-01T00:00:00+00:00")  # now SF9
    dl = d.maybe_trigger_downlink_test("aaaa000000000001", 1)
    assert dl["sf"] == 9


# --- record_downlink_test_ack -------------------------------------------


def test_record_ack_noop_without_active_run():
    d = _new_db()
    d.upsert_node("device", "d1", "aaaa000000000001")
    d.record_downlink_test_ack("aaaa000000000001", True)  # must not raise


def test_record_ack_noop_without_pending():
    d, node_id, run = _new_sweep_run(interval_minutes=15)
    d.record_downlink_test_ack("aaaa000000000001", True)  # nothing pending yet
    counts = parse_dl_counts(d.get_run(run["id"])["dl_counts"])
    assert counts["by_sf"] == {}


def test_record_ack_true_increments_acked_and_clears_pending():
    d, node_id, run = _new_sweep_run(interval_minutes=15)
    d.maybe_trigger_downlink_test("aaaa000000000001", 1)  # sf7 pending

    d.record_downlink_test_ack("aaaa000000000001", True)

    counts = parse_dl_counts(d.get_run(run["id"])["dl_counts"])
    assert counts["by_sf"]["7"] == {"sent": 1, "acked": 1}
    assert counts["pending_sf"] is None


def test_record_ack_false_clears_pending_without_incrementing():
    d, node_id, run = _new_sweep_run(interval_minutes=15)
    d.maybe_trigger_downlink_test("aaaa000000000001", 1)

    d.record_downlink_test_ack("aaaa000000000001", False)

    counts = parse_dl_counts(d.get_run(run["id"])["dl_counts"])
    assert counts["by_sf"]["7"] == {"sent": 1, "acked": 0}
    assert counts["pending_sf"] is None


def test_record_ack_unblocks_next_trigger():
    d, node_id, run = _new_sweep_run(interval_minutes=15)  # K=1
    d.maybe_trigger_downlink_test("aaaa000000000001", 1)
    assert d.maybe_trigger_downlink_test("aaaa000000000001", 2) is None  # still pending

    d.record_downlink_test_ack("aaaa000000000001", True)

    assert d.maybe_trigger_downlink_test("aaaa000000000001", 3) is not None  # free again


def test_record_ack_attributed_to_sf_active_when_sent_not_when_acked():
    """The pending downlink was sent while SF7 was current; the sweep then
    advances to SF9 before the ack arrives — the ack must still count
    against SF7, not SF9 (Class A: ack can arrive well after the send)."""
    d, node_id, run = _new_sweep_run(interval_minutes=15)  # K=1, sf7
    d.maybe_trigger_downlink_test("aaaa000000000001", 1)  # sent under SF7

    d.advance_run_segment(run["id"], 1, "2026-01-01T00:00:00+00:00")  # now SF9

    d.record_downlink_test_ack("aaaa000000000001", True)

    counts = parse_dl_counts(d.get_run(run["id"])["dl_counts"])
    assert counts["by_sf"]["7"] == {"sent": 1, "acked": 1}
    assert "9" not in counts["by_sf"]


# ---------------------------------------------------------------------------
# rf_frame / rf_stat / get_rf_environment — RF-environment survey (F-0006)
#
# The survey panel is a view over this persisted log, not over transient
# in-memory state — these tests cover the DB layer directly (state.py's
# orchestration of *when* to write is covered in test_state.py).
# ---------------------------------------------------------------------------


def test_record_rf_frame_data_row():
    d = _new_db()
    d.record_rf_frame(
        dev_addr="26ccbbaa",
        network="The Things Network",
        channel=0,
        sf=7,
        rssi=-80,
        snr=-5.0,
        mtype=2,
    )
    rows = d.list_rf_frames()
    assert len(rows) == 1
    row = rows[0]
    assert row["dev_addr"] == "26ccbbaa"
    assert row["network"] == "The Things Network"
    assert row["channel"] == 0
    assert row["sf"] == 7
    assert row["rssi"] == -80
    assert row["snr"] == -5.0
    assert row["mtype"] == 2
    assert row["join_deveui"] is None
    assert row["vendor"] is None
    assert row["ts"]  # non-empty ISO timestamp


def test_record_rf_frame_join_row():
    d = _new_db()
    d.record_rf_frame(
        dev_addr=None,
        network=None,
        channel=1,
        sf=9,
        rssi=-90,
        snr=None,
        mtype=0,
        join_deveui="a84041aabbccddee",
        join_joineui="0000000000000000",
        vendor="Dragino",
    )
    rows = d.list_rf_frames()
    assert len(rows) == 1
    row = rows[0]
    assert row["dev_addr"] is None
    assert row["mtype"] == 0
    assert row["join_deveui"] == "a84041aabbccddee"
    assert row["join_joineui"] == "0000000000000000"
    assert row["vendor"] == "Dragino"


def test_list_rf_frames_ordered_oldest_first():
    d = _new_db()
    for i in range(3):
        d.record_rf_frame(
            dev_addr=f"{i:08x}", network=None, channel=0, sf=7,
            rssi=-80, snr=None, mtype=2,
        )
    rows = d.list_rf_frames()
    assert [r["dev_addr"] for r in rows] == ["00000000", "00000001", "00000002"]


def test_list_rf_frames_columns_match_csv_columns():
    d = _new_db()
    d.record_rf_frame(dev_addr="aaaaaaaa", network=None, channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    row = d.list_rf_frames()[0]
    assert set(row.keys()) == set(RF_FRAME_COLUMNS)


def test_increment_rf_stat_starts_at_zero_and_accumulates():
    d = _new_db()
    assert d.get_rf_stat("own_frames") == 0
    assert d.increment_rf_stat("own_frames") == 1
    assert d.increment_rf_stat("own_frames") == 2
    assert d.get_rf_stat("own_frames") == 2


def test_increment_rf_stat_by_custom_amount():
    d = _new_db()
    assert d.increment_rf_stat("own_frames", by=5) == 5
    assert d.increment_rf_stat("own_frames", by=3) == 8


def test_get_rf_stat_unknown_key_returns_zero():
    d = _new_db()
    assert d.get_rf_stat("nonexistent") == 0


def test_get_rf_environment_empty_initially():
    d = _new_db()
    env = d.get_rf_environment()
    assert env["own_frames"] == 0
    assert env["foreign_frames"] == 0
    assert env["foreign_devices"] == {}
    assert env["networks"] == {}
    assert env["vendors"] == {}
    assert env["mtype_counts"] == {"join": 0, "data_up": 0, "data_down": 0, "other": 0}
    assert env["channel_sf_matrix"] == {}
    assert env["frames_per_min"] == 0.0
    assert env["frames_per_min_sparkline"] == [0] * 10


def test_get_rf_environment_distinct_devices_latest_row_wins():
    d = _new_db()
    d.record_rf_frame(dev_addr="aaaaaaaa", network="other", channel=0, sf=7, rssi=-90, snr=-8.0, mtype=2)
    d.record_rf_frame(dev_addr="aaaaaaaa", network="other", channel=2, sf=9, rssi=-70, snr=2.0, mtype=2)

    env = d.get_rf_environment()
    assert len(env["foreign_devices"]) == 1
    entry = env["foreign_devices"]["aaaaaaaa"]
    assert entry["frames"] == 2
    assert entry["last_channel"] == 2  # the SECOND (latest) row, not the first
    assert entry["last_sf"] == 9
    assert entry["last_rssi"] == -70
    assert entry["last_snr"] == 2.0


def test_get_rf_environment_networks_rollup():
    d = _new_db()
    d.record_rf_frame(dev_addr="aaaaaaaa", network="The Things Network", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    d.record_rf_frame(dev_addr="bbbbbbbb", network="The Things Network", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    d.record_rf_frame(dev_addr="cccccccc", network="private/experimental", channel=1, sf=8, rssi=-80, snr=None, mtype=2)

    env = d.get_rf_environment()
    assert env["networks"] == {
        "The Things Network": {"devices": 2, "frames": 2},
        "private/experimental": {"devices": 1, "frames": 1},
    }


def test_get_rf_environment_channel_sf_matrix():
    d = _new_db()
    d.record_rf_frame(dev_addr="aaaaaaaa", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    d.record_rf_frame(dev_addr="aaaaaaaa", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    d.record_rf_frame(dev_addr="bbbbbbbb", network="other", channel=3, sf=12, rssi=-80, snr=None, mtype=2)

    env = d.get_rf_environment()
    assert env["channel_sf_matrix"] == {"ch0_sf7": 2, "ch3_sf12": 1}


def test_get_rf_environment_vendors_from_joins():
    d = _new_db()
    d.record_rf_frame(
        dev_addr=None, network=None, channel=0, sf=7, rssi=-90, snr=None, mtype=0,
        join_deveui="a84041aabbccddee", join_joineui="0" * 16, vendor="Dragino",
    )
    d.record_rf_frame(
        dev_addr=None, network=None, channel=0, sf=7, rssi=-90, snr=None, mtype=0,
        join_deveui="a84041112233ffff", join_joineui="0" * 16, vendor="Dragino",
    )
    d.record_rf_frame(
        dev_addr=None, network=None, channel=0, sf=7, rssi=-90, snr=None, mtype=0,
        join_deveui="24e124aabbccddee", join_joineui="0" * 16, vendor="Milesight",
    )

    env = d.get_rf_environment()
    assert env["vendors"] == {
        "a84041": {"name": "Dragino", "joins": 2},
        "24e124": {"name": "Milesight", "joins": 1},
    }


def test_get_rf_environment_mtype_counts():
    d = _new_db()
    d.record_rf_frame(dev_addr=None, network=None, channel=0, sf=7, rssi=-90, snr=None, mtype=0,
                       join_deveui="a84041aabbccddee", vendor="Dragino")
    d.record_rf_frame(dev_addr="aaaaaaaa", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    d.record_rf_frame(dev_addr="bbbbbbbb", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=4)
    d.record_rf_frame(dev_addr="cccccccc", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=3)
    d.record_rf_frame(dev_addr="dddddddd", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=5)

    env = d.get_rf_environment()
    assert env["mtype_counts"] == {"join": 1, "data_up": 2, "data_down": 2, "other": 0}


def test_get_rf_environment_totals_include_joins_in_foreign_frames():
    """foreign_frames counts every persisted rf_frame row, including
    foreign join-requests — a deliberate, broader definition than the
    old in-memory coex_foreign_frames counter (data frames only)."""
    d = _new_db()
    d.record_rf_frame(dev_addr=None, network=None, channel=0, sf=7, rssi=-90, snr=None, mtype=0,
                       join_deveui="a84041aabbccddee", vendor="Dragino")
    d.record_rf_frame(dev_addr="aaaaaaaa", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)

    env = d.get_rf_environment()
    assert env["foreign_frames"] == 2
    assert env["own_frames"] == 0


def test_get_rf_environment_frames_per_min_and_sparkline():
    d = _new_db()
    for i in range(3):
        d.record_rf_frame(dev_addr=f"{i:08x}", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)

    env = d.get_rf_environment()
    assert env["frames_per_min"] > 0
    assert len(env["frames_per_min_sparkline"]) == 10
    assert sum(env["frames_per_min_sparkline"]) == 3
    assert env["frames_per_min_sparkline"][-1] == 3  # all just happened -> most-recent bucket


def test_get_rf_environment_own_frames_from_rf_stat():
    d = _new_db()
    d.increment_rf_stat("own_frames", by=4)
    env = d.get_rf_environment()
    assert env["own_frames"] == 4


def test_get_rf_environment_survives_a_simulated_restart():
    """Re-opening a NEW Database instance against the SAME file must see
    everything the previous instance wrote — this is what makes the panel
    survive a cockpit restart."""
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    d1 = Database(path)
    d1.init_schema()
    d1.record_rf_frame(dev_addr="aaaaaaaa", network="The Things Network", channel=0, sf=7,
                        rssi=-80, snr=-5.0, mtype=2)
    d1.increment_rf_stat("own_frames", by=2)

    d2 = Database(path)  # simulates a fresh process re-opening /data/cockpit.db
    d2.init_schema()

    env = d2.get_rf_environment()
    assert env["own_frames"] == 2
    assert env["foreign_frames"] == 1
    assert len(env["foreign_devices"]) == 1
    assert len(d2.list_rf_frames()) == 1


def test_rf_frame_retention_trims_oldest(monkeypatch):
    from app import db as db_module

    monkeypatch.setattr(db_module, "RF_FRAME_RETENTION_MAX", 3)
    monkeypatch.setattr(db_module, "_RF_FRAME_TRIM_EVERY", 1)  # trim on every insert for the test

    d = _new_db()
    for i in range(5):
        d.record_rf_frame(dev_addr=f"{i:08x}", network="other", channel=0, sf=7,
                           rssi=-80, snr=None, mtype=2)

    rows = d.list_rf_frames()
    assert len(rows) == 3
    assert [r["dev_addr"] for r in rows] == ["00000002", "00000003", "00000004"]


def test_rf_frame_retention_noop_under_cap(monkeypatch):
    from app import db as db_module

    monkeypatch.setattr(db_module, "RF_FRAME_RETENTION_MAX", 100)
    monkeypatch.setattr(db_module, "_RF_FRAME_TRIM_EVERY", 1)

    d = _new_db()
    for i in range(5):
        d.record_rf_frame(dev_addr=f"{i:08x}", network="other", channel=0, sf=7,
                           rssi=-80, snr=None, mtype=2)

    assert len(d.list_rf_frames()) == 5  # well under the cap — nothing trimmed


def test_rf_frame_retention_default_is_generous():
    assert RF_FRAME_RETENTION_MAX >= 100_000


# ---------------------------------------------------------------------------
# get_rf_environment — traffic timeline (24 h, hourly, zero-filled),
# recent_frames (live log), sf_distribution, rssi_distribution
# ---------------------------------------------------------------------------


def _insert_frame_at(d, ts, dev_addr="aaaaaaaa", sf=7, rssi=-90, mtype=2):
    """Insert a rf_frame row at an exact timestamp — bypasses
    record_rf_frame (which always stamps "now") so timeline/window tests
    can be deterministic without depending on wall-clock time."""
    d._conn.execute(
        "INSERT INTO rf_frame "
        "(ts, dev_addr, network, channel, sf, rssi, snr, mtype, join_deveui, join_joineui, vendor) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts.isoformat(timespec="seconds"), dev_addr, "other", 0, sf, rssi, None, mtype, None, None, None),
    )
    d._conn.commit()


_NOW = datetime.datetime(2026, 7, 9, 14, 30, 0, tzinfo=datetime.timezone.utc)


def test_get_rf_environment_now_defaults_to_current_time():
    """Without an explicit now=, get_rf_environment must still work (uses
    the real wall clock) — the deterministic tests below always pass one."""
    d = _new_db()
    env = d.get_rf_environment()
    assert len(env["timeline"]) == RF_TIMELINE_HOURS


def test_timeline_has_24_zero_filled_buckets_when_empty():
    d = _new_db()
    env = d.get_rf_environment(now=_NOW)
    timeline = env["timeline"]
    assert len(timeline) == RF_TIMELINE_HOURS == 24
    assert all(b["count"] == 0 for b in timeline)
    # oldest -> newest: each bucket is exactly 1h after the previous one.
    for i in range(1, len(timeline)):
        prev = datetime.datetime.fromisoformat(timeline[i - 1]["bucket"])
        cur = datetime.datetime.fromisoformat(timeline[i]["bucket"])
        assert cur - prev == datetime.timedelta(hours=1)
    # the newest bucket starts at the current hour.
    assert timeline[-1]["bucket"] == _NOW.replace(minute=0, second=0, microsecond=0).isoformat(
        timespec="seconds"
    )


def test_timeline_buckets_a_frame_in_the_current_hour():
    d = _new_db()
    _insert_frame_at(d, _NOW)  # same hour as "now"
    env = d.get_rf_environment(now=_NOW)
    timeline = env["timeline"]
    assert timeline[-1]["count"] == 1  # newest (current-hour) bucket
    assert sum(b["count"] for b in timeline) == 1


def test_timeline_buckets_a_frame_a_few_hours_ago():
    d = _new_db()
    _insert_frame_at(d, _NOW - datetime.timedelta(hours=3, minutes=10))
    env = d.get_rf_environment(now=_NOW)
    timeline = env["timeline"]
    # 3 whole hours before the current-hour bucket -> 3rd-from-last bucket.
    assert timeline[-4]["count"] == 1
    assert sum(b["count"] for b in timeline) == 1


def test_timeline_excludes_frames_older_than_24h_window():
    d = _new_db()
    hour_start = _NOW.replace(minute=0, second=0, microsecond=0)
    _insert_frame_at(d, hour_start - datetime.timedelta(hours=24))  # just outside the window
    env = d.get_rf_environment(now=_NOW)
    assert sum(b["count"] for b in env["timeline"]) == 0


def test_timeline_includes_the_oldest_in_window_hour():
    d = _new_db()
    hour_start = _NOW.replace(minute=0, second=0, microsecond=0)
    _insert_frame_at(d, hour_start - datetime.timedelta(hours=23))  # oldest bucket, still in window
    env = d.get_rf_environment(now=_NOW)
    timeline = env["timeline"]
    assert timeline[0]["count"] == 1  # the oldest (first) bucket
    assert sum(b["count"] for b in timeline) == 1


def test_recent_frames_empty_initially():
    d = _new_db()
    env = d.get_rf_environment(now=_NOW)
    assert env["recent_frames"] == []


def test_recent_frames_newest_first():
    d = _new_db()
    for i in range(3):
        _insert_frame_at(d, _NOW - datetime.timedelta(minutes=10 - i), dev_addr=f"{i:08x}")
    env = d.get_rf_environment(now=_NOW)
    frames = env["recent_frames"]
    assert [f["dev_addr"] for f in frames] == ["00000002", "00000001", "00000000"]


def test_recent_frames_limited_to_20():
    d = _new_db()
    for i in range(30):
        _insert_frame_at(d, _NOW - datetime.timedelta(minutes=30 - i), dev_addr=f"{i:08x}")
    env = d.get_rf_environment(now=_NOW)
    frames = env["recent_frames"]
    assert len(frames) == RF_RECENT_FRAMES_LIMIT == 20
    # newest 20 (dev_addr 10..29), newest first.
    assert frames[0]["dev_addr"] == "0000001d"  # 29
    assert frames[-1]["dev_addr"] == "0000000a"  # 10


def test_recent_frames_field_shape():
    d = _new_db()
    _insert_frame_at(d, _NOW, dev_addr="aaaaaaaa", sf=9, rssi=-95, mtype=2)
    env = d.get_rf_environment(now=_NOW)
    frame = env["recent_frames"][0]
    assert set(frame.keys()) == {"ts", "dev_addr", "network", "sf", "rssi", "mtype"}
    assert frame["dev_addr"] == "aaaaaaaa"
    assert frame["sf"] == 9
    assert frame["rssi"] == -95
    assert frame["mtype"] == 2


def test_recent_frames_includes_join_requests():
    d = _new_db()
    d.record_rf_frame(
        dev_addr=None, network=None, channel=0, sf=7, rssi=-90, snr=None, mtype=0,
        join_deveui="a84041aabbccddee", vendor="Dragino",
    )
    env = d.get_rf_environment()
    assert len(env["recent_frames"]) == 1
    assert env["recent_frames"][0]["dev_addr"] is None


def test_sf_distribution_all_sfs_present_with_zeros():
    d = _new_db()
    env = d.get_rf_environment(now=_NOW)
    assert env["sf_distribution"] == {"7": 0, "8": 0, "9": 0, "10": 0, "11": 0, "12": 0}


def test_sf_distribution_counts_by_sf():
    d = _new_db()
    _insert_frame_at(d, _NOW, dev_addr="aaaaaaaa", sf=7)
    _insert_frame_at(d, _NOW, dev_addr="bbbbbbbb", sf=7)
    _insert_frame_at(d, _NOW, dev_addr="cccccccc", sf=12)
    env = d.get_rf_environment(now=_NOW)
    assert env["sf_distribution"] == {"7": 2, "8": 0, "9": 0, "10": 0, "11": 0, "12": 1}


def test_sf_distribution_excludes_join_requests():
    """Matches channel_sf_matrix's existing scope (data frames only) so the
    SF distribution agrees with the heatmap it's displayed alongside."""
    d = _new_db()
    d.record_rf_frame(
        dev_addr=None, network=None, channel=0, sf=9, rssi=-90, snr=None, mtype=0,
        join_deveui="a84041aabbccddee", vendor="Dragino",
    )
    env = d.get_rf_environment()
    assert env["sf_distribution"]["9"] == 0


def test_rssi_distribution_empty_initially():
    d = _new_db()
    env = d.get_rf_environment(now=_NOW)
    assert env["rssi_distribution"] == [
        {"label": "≥ -80 dBm", "count": 0},
        {"label": "-80…-100 dBm", "count": 0},
        {"label": "-100…-115 dBm", "count": 0},
        {"label": "< -115 dBm", "count": 0},
    ]


def test_rssi_distribution_bucket_boundaries():
    d = _new_db()
    # exact boundary values, one per bucket + one comfortably inside each.
    for i, rssi in enumerate([-70, -80, -90, -100, -110, -115, -120]):
        _insert_frame_at(d, _NOW, dev_addr=f"{i:08x}", rssi=rssi)
    env = d.get_rf_environment(now=_NOW)
    by_label = {b["label"]: b["count"] for b in env["rssi_distribution"]}
    # strong (>= -80): -70, -80  -> 2
    assert by_label["≥ -80 dBm"] == 2
    # -80..-100 (< -80, >= -100): -90, -100 -> 2
    assert by_label["-80…-100 dBm"] == 2
    # -100..-115 (< -100, >= -115): -110, -115 -> 2
    assert by_label["-100…-115 dBm"] == 2
    # weak (< -115): -120 -> 1
    assert by_label["< -115 dBm"] == 1
    assert sum(by_label.values()) == 7


def test_rssi_distribution_excludes_join_requests():
    d = _new_db()
    d.record_rf_frame(
        dev_addr=None, network=None, channel=0, sf=7, rssi=-70, snr=None, mtype=0,
        join_deveui="a84041aabbccddee", vendor="Dragino",
    )
    env = d.get_rf_environment()
    assert env["rssi_distribution"][0]["count"] == 0


# ---------------------------------------------------------------------------
# list_rf_frames — limit / newest_first (used by get_rf_environment's live
# frame-log; default behavior for the CSV export stays unchanged)
# ---------------------------------------------------------------------------


def test_list_rf_frames_default_unchanged():
    d = _new_db()
    for i in range(3):
        d.record_rf_frame(dev_addr=f"{i:08x}", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    rows = d.list_rf_frames()
    assert [r["dev_addr"] for r in rows] == ["00000000", "00000001", "00000002"]


def test_list_rf_frames_newest_first():
    d = _new_db()
    for i in range(3):
        d.record_rf_frame(dev_addr=f"{i:08x}", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    rows = d.list_rf_frames(newest_first=True)
    assert [r["dev_addr"] for r in rows] == ["00000002", "00000001", "00000000"]


def test_list_rf_frames_limit():
    d = _new_db()
    for i in range(5):
        d.record_rf_frame(dev_addr=f"{i:08x}", network="other", channel=0, sf=7, rssi=-80, snr=None, mtype=2)
    rows = d.list_rf_frames(limit=2, newest_first=True)
    assert [r["dev_addr"] for r in rows] == ["00000004", "00000003"]


# ---------------------------------------------------------------------------
# get_rf_environment — full snapshot shape includes the new fields
# ---------------------------------------------------------------------------


def test_get_rf_environment_shape_includes_new_fields():
    d = _new_db()
    env = d.get_rf_environment(now=_NOW)
    assert set(env.keys()) == {
        "own_frames", "foreign_frames", "foreign_devices", "networks", "vendors",
        "mtype_counts", "channel_sf_matrix", "frames_per_min", "frames_per_min_sparkline",
        "timeline", "recent_frames", "sf_distribution", "rssi_distribution",
    }


# ---------------------------------------------------------------------------
# floorplan + placement map position — Map / Placement Editor (F-0008)
# ---------------------------------------------------------------------------


def test_create_floorplan_returns_row():
    d = _new_db()
    fp = d.create_floorplan("Building A", "floorplan_20260101T000000Z.jpg")
    assert fp["id"] is not None
    assert fp["name"] == "Building A"
    assert fp["image_filename"] == "floorplan_20260101T000000Z.jpg"
    assert fp["uploaded_at"]


def test_get_current_floorplan_none_initially():
    d = _new_db()
    assert d.get_current_floorplan() is None


def test_get_current_floorplan_is_the_most_recent_upload():
    d = _new_db()
    d.create_floorplan("Old map", "old.jpg")
    newest = d.create_floorplan("New map", "new.jpg")
    current = d.get_current_floorplan()
    assert current["id"] == newest["id"]
    assert current["name"] == "New map"


def test_get_floorplan_by_id():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    assert d.get_floorplan(fp["id"])["name"] == "Building A"


def test_get_floorplan_unknown_returns_none():
    d = _new_db()
    assert d.get_floorplan(999) is None


def test_create_placement_stores_map_position():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")

    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi", floorplan_id=fp["id"], map_x=0.25, map_y=0.5)

    p = d.get_active_placement(node_id)
    assert p["floorplan_id"] == fp["id"]
    assert p["map_x"] == 0.25
    assert p["map_y"] == 0.5


def test_create_placement_without_map_position_leaves_it_null():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")

    p = d.get_active_placement(node_id)
    assert p["floorplan_id"] is None
    assert p["map_x"] is None
    assert p["map_y"] is None


def test_set_active_placement_map_position_updates_the_active_placement():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")

    ok = d.set_active_placement_map_position(node_id, fp["id"], 0.25, 0.5)
    assert ok is True

    p = d.get_active_placement(node_id)
    assert p["floorplan_id"] == fp["id"]
    assert p["map_x"] == 0.25
    assert p["map_y"] == 0.5


def test_set_active_placement_map_position_drag_overwrites_previous_value():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")

    d.set_active_placement_map_position(node_id, fp["id"], 0.1, 0.1)
    d.set_active_placement_map_position(node_id, fp["id"], 0.9, 0.2)  # dragged elsewhere

    p = d.get_active_placement(node_id)
    assert p["map_x"] == 0.9
    assert p["map_y"] == 0.2


def test_set_active_placement_map_position_does_not_create_a_new_placement():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    original = d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")

    d.set_active_placement_map_position(node_id, fp["id"], 0.5, 0.5)

    p = d.get_active_placement(node_id)
    assert p["id"] == original  # same placement row, just updated in place


def test_set_active_placement_map_position_false_when_no_active_placement():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")  # never placed
    assert d.set_active_placement_map_position(node_id, fp["id"], 0.5, 0.5) is False


def test_clear_active_placement_map_position_clears_it():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi", floorplan_id=fp["id"], map_x=0.5, map_y=0.5)

    ok = d.clear_active_placement_map_position(node_id)
    assert ok is True

    p = d.get_active_placement(node_id)
    assert p["floorplan_id"] is None
    assert p["map_x"] is None
    assert p["map_y"] is None


def test_clear_active_placement_map_position_false_when_no_active_placement():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")  # never placed
    assert d.clear_active_placement_map_position(node_id) is False


def test_clear_active_placement_map_position_noop_when_nothing_set():
    d = _new_db()
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")  # no map position
    assert d.clear_active_placement_map_position(node_id) is True  # still "success"


def test_list_active_map_positions_joins_node_name_and_kind():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    gw_id, _ = d.upsert_node("gateway", "gw", "7076ff0064071a3d")
    dev_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(gw_id, "EG", "flur", "", "", "", floorplan_id=fp["id"], map_x=0.5, map_y=0.5)
    d.create_placement(dev_id, "3OG", "R301", "", "", "3dbi", floorplan_id=fp["id"], map_x=0.2, map_y=0.3)

    markers = {m["node_id"]: m for m in d.list_active_map_positions(fp["id"])}
    assert markers[gw_id]["name"] == "gw"
    assert markers[gw_id]["kind"] == "gateway"
    assert markers[dev_id]["name"] == "d1"
    assert markers[dev_id]["kind"] == "device"
    assert markers[dev_id]["x"] == 0.2
    assert markers[dev_id]["y"] == 0.3


def test_list_active_map_positions_empty_for_unknown_floorplan():
    d = _new_db()
    assert d.list_active_map_positions(999) == []


def test_list_active_map_positions_excludes_placements_without_a_position():
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi")  # no map position

    assert d.list_active_map_positions(fp["id"]) == []


def test_list_active_map_positions_excludes_no_longer_active_placements():
    """Relocating (superseding the placement) must drop the old position
    from the map — only the CURRENT active placement counts."""
    d = _new_db()
    fp = d.create_floorplan("Building A", "a.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi", floorplan_id=fp["id"], map_x=0.5, map_y=0.5)
    d.create_placement(node_id, "1OG", "R2", "", "", "3dbi")  # relocate, no position this time

    assert d.list_active_map_positions(fp["id"]) == []


def test_list_active_map_positions_scoped_to_its_own_floorplan():
    """A position captured against an older (no-longer-current) floorplan
    must not leak into another floorplan's marker list."""
    d = _new_db()
    fp1 = d.create_floorplan("Old map", "old.jpg")
    fp2 = d.create_floorplan("New map", "new.jpg")
    node_id, _ = d.upsert_node("device", "d1", "aaaa000000000001")
    d.create_placement(node_id, "3OG", "R301", "", "", "3dbi", floorplan_id=fp1["id"], map_x=0.5, map_y=0.5)

    assert len(d.list_active_map_positions(fp1["id"])) == 1
    assert d.list_active_map_positions(fp2["id"]) == []


def test_map_position_survives_a_simulated_restart():
    """Re-opening a NEW Database instance against the SAME file must see
    everything the previous instance wrote."""
    path = os.path.join(tempfile.mkdtemp(), "test.db")
    d1 = Database(path)
    d1.init_schema()
    fp = d1.create_floorplan("Building A", "a.jpg")
    node_id, _ = d1.upsert_node("device", "d1", "aaaa000000000001")
    d1.create_placement(node_id, "3OG", "R301", "", "", "3dbi", floorplan_id=fp["id"], map_x=0.4, map_y=0.6)

    d2 = Database(path)  # simulates a fresh process re-opening /data/cockpit.db
    d2.init_schema()

    current = d2.get_current_floorplan()
    assert current is not None
    assert current["name"] == "Building A"
    markers = d2.list_active_map_positions(current["id"])
    assert len(markers) == 1
    assert markers[0]["x"] == 0.4
    assert markers[0]["y"] == 0.6
