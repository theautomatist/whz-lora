"""db.py — SQLite persistence for the Feldmess-Workflow (F-0006).

Stdlib sqlite3 only (no new heavy dependency). One Database instance is
shared across the asyncio event loop, the FastAPI threadpool (sync `def`
handlers) and the MQTT ingest thread — every method acquires an internal
RLock, and the underlying connection is opened with
check_same_thread=False, so the class is safe to call from any thread.

Schema (see _SCHEMA below):
  node       — a device or the gateway; identified by a unique EUI
  placement  — a node's physical location over time; "active" == ended_at IS NULL
  photo      — up to MAX_PHOTOS_PER_PLACEMENT images attached to a placement
  run        — one CSV-recording session for a device, tied to the device's
               and the gateway's placement at the time it started. Phase B
               adds an optional timed per-device SF-sweep to a run
               (planned_seconds/sf_schedule/interval_minutes/segment_index/
               segment_started_at) — NULL/0 on a run means "no sweep",
               behaving exactly like a Phase A fixed run.

No GPS anywhere — placements are floor/room/description, not coordinates.
"""
import csv
import datetime
import json
import logging
import os
import sqlite3
import threading
from typing import Optional

logger = logging.getLogger(__name__)

MAX_PHOTOS_PER_PLACEMENT = 3

# CSV schema for per-run recordings (written by record_uplink_for_run).
CSV_COLUMNS = [
    "timestamp_utc",
    "dev_eui",
    "run_id",
    "node_name",
    "floor",
    "room",
    "description",
    "antenna",
    "phase",
    "gateway_desc",
    "rssi_dbm",
    "snr_db",
    "sf",
    "freq_hz",
    "f_cnt",
    "gw_eui",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS node (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT NOT NULL,          -- 'device' | 'gateway'
    name       TEXT NOT NULL,
    eui        TEXT UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS placement (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     INTEGER NOT NULL REFERENCES node(id),
    floor       TEXT NOT NULL DEFAULT '',
    room        TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    antenna     TEXT NOT NULL DEFAULT '',
    started_at  TEXT NOT NULL,
    ended_at    TEXT                   -- NULL == active placement
);
CREATE INDEX IF NOT EXISTS idx_placement_node ON placement(node_id);

CREATE TABLE IF NOT EXISTS photo (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    placement_id INTEGER NOT NULL REFERENCES placement(id),
    filename     TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_photo_placement ON photo(placement_id);

CREATE TABLE IF NOT EXISTS run (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    device_node_id        INTEGER NOT NULL REFERENCES node(id),
    device_placement_id   INTEGER NOT NULL REFERENCES placement(id),
    gateway_placement_id  INTEGER NOT NULL REFERENCES placement(id),
    phase                 TEXT NOT NULL,
    csv_path              TEXT NOT NULL DEFAULT '',
    started_at            TEXT NOT NULL,
    ended_at              TEXT,
    status                TEXT NOT NULL,   -- 'running' | 'done' | 'aborted'
    reason                TEXT,
    packets               INTEGER NOT NULL DEFAULT 0,
    -- Phase B — optional timed SF-sweep; NULL/0 = no sweep (Phase A run).
    planned_seconds       INTEGER,
    sf_schedule           TEXT,             -- JSON [{"sf":7,"seconds":28800}, ...] or NULL
    interval_minutes      INTEGER,
    segment_index         INTEGER NOT NULL DEFAULT 0,
    segment_started_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_device ON run(device_node_id);
CREATE INDEX IF NOT EXISTS idx_run_status ON run(status);
"""

# NOTE — schema deviation from the original brief: a `packets INTEGER` column
# was added to `run`. Endpoints need a live packet count (GET /api/nodes,
# the gateway-move guard, GET /api/runs) and computing it by re-reading each
# run's CSV file on every request is needless I/O; a counter maintained by
# record_uplink_for_run is the KISS choice.

# Additive Phase B migration for databases created before the SF-sweep
# columns existed. _SCHEMA above already creates them on a fresh database
# (CREATE TABLE IF NOT EXISTS is a no-op there); this covers upgrades of an
# existing /data/cockpit.db. Guarded by a PRAGMA table_info check, so it is
# always safe to call — a no-op once the columns are present.
_RUN_MIGRATION_COLUMNS: list[tuple[str, str]] = [
    ("planned_seconds", "INTEGER"),
    ("sf_schedule", "TEXT"),
    ("interval_minutes", "INTEGER"),
    ("segment_index", "INTEGER NOT NULL DEFAULT 0"),
    ("segment_started_at", "TEXT"),
]


class Database:
    """Thin synchronous SQLite wrapper. All methods are thread-safe."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.RLock()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate_run_columns()
            self._conn.commit()

    def _migrate_run_columns(self) -> None:
        """Additive `ALTER TABLE run ADD COLUMN` for Phase B, guarded by a
        schema check (PRAGMA table_info) — a no-op when the columns already
        exist (fresh databases get them straight from _SCHEMA)."""
        existing = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(run)").fetchall()
        }
        for name, decl in _RUN_MIGRATION_COLUMNS:
            if name not in existing:
                self._conn.execute(f"ALTER TABLE run ADD COLUMN {name} {decl}")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    # ------------------------------------------------------------------
    # node
    # ------------------------------------------------------------------

    def upsert_node(self, kind: str, name: str, eui: str) -> tuple[int, bool]:
        """Find-or-create a node by its unique EUI. Returns (node_id, created)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, name FROM node WHERE eui = ?", (eui,)
            ).fetchone()
            if row:
                if row["name"] != name:
                    self._conn.execute(
                        "UPDATE node SET name = ? WHERE id = ?", (name, row["id"])
                    )
                    self._conn.commit()
                return row["id"], False
            cur = self._conn.execute(
                "INSERT INTO node (kind, name, eui, created_at) VALUES (?, ?, ?, ?)",
                (kind, name, eui, self._now()),
            )
            self._conn.commit()
            return cur.lastrowid, True

    def get_node(self, node_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM node WHERE id = ?", (node_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_node_by_eui(self, eui: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM node WHERE eui = ?", (eui,)
            ).fetchone()
            return dict(row) if row else None

    def list_nodes(self, kind: Optional[str] = None) -> list[dict]:
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT * FROM node WHERE kind = ? ORDER BY id", (kind,)
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM node ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # placement
    # ------------------------------------------------------------------

    def get_active_placement(self, node_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM placement WHERE node_id = ? AND ended_at IS NULL",
                (node_id,),
            ).fetchone()
            return dict(row) if row else None

    def create_placement(
        self,
        node_id: int,
        floor: str,
        room: str,
        description: str,
        note: str,
        antenna: str,
    ) -> int:
        """Close the node's current active placement (if any) and open a new one."""
        with self._lock:
            now = self._now()
            self._conn.execute(
                "UPDATE placement SET ended_at = ? WHERE node_id = ? AND ended_at IS NULL",
                (now, node_id),
            )
            cur = self._conn.execute(
                "INSERT INTO placement "
                "(node_id, floor, room, description, note, antenna, started_at, ended_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                (node_id, floor, room, description, note, antenna, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_placement(self, placement_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM placement WHERE id = ?", (placement_id,)
            ).fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # photo
    # ------------------------------------------------------------------

    def count_photos(self, placement_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM photo WHERE placement_id = ?",
                (placement_id,),
            ).fetchone()
            return row["c"]

    def add_photo(self, placement_id: int, filename: str) -> int:
        """Insert a photo row. Raises ValueError if the placement already has
        MAX_PHOTOS_PER_PLACEMENT photos (caller maps this to HTTP 409)."""
        with self._lock:
            if self.count_photos(placement_id) >= MAX_PHOTOS_PER_PLACEMENT:
                raise ValueError(
                    f"placement {placement_id} already has "
                    f"{MAX_PHOTOS_PER_PLACEMENT} photos"
                )
            cur = self._conn.execute(
                "INSERT INTO photo (placement_id, filename, created_at) VALUES (?, ?, ?)",
                (placement_id, filename, self._now()),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_photo(self, photo_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM photo WHERE id = ?", (photo_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_photos(self, placement_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM photo WHERE placement_id = ? ORDER BY id",
                (placement_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------

    def get_active_run(self, device_node_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM run WHERE device_node_id = ? AND status = 'running'",
                (device_node_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_run(self, run_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM run WHERE id = ?", (run_id,)
            ).fetchone()
            return dict(row) if row else None

    def get_last_run(self, device_node_id: int) -> Optional[dict]:
        """Return the device's most recent run (any status), or None if it
        has never run. Used alongside get_active_run so the frontend can
        keep showing a just-completed sweep's summary (done=True)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM run WHERE device_node_id = ? ORDER BY id DESC LIMIT 1",
                (device_node_id,),
            ).fetchone()
            return dict(row) if row else None

    def start_run(
        self,
        device_node_id: int,
        device_placement_id: int,
        gateway_placement_id: int,
        phase: str,
        data_dir: str,
        dev_eui: str,
        planned_seconds: Optional[int] = None,
        sf_schedule: Optional[list] = None,
        interval_minutes: Optional[int] = None,
    ) -> dict:
        """Insert a new 'running' run row, write its CSV file + header, return it.

        csv_path = <data_dir>/run_<id>_<dev_eui>_<UTC compact timestamp>.csv

        Phase B: when *sf_schedule* (a list of {"sf": int, "seconds": int})
        is given, the run also gets planned_seconds/interval_minutes stored
        and segment_index=0/segment_started_at=now — the background
        scheduler (see scheduler.py + main.py) advances it over time. When
        *sf_schedule* is None/empty, the row behaves exactly like a Phase A
        fixed run (no sweep) — full backward compatibility.
        """
        with self._lock:
            now = self._now()
            sf_schedule_json = json.dumps(sf_schedule) if sf_schedule else None
            segment_started_at = now if sf_schedule else None
            cur = self._conn.execute(
                "INSERT INTO run "
                "(device_node_id, device_placement_id, gateway_placement_id, phase, "
                " csv_path, started_at, ended_at, status, reason, packets, "
                " planned_seconds, sf_schedule, interval_minutes, segment_index, segment_started_at) "
                "VALUES (?, ?, ?, ?, '', ?, NULL, 'running', NULL, 0, ?, ?, ?, 0, ?)",
                (
                    device_node_id, device_placement_id, gateway_placement_id, phase, now,
                    planned_seconds, sf_schedule_json, interval_minutes, segment_started_at,
                ),
            )
            run_id = cur.lastrowid

            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            os.makedirs(data_dir, exist_ok=True)
            csv_path = os.path.join(data_dir, f"run_{run_id}_{dev_eui}_{ts}.csv")
            self._conn.execute(
                "UPDATE run SET csv_path = ? WHERE id = ?", (csv_path, run_id)
            )
            self._conn.commit()

            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=CSV_COLUMNS).writeheader()

            row = self._conn.execute(
                "SELECT * FROM run WHERE id = ?", (run_id,)
            ).fetchone()
            return dict(row)

    def stop_run(
        self, run_id: int, status: str = "done", reason: Optional[str] = None
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE run SET ended_at = ?, status = ?, reason = ? WHERE id = ?",
                (self._now(), status, reason, run_id),
            )
            self._conn.commit()

    def advance_run_segment(
        self, run_id: int, segment_index: int, segment_started_at: str
    ) -> None:
        """Phase B: move a running sweep to its next SF segment."""
        with self._lock:
            self._conn.execute(
                "UPDATE run SET segment_index = ?, segment_started_at = ? WHERE id = ?",
                (segment_index, segment_started_at, run_id),
            )
            self._conn.commit()

    def stop_active_run_for_device(
        self, device_node_id: int, status: str = "done", reason: Optional[str] = None
    ) -> Optional[int]:
        """Stop the device's active run, if any. Returns its run_id or None."""
        with self._lock:
            run = self.get_active_run(device_node_id)
            if run is None:
                return None
            self.stop_run(run["id"], status=status, reason=reason)
            return run["id"]

    def list_running_runs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT r.*, n.name AS device_name FROM run r "
                "JOIN node n ON n.id = r.device_node_id "
                "WHERE r.status = 'running' ORDER BY r.id"
            ).fetchall()
            return [dict(r) for r in rows]

    def abort_running_runs(self, reason: str) -> list[dict]:
        """Set every currently-running run to status='aborted'. Returns the
        (pre-abort) list of run rows that were aborted — CSV files/data untouched."""
        with self._lock:
            running = self.list_running_runs()
            now = self._now()
            for r in running:
                self._conn.execute(
                    "UPDATE run SET ended_at = ?, status = 'aborted', reason = ? WHERE id = ?",
                    (now, reason, r["id"]),
                )
            self._conn.commit()
            return running

    def increment_run_packets(self, run_id: int) -> int:
        with self._lock:
            self._conn.execute(
                "UPDATE run SET packets = packets + 1 WHERE id = ?", (run_id,)
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT packets FROM run WHERE id = ?", (run_id,)
            ).fetchone()
            return row["packets"] if row else 0

    def list_runs_for_node(self, node_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT r.*, "
                "dp.floor AS d_floor, dp.room AS d_room, dp.description AS d_description, "
                "gp.description AS g_description "
                "FROM run r "
                "JOIN placement dp ON dp.id = r.device_placement_id "
                "JOIN placement gp ON gp.id = r.gateway_placement_id "
                "WHERE r.device_node_id = ? ORDER BY r.id DESC",
                (node_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Per-run CSV recording (called from MQTT ingest on every uplink)
    # ------------------------------------------------------------------

    def record_uplink_for_run(self, dev_eui: str, metrics: dict) -> Optional[int]:
        """If *dev_eui* has an active run, append a CSV row and bump its
        packet counter. Returns the new packet count, or None if the device
        is unknown or has no active run (a no-op, not an error).
        """
        with self._lock:
            node = self.get_node_by_eui(dev_eui)
            if node is None or node["kind"] != "device":
                return None
            run = self.get_active_run(node["id"])
            if run is None:
                return None

            device_placement = self.get_placement(run["device_placement_id"])
            gateway_placement = self.get_placement(run["gateway_placement_id"])

            row = {
                "timestamp_utc": self._now(),
                "dev_eui": dev_eui,
                "run_id": run["id"],
                "node_name": node["name"],
                "floor": device_placement["floor"] if device_placement else "",
                "room": device_placement["room"] if device_placement else "",
                "description": device_placement["description"] if device_placement else "",
                "antenna": device_placement["antenna"] if device_placement else "",
                "phase": run["phase"],
                "gateway_desc": gateway_placement["description"] if gateway_placement else "",
                "rssi_dbm": metrics.get("rssi_dbm", ""),
                "snr_db": metrics.get("snr_db", ""),
                "sf": metrics.get("sf", ""),
                "freq_hz": metrics.get("freq_hz", ""),
                "f_cnt": metrics.get("f_cnt", ""),
                "gw_eui": metrics.get("gw_eui", ""),
            }

            os.makedirs(os.path.dirname(run["csv_path"]) or ".", exist_ok=True)
            write_header = not os.path.exists(run["csv_path"])
            with open(run["csv_path"], "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                if write_header:
                    writer.writeheader()
                writer.writerow(row)

            return self.increment_run_packets(run["id"])
