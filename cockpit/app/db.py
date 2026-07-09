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
               behaving exactly like a Phase A fixed run. "Trust &
               Sichtbarkeit" adds a per-SF downlink reliability test
               (downlink_test/dl_counts) on top of that — see
               maybe_trigger_downlink_test/record_downlink_test_ack below.
  rf_frame   — append-only log of foreign LoRa traffic seen by the gateway
               (RF-environment survey, F-0006). One row per foreign data
               frame or foreign join-request; see
               CampaignState._record_rf_environment_frame (state.py) for the
               writer and get_rf_environment below for the reader. This is
               what makes the RF-environment panel survive a cockpit
               restart / page reload — the panel is a view over this log,
               not in-memory state. Bounded by RF_FRAME_RETENTION_MAX (see
               _trim_rf_frames).
  rf_stat    — small persistent key/value counter table alongside rf_frame
               (currently just "own_frames") so the own/foreign totals
               also survive a restart.

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

# rf_frame retention — a generous cap so the RF-environment survey log
# cannot grow unbounded over a long campaign, without losing recent data
# prematurely (foreign traffic is currently sparse). Checked/trimmed only
# every _RF_FRAME_TRIM_EVERY inserts, not on every insert, to keep the
# common-path write cheap.
RF_FRAME_RETENTION_MAX = 200_000
_RF_FRAME_TRIM_EVERY = 500

# Column order for the rf_frame CSV export (GET /api/rf-environment/csv).
RF_FRAME_COLUMNS = [
    "id",
    "ts",
    "dev_addr",
    "network",
    "channel",
    "sf",
    "rssi",
    "snr",
    "mtype",
    "join_deveui",
    "join_joineui",
    "vendor",
]

# get_rf_environment: the live frame-log shows the last N foreign frames
# (newest first); the traffic timeline covers a fixed 24 h window bucketed
# by hour.
RF_RECENT_FRAMES_LIMIT = 20
RF_TIMELINE_HOURS = 24

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
    segment_started_at    TEXT,
    -- "Trust & Sichtbarkeit" — per-SF downlink reliability test (confirmed
    -- downlinks). downlink_test defaults ON; dl_counts is JSON
    -- {"by_sf": {"<sf>": {"sent": int, "acked": int}}, "pending_sf": int|null}
    -- — see maybe_trigger_downlink_test/record_downlink_test_ack.
    downlink_test         INTEGER NOT NULL DEFAULT 1,
    dl_counts             TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_device ON run(device_node_id);
CREATE INDEX IF NOT EXISTS idx_run_status ON run(status);

CREATE TABLE IF NOT EXISTS rf_frame (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    dev_addr      TEXT,             -- NULL for join-requests
    network       TEXT,             -- classify_network label; NULL for join-requests
    channel       INTEGER,
    sf            INTEGER,
    rssi          INTEGER,
    snr           REAL,
    mtype         INTEGER NOT NULL,
    join_deveui   TEXT,             -- set only for mtype == 0 (join-request)
    join_joineui  TEXT,
    vendor        TEXT              -- OUI-derived vendor name; join-requests only
);
CREATE INDEX IF NOT EXISTS idx_rf_frame_ts ON rf_frame(ts);
CREATE INDEX IF NOT EXISTS idx_rf_frame_dev_addr ON rf_frame(dev_addr);

CREATE TABLE IF NOT EXISTS rf_stat (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);
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
    ("downlink_test", "INTEGER NOT NULL DEFAULT 1"),
    ("dl_counts", "TEXT"),
]


def parse_dl_counts(raw: Optional[str]) -> dict:
    """Decode run.dl_counts JSON:
    {"by_sf": {"<sf>": {"sent": int, "acked": int}}, "pending_sf": int|None}.
    Empty/None/invalid -> the empty/default shape (never raises).
    """
    if not raw:
        return {"by_sf": {}, "pending_sf": None}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {"by_sf": {}, "pending_sf": None}
    if not isinstance(data, dict):
        return {"by_sf": {}, "pending_sf": None}
    return {"by_sf": data.get("by_sf") or {}, "pending_sf": data.get("pending_sf")}


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
        self._rf_frame_insert_count = 0

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
        downlink_test: bool = True,
    ) -> dict:
        """Insert a new 'running' run row, write its CSV file + header, return it.

        csv_path = <data_dir>/run_<id>_<dev_eui>_<UTC compact timestamp>.csv

        Phase B: when *sf_schedule* (a list of {"sf": int, "seconds": int})
        is given, the run also gets planned_seconds/interval_minutes stored
        and segment_index=0/segment_started_at=now — the background
        scheduler (see scheduler.py + main.py) advances it over time. When
        *sf_schedule* is None/empty, the row behaves exactly like a Phase A
        fixed run (no sweep) — full backward compatibility.

        *downlink_test* (default True) enables the per-SF confirmed-downlink
        reliability test (see maybe_trigger_downlink_test) — it only ever
        actually fires for a sweep run (needs interval_minutes + sf_schedule
        to attribute to an SF), so it is harmless to leave True on a plain
        Phase A run too.
        """
        with self._lock:
            now = self._now()
            sf_schedule_json = json.dumps(sf_schedule) if sf_schedule else None
            segment_started_at = now if sf_schedule else None
            cur = self._conn.execute(
                "INSERT INTO run "
                "(device_node_id, device_placement_id, gateway_placement_id, phase, "
                " csv_path, started_at, ended_at, status, reason, packets, "
                " planned_seconds, sf_schedule, interval_minutes, segment_index, segment_started_at, "
                " downlink_test, dl_counts) "
                "VALUES (?, ?, ?, ?, '', ?, NULL, 'running', NULL, 0, ?, ?, ?, 0, ?, ?, NULL)",
                (
                    device_node_id, device_placement_id, gateway_placement_id, phase, now,
                    planned_seconds, sf_schedule_json, interval_minutes, segment_started_at,
                    1 if downlink_test else 0,
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

    # ------------------------------------------------------------------
    # "Trust & Sichtbarkeit" — per-SF downlink reliability test
    #
    # LoRaWAN Class A: a confirmed downlink can only be *delivered* right
    # after the device's own next uplink, and its MAC-ACK only becomes
    # visible on the uplink *after that* — so "sent" and "acked" are two
    # separate MQTT events, potentially minutes apart and, for a short
    # sweep segment, potentially spanning a segment change. dl_counts'
    # pending_sf remembers which SF the currently in-flight downlink was
    # sent for, so the eventual ack is attributed correctly even if the
    # sweep has since advanced.
    # ------------------------------------------------------------------

    def maybe_trigger_downlink_test(self, dev_eui: str, packet_count: int) -> Optional[dict]:
        """Called after record_uplink_for_run, once per uplink, with the
        packet count it just returned. Every Kth uplink
        (K = max(1, round(15 / interval_minutes)), i.e. roughly one every
        ~15 min) enqueues a confirmed benign downlink (fPort 1, data "04" =
        read HW/SW version) for the device's CURRENT SF segment — unless
        one is already pending/un-acked (never pile up) or downlink_test is
        off for this run. Returns {"dev_eui", "f_port", "data_hex",
        "run_id", "sf"} for the caller to actually enqueue via ChirpStack,
        or None when nothing should be sent right now.
        """
        with self._lock:
            node = self.get_node_by_eui(dev_eui)
            if node is None or node["kind"] != "device":
                return None
            run = self.get_active_run(node["id"])
            if run is None or not run.get("downlink_test"):
                return None
            interval_minutes = run.get("interval_minutes")
            if not interval_minutes:
                return None  # Phase A fixed run — no commanded rate, no SF to attribute to
            schedule = json.loads(run["sf_schedule"]) if run.get("sf_schedule") else []
            segment_index = run.get("segment_index") or 0
            if not schedule or not (0 <= segment_index < len(schedule)):
                return None
            current_sf = schedule[segment_index]["sf"]

            counts = parse_dl_counts(run.get("dl_counts"))
            if counts.get("pending_sf") is not None:
                return None  # a confirmed downlink is still in flight — don't pile up

            k = max(1, round(15 / interval_minutes))
            if packet_count % k != 0:
                return None

            by_sf = counts.setdefault("by_sf", {})
            entry = by_sf.setdefault(str(current_sf), {"sent": 0, "acked": 0})
            entry["sent"] += 1
            counts["pending_sf"] = current_sf
            self._conn.execute(
                "UPDATE run SET dl_counts = ? WHERE id = ?", (json.dumps(counts), run["id"])
            )
            self._conn.commit()
            return {
                "dev_eui": dev_eui,
                "f_port": 1,
                "data_hex": "04",
                "run_id": run["id"],
                "sf": current_sf,
            }

    def record_downlink_test_ack(self, dev_eui: str, acknowledged: bool) -> None:
        """Resolve the currently-pending downlink test for *dev_eui*'s
        active run — attributed to whichever SF it was originally SENT for
        (dl_counts.pending_sf), not whatever SF is current now. A no-op if
        there is no active run or nothing pending (e.g. this ack belongs to
        an unrelated confirmed downlink, such as a manual test/keep-alive).
        A NACK (acknowledged=False) still clears pending_sf — ChirpStack has
        resolved the attempt (exhausted retries), so the next uplink is free
        to trigger another test.
        """
        with self._lock:
            node = self.get_node_by_eui(dev_eui)
            if node is None or node["kind"] != "device":
                return
            run = self.get_active_run(node["id"])
            if run is None:
                return
            counts = parse_dl_counts(run.get("dl_counts"))
            pending_sf = counts.get("pending_sf")
            if pending_sf is None:
                return
            if acknowledged:
                by_sf = counts.setdefault("by_sf", {})
                entry = by_sf.setdefault(str(pending_sf), {"sent": 0, "acked": 0})
                entry["acked"] += 1
            counts["pending_sf"] = None
            self._conn.execute(
                "UPDATE run SET dl_counts = ? WHERE id = ?", (json.dumps(counts), run["id"])
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # rf_frame / rf_stat — RF-environment survey (F-0006)
    #
    # Foreign-traffic detail is written here by
    # CampaignState._record_rf_environment_frame (state.py) on every
    # confirmed-foreign data frame and every foreign join-request. The panel
    # reads back via get_rf_environment, which aggregates FROM this log —
    # never from transient in-memory state — so a page reload or a cockpit
    # restart still shows the accumulated recording.
    # ------------------------------------------------------------------

    def record_rf_frame(
        self,
        dev_addr: Optional[str],
        network: Optional[str],
        channel: Optional[int],
        sf: Optional[int],
        rssi: Optional[int],
        snr: Optional[float],
        mtype: int,
        join_deveui: Optional[str] = None,
        join_joineui: Optional[str] = None,
        vendor: Optional[str] = None,
    ) -> None:
        """Append one row to the rf_frame log. Callers (state.py) treat this
        as best-effort — a DB error here must never break coex
        classification — but this method itself just lets exceptions
        propagate; the caller is responsible for catching."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO rf_frame "
                "(ts, dev_addr, network, channel, sf, rssi, snr, mtype, "
                " join_deveui, join_joineui, vendor) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._now(),
                    dev_addr,
                    network,
                    channel,
                    sf,
                    rssi,
                    snr,
                    mtype,
                    join_deveui,
                    join_joineui,
                    vendor,
                ),
            )
            self._conn.commit()
            self._rf_frame_insert_count += 1
            if self._rf_frame_insert_count % _RF_FRAME_TRIM_EVERY == 0:
                self._trim_rf_frames()

    def _trim_rf_frames(self) -> None:
        """Enforce RF_FRAME_RETENTION_MAX by deleting the oldest rows once
        the log exceeds it. Uses an OFFSET lookup to find the cutoff id
        rather than a NOT IN subquery scan, so it stays cheap even at the
        cap. A no-op while the log is still under the cap."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM rf_frame ORDER BY id DESC LIMIT 1 OFFSET ?",
                (RF_FRAME_RETENTION_MAX - 1,),
            ).fetchone()
            if row is None:
                return  # fewer than RF_FRAME_RETENTION_MAX rows — nothing to trim
            self._conn.execute("DELETE FROM rf_frame WHERE id < ?", (row["id"],))
            self._conn.commit()

    def increment_rf_stat(self, key: str, by: int = 1) -> int:
        """UPSERT-increment a persistent counter (currently just
        "own_frames") and return its new value."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO rf_stat (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
                (key, by),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT value FROM rf_stat WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else 0

    def get_rf_stat(self, key: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM rf_stat WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else 0

    def list_rf_frames(self, limit: Optional[int] = None, newest_first: bool = False) -> list[dict]:
        """Dump of the rf_frame log. Default (no args): the full log, oldest
        first — used by the CSV export; bounded by RF_FRAME_RETENTION_MAX,
        so that is a modest, non-streamed read even for a long campaign.
        Pass limit/newest_first for a cheap indexed "last N frames" query
        (e.g. get_rf_environment's live frame-log) instead of loading the
        whole log."""
        with self._lock:
            order = "id DESC" if newest_first else "id ASC"
            sql = (
                "SELECT id, ts, dev_addr, network, channel, sf, rssi, snr, mtype, "
                "join_deveui, join_joineui, vendor FROM rf_frame ORDER BY " + order
            )
            params: tuple = ()
            if limit is not None:
                sql += " LIMIT ?"
                params = (limit,)
            rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def get_rf_environment(
        self,
        recent_window_s: int = 900,
        sparkline_buckets: int = 10,
        now: Optional[datetime.datetime] = None,
    ) -> dict:
        """Aggregate the RF-environment survey snapshot straight from the
        rf_frame log (plus the rf_stat own_frames counter) — this is the
        DB-backed replacement for the old in-memory
        CampaignState.get_rf_environment. See the rf_frame table comment
        above for what feeds it.

        *now* is the reference "current time" for every time-windowed field
        below (recent-window sparkline, the 24 h timeline) — defaults to
        the real current time; a caller (tests) can pass a fixed value for
        a deterministic window instead of depending on wall-clock time.

        Returns own_frames/foreign_frames totals, per-dev_addr latest-seen
        detail (foreign_devices), a per-network rollup, a foreign-only
        (channel, SF) matrix, per-OUI vendor counts (from join-requests),
        an MType breakdown, a recent-window frames/min figure with a short
        sparkline, an hourly 24 h traffic timeline, the last N frames for a
        live log, and SF/RSSI distributions (data frames only — like
        channel_sf_matrix, join-requests are excluded so these agree with
        the heatmap).
        """
        with self._lock:
            now = now or datetime.datetime.now(datetime.timezone.utc)
            own_frames = self.get_rf_stat("own_frames")
            total_row = self._conn.execute("SELECT COUNT(*) AS c FROM rf_frame").fetchone()
            foreign_frames = total_row["c"] if total_row else 0

            device_rows = self._conn.execute(
                "SELECT f.dev_addr, f.network, f.rssi AS last_rssi, f.snr AS last_snr, "
                "f.sf AS last_sf, f.channel AS last_channel, f.ts AS last_seen, c.frames "
                "FROM rf_frame f JOIN ("
                "  SELECT dev_addr, MAX(id) AS max_id, COUNT(*) AS frames "
                "  FROM rf_frame WHERE dev_addr IS NOT NULL GROUP BY dev_addr"
                ") c ON c.dev_addr = f.dev_addr AND c.max_id = f.id"
            ).fetchall()
            foreign_devices = {
                row["dev_addr"]: {
                    "frames": row["frames"],
                    "network": row["network"],
                    "last_seen": row["last_seen"],
                    "last_rssi": row["last_rssi"],
                    "last_snr": row["last_snr"],
                    "last_sf": row["last_sf"],
                    "last_channel": row["last_channel"],
                }
                for row in device_rows
            }

            networks: dict[str, dict] = {}
            for entry in foreign_devices.values():
                label = entry.get("network") or "other"
                bucket = networks.setdefault(label, {"devices": 0, "frames": 0})
                bucket["devices"] += 1
                bucket["frames"] += entry["frames"]

            matrix_rows = self._conn.execute(
                "SELECT channel, sf, COUNT(*) AS cnt FROM rf_frame "
                "WHERE dev_addr IS NOT NULL GROUP BY channel, sf"
            ).fetchall()
            channel_sf_matrix = {
                f"ch{row['channel']}_sf{row['sf']}": row["cnt"] for row in matrix_rows
            }

            vendor_rows = self._conn.execute(
                "SELECT substr(join_deveui, 1, 6) AS oui, vendor, COUNT(*) AS joins "
                "FROM rf_frame WHERE mtype = 0 AND join_deveui IS NOT NULL GROUP BY oui"
            ).fetchall()
            vendors = {
                row["oui"]: {"name": row["vendor"], "joins": row["joins"]} for row in vendor_rows
            }

            mtype_rows = self._conn.execute(
                "SELECT mtype, COUNT(*) AS cnt FROM rf_frame GROUP BY mtype"
            ).fetchall()
            mtype_counts = {"join": 0, "data_up": 0, "data_down": 0, "other": 0}
            for row in mtype_rows:
                if row["mtype"] == 0:
                    mtype_counts["join"] += row["cnt"]
                elif row["mtype"] in (2, 4):
                    mtype_counts["data_up"] += row["cnt"]
                elif row["mtype"] in (3, 5):
                    mtype_counts["data_down"] += row["cnt"]
                else:
                    mtype_counts["other"] += row["cnt"]

            cutoff = (now - datetime.timedelta(seconds=recent_window_s)).isoformat(
                timespec="seconds"
            )
            recent_rows = self._conn.execute(
                "SELECT ts FROM rf_frame WHERE ts >= ? ORDER BY ts", (cutoff,)
            ).fetchall()
            recent_times = [datetime.datetime.fromisoformat(row["ts"]) for row in recent_rows]

            frames_per_min = (
                round(len(recent_times) / (recent_window_s / 60), 2) if recent_times else 0.0
            )
            bucket_seconds = recent_window_s / sparkline_buckets
            sparkline = [0] * sparkline_buckets
            for t in recent_times:
                age_s = (now - t).total_seconds()
                idx = int(age_s // bucket_seconds)
                if 0 <= idx < sparkline_buckets:
                    sparkline[sparkline_buckets - 1 - idx] += 1

            # Traffic timeline — foreign frames per 1 h bucket over the last
            # RF_TIMELINE_HOURS, zero-filled, oldest -> newest. Bucketed in
            # Python (not SQL strftime) to match the sparkline above and
            # avoid any doubt about SQLite's handling of the "+00:00" suffix
            # in stored timestamps.
            def _hour_floor(dt: datetime.datetime) -> datetime.datetime:
                return dt.replace(minute=0, second=0, microsecond=0)

            hour_start = _hour_floor(now)  # start of the current (newest) bucket
            timeline_start = hour_start - datetime.timedelta(hours=RF_TIMELINE_HOURS - 1)
            timeline_rows = self._conn.execute(
                "SELECT ts FROM rf_frame WHERE ts >= ? ORDER BY ts",
                (timeline_start.isoformat(timespec="seconds"),),
            ).fetchall()
            timeline_counts = [0] * RF_TIMELINE_HOURS
            for row in timeline_rows:
                t_hour = _hour_floor(datetime.datetime.fromisoformat(row["ts"]))
                hours_ago = int((hour_start - t_hour).total_seconds() // 3600)
                idx = RF_TIMELINE_HOURS - 1 - hours_ago
                if 0 <= idx < RF_TIMELINE_HOURS:
                    timeline_counts[idx] += 1
            timeline = [
                {
                    "bucket": (timeline_start + datetime.timedelta(hours=i)).isoformat(
                        timespec="seconds"
                    ),
                    "count": timeline_counts[i],
                }
                for i in range(RF_TIMELINE_HOURS)
            ]

            # Live frame log — the last RF_RECENT_FRAMES_LIMIT foreign frames
            # (data frames AND join-requests), newest first.
            recent_frames = [
                {
                    "ts": row["ts"],
                    "dev_addr": row["dev_addr"],
                    "network": row["network"],
                    "sf": row["sf"],
                    "rssi": row["rssi"],
                    "mtype": row["mtype"],
                }
                for row in self.list_rf_frames(limit=RF_RECENT_FRAMES_LIMIT, newest_first=True)
            ]

            # SF / RSSI distributions — data frames only (dev_addr IS NOT
            # NULL), same population as channel_sf_matrix, so these agree
            # with the heatmap they're displayed alongside.
            sf_rows = self._conn.execute(
                "SELECT sf, COUNT(*) AS cnt FROM rf_frame "
                "WHERE dev_addr IS NOT NULL AND sf IS NOT NULL GROUP BY sf"
            ).fetchall()
            sf_counts_by_val = {row["sf"]: row["cnt"] for row in sf_rows}
            sf_distribution = {str(sf): sf_counts_by_val.get(sf, 0) for sf in range(7, 13)}

            rssi_row = self._conn.execute(
                "SELECT "
                "  SUM(CASE WHEN rssi >= -80 THEN 1 ELSE 0 END) AS strong, "
                "  SUM(CASE WHEN rssi < -80 AND rssi >= -100 THEN 1 ELSE 0 END) AS mid, "
                "  SUM(CASE WHEN rssi < -100 AND rssi >= -115 THEN 1 ELSE 0 END) AS weak, "
                "  SUM(CASE WHEN rssi < -115 THEN 1 ELSE 0 END) AS weakest "
                "FROM rf_frame WHERE dev_addr IS NOT NULL AND rssi IS NOT NULL"
            ).fetchone()
            rssi_distribution = [
                {"label": "≥ -80 dBm", "count": (rssi_row["strong"] or 0) if rssi_row else 0},
                {"label": "-80…-100 dBm", "count": (rssi_row["mid"] or 0) if rssi_row else 0},
                {"label": "-100…-115 dBm", "count": (rssi_row["weak"] or 0) if rssi_row else 0},
                {"label": "< -115 dBm", "count": (rssi_row["weakest"] or 0) if rssi_row else 0},
            ]

            return {
                "own_frames": own_frames,
                "foreign_frames": foreign_frames,
                "foreign_devices": foreign_devices,
                "networks": networks,
                "vendors": vendors,
                "mtype_counts": mtype_counts,
                "channel_sf_matrix": channel_sf_matrix,
                "frames_per_min": frames_per_min,
                "frames_per_min_sparkline": sparkline,
                "timeline": timeline,
                "recent_frames": recent_frames,
                "sf_distribution": sf_distribution,
                "rssi_distribution": rssi_distribution,
            }
