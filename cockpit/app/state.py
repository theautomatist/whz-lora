"""state.py — CampaignState: in-memory field-test state + CSV recording + SSE fan-out.

No external package imports at module level — importable without grpc/fastapi installed.
All public methods are thread-safe (called from MQTT ingest thread and asyncio handlers).
"""
import asyncio
import collections
import csv
import dataclasses
import datetime
import logging
import os
import statistics
import threading
from typing import Optional

from .db import Database
from .lorawan import (
    caf as calc_caf,
    classify_network,
    freq_to_channel,
    parse_devaddr,
    parse_join_request,
    parse_mhdr,
    traffic_light,
    vendor_for_oui,
)

logger = logging.getLogger(__name__)

# Minimum observation window before the coex CAF / traffic-light verdict is
# considered stable.  Below this threshold the event carries status="measuring"
# to signal that the rate estimate is not yet reliable.
_COEX_MIN_WINDOW_S: int = 60

# How many recent uplink timestamps to retain per device for the median-
# based interval_seconds estimate (7 timestamps -> up to 6 gaps, "median of
# the last ~6 uplink gaps").
_UPLINK_HISTORY_LEN: int = 7

# ---------------------------------------------------------------------------
# CSV schema
# ---------------------------------------------------------------------------

CSV_COLUMNS = [
    "timestamp_utc",
    "dev_eui",
    "pos_id",
    "rssi_dbm",
    "snr_db",
    "sf",
    "freq_hz",
    "f_cnt",
    "gw_eui",
    "antenna",
    "phase",
    "floor",
    "room",
    "point_type",
    "path",
    "los",
    "mounting",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class PointMeta:
    """Metadata for the current measurement point."""

    pos_id: str
    floor: str
    room: str
    point_type: str
    path: str
    los: str
    mounting: str
    expected_n: Optional[int]


@dataclasses.dataclass
class DeviceMetrics:
    """Per-device live metrics (latest uplink values)."""

    rssi: Optional[float] = None
    snr: Optional[float] = None
    sf: Optional[int] = None
    f_cnt: Optional[int] = None
    received: int = 0
    acked: int = 0
    downlinks_sent: int = 0
    last_uplink_at: Optional[str] = None  # ISO of the most recent uplink
    last_downlink_at: Optional[str] = None  # ISO of the last txack/ack (F-0006 "Trust & Sichtbarkeit")
    # Bounded history of recent uplink timestamps (ISO strings, oldest
    # first) — feeds _median_interval_seconds, robust to a single missed
    # uplink skewing a simple last-two-gap measurement.
    uplink_times: collections.deque = dataclasses.field(
        default_factory=lambda: collections.deque(maxlen=_UPLINK_HISTORY_LEN)
    )


# ---------------------------------------------------------------------------
# Module-level SSE helper — keeps QueueFull off the event-loop exception log
# ---------------------------------------------------------------------------


def _safe_put(queue: asyncio.Queue, event: dict) -> None:
    """Scheduled inside the event loop; drops the oldest item on full queue."""
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass  # still full after eviction — discard the new event silently


def _median_interval_seconds(uplink_times) -> Optional[float]:
    """Measured send cadence = median of the consecutive gaps between the
    retained recent uplink timestamps (seconds).

    Lets the UI show the device's *actual* interval (e.g. confirm the 5-min
    Vicki downlink took effect), not just the commanded one — using the
    median instead of just the last two timestamps makes this robust to a
    single missed/late packet (which would otherwise make a steady 5-min
    device briefly read as "15 min"). None until at least two uplinks have
    been seen.
    """
    if len(uplink_times) < 2:
        return None
    try:
        parsed = [datetime.datetime.fromisoformat(t) for t in uplink_times]
    except (ValueError, TypeError):
        return None
    gaps = [(b - a).total_seconds() for a, b in zip(parsed, parsed[1:])]
    gaps = [g for g in gaps if g > 0]
    if not gaps:
        return None
    return statistics.median(gaps)


# ---------------------------------------------------------------------------
# Standalone CSV-row builder (testable without a running CampaignState)
# ---------------------------------------------------------------------------


def build_csv_row(
    metrics: dict,
    point: Optional[PointMeta],
    antenna: str,
    phase: str = "adr",
) -> dict:
    """Build a CSV row dict from uplink metrics + current point metadata.

    metrics dict keys (all optional): dev_eui, rssi_dbm, snr_db, sf,
    freq_hz, f_cnt, gw_eui.  Missing keys produce empty strings.
    """
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    return {
        "timestamp_utc": ts,
        "dev_eui": metrics.get("dev_eui", ""),
        "pos_id": point.pos_id if point else "",
        "rssi_dbm": metrics.get("rssi_dbm", ""),
        "snr_db": metrics.get("snr_db", ""),
        "sf": metrics.get("sf", ""),
        "freq_hz": metrics.get("freq_hz", ""),
        "f_cnt": metrics.get("f_cnt", ""),
        "gw_eui": metrics.get("gw_eui", ""),
        "antenna": antenna,
        "phase": phase,
        "floor": point.floor if point else "",
        "room": point.room if point else "",
        "point_type": point.point_type if point else "",
        "path": point.path if point else "",
        "los": point.los if point else "",
        "mounting": point.mounting if point else "",
    }


# ---------------------------------------------------------------------------
# Campaign state
# ---------------------------------------------------------------------------


class CampaignState:
    """Central in-memory state for one field-test session.

    Thread-safe: a single threading.Lock protects all mutable attributes.
    The asyncio event loop (set via set_loop) is used only for SSE fan-out.
    """

    def __init__(self, data_dir: str = "/data") -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir

        # Current measurement point
        self._point: Optional[PointMeta] = None
        self._antenna: str = "3dbi"
        self._phase: str = "adr"  # "adr" | "sf9" | "sf12"

        # CSV recording
        self._recording: bool = False
        self._csv_path: Optional[str] = None
        self._csv_file = None
        self._csv_writer = None

        # Per-device live metrics  {dev_eui: DeviceMetrics}
        self._devices: dict[str, DeviceMetrics] = {}

        # Per-point received uplink counts  {pos_id: count}
        # Reset to 0 for the active pos_id each time set_point is called so
        # PDR is computed against the current visit, not accumulated history.
        self._pos_counts: dict[str, int] = {}

        # Known DevAddrs for coex own/foreign classification  {dev_eui: dev_addr_hex}
        self._dev_addrs: dict[str, str] = {}

        # Coex scan state — always-on (F-0006 "Trust & Sichtbarkeit"): the
        # gateway physically receives every LoRa frame in range regardless
        # of any UI toggle, so classification runs unconditionally.
        # toggle_coex/is_coex_active are kept for backward-compat API shape
        # only; they no longer gate process_coex_frame.
        self._coex_active: bool = True
        self._coex_start: Optional[datetime.datetime] = None
        # {(channel, sf): frame_count}
        self._coex_frames: dict[tuple, int] = {}
        self._coex_own_frames: int = 0
        self._coex_foreign_frames: int = 0
        self._coex_unknown_frames: int = 0

        # RF-environment survey (F-0006) — foreign-traffic detail is
        # PERSISTED (see set_db/_record_rf_environment_frame and
        # db.Database.get_rf_environment) rather than kept in memory, so it
        # survives a cockpit restart and a page reload shows the
        # accumulated recording. self._db is None until set_db() is called
        # (e.g. in a unit test that doesn't need persistence) — best-effort
        # no-op in that case.
        self._db: Optional[Database] = None

        # SSE subscriber queues and the asyncio loop they belong to
        self._subscribers: list[asyncio.Queue] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the asyncio event loop; required before SSE fan-out works."""
        self._loop = loop

    def set_db(self, db: Database) -> None:
        """Register the persistent Database for the RF-environment survey
        log (F-0006) — mirrors set_loop(). Without it, process_coex_frame's
        foreign-frame detail is simply not persisted (best-effort no-op)."""
        self._db = db

    # ------------------------------------------------------------------
    # Measurement point + antenna
    # ------------------------------------------------------------------

    def set_point(
        self,
        pos_id: str,
        floor: str,
        room: str,
        point_type: str,
        path: str,
        los: str,
        mounting: str,
        expected_n: Optional[int],
    ) -> None:
        with self._lock:
            self._point = PointMeta(
                pos_id, floor, room, point_type, path, los, mounting, expected_n
            )
            # Reset received counter for this pos_id so each set_point call
            # starts a fresh PDR tally (re-visiting a point resets its count).
            self._pos_counts[pos_id] = 0
        self._broadcast(
            {
                "type": "state",
                "pos_id": pos_id,
                "expected_n": expected_n,
                "antenna": self._antenna,
            }
        )

    def set_antenna(self, antenna_type: str) -> None:
        with self._lock:
            self._antenna = antenna_type
        self._broadcast({"type": "state", "antenna": antenna_type})

    def set_phase(self, phase: str) -> None:
        """Switch the active measurement phase (\"adr\", \"sf9\" or \"sf12\")."""
        with self._lock:
            self._phase = phase
        self._broadcast({"type": "state", "phase": phase})

    def get_phase(self) -> str:
        with self._lock:
            return self._phase

    # ------------------------------------------------------------------
    # CSV recording
    # ------------------------------------------------------------------

    def start_recording(self) -> str:
        """Open a new CSV file and start writing. Returns the file path."""
        with self._lock:
            if self._recording and self._csv_path:
                return self._csv_path
            os.makedirs(self._data_dir, exist_ok=True)
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
            self._csv_path = os.path.join(self._data_dir, f"field_{ts}.csv")
            self._csv_file = open(self._csv_path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=CSV_COLUMNS)
            self._csv_writer.writeheader()
            self._csv_file.flush()
            self._recording = True
        return self._csv_path

    def stop_recording(self) -> Optional[str]:
        """Stop writing and close the CSV file. Returns the path or None."""
        with self._lock:
            if not self._recording:
                return None
            path = self._csv_path
            self._recording = False
            if self._csv_file:
                self._csv_file.close()
                self._csv_file = None
                self._csv_writer = None
        return path

    def current_csv_path(self) -> Optional[str]:
        with self._lock:
            return self._csv_path

    # ------------------------------------------------------------------
    # Uplink / join / ack processing
    # ------------------------------------------------------------------

    def process_uplink(self, metrics: dict) -> None:
        """Update device metrics, write CSV row if recording, broadcast SSE event."""
        dev_eui = metrics.get("dev_eui", "")

        with self._lock:
            dm = self._devices.setdefault(dev_eui, DeviceMetrics())
            dm.rssi = metrics.get("rssi_dbm")
            dm.snr = metrics.get("snr_db")
            dm.sf = metrics.get("sf")
            dm.f_cnt = metrics.get("f_cnt")
            dm.received += 1
            _now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            )
            dm.last_uplink_at = _now_iso
            dm.uplink_times.append(_now_iso)
            _last_at = dm.last_uplink_at
            _interval_s = _median_interval_seconds(dm.uplink_times)

            pos_id = self._point.pos_id if self._point else ""
            self._pos_counts[pos_id] = self._pos_counts.get(pos_id, 0) + 1
            received_count = self._pos_counts[pos_id]
            expected_n = self._point.expected_n if self._point else None
            pdr = received_count / expected_n if expected_n else None

            # Write CSV row only when a measurement point is set; rows without
            # a point are meaningless for post-processing.
            if (
                self._recording
                and self._point is not None
                and self._csv_writer is not None
            ):
                row = build_csv_row(metrics, self._point, self._antenna, self._phase)
                self._csv_writer.writerow(row)
                self._csv_file.flush()

        self._broadcast(
            {
                "type": "uplink",
                "dev_eui": dev_eui,
                "rssi_dbm": metrics.get("rssi_dbm"),
                "snr_db": metrics.get("snr_db"),
                "sf": metrics.get("sf"),
                "freq_hz": metrics.get("freq_hz"),
                "f_cnt": metrics.get("f_cnt"),
                "gw_eui": metrics.get("gw_eui"),
                "pos_id": pos_id,
                "pos_received": received_count,
                "pdr": pdr,
                "last_uplink_at": _last_at,
                "interval_seconds": _interval_s,
            }
        )

    def process_join(self, dev_eui: str, dev_addr: str) -> None:
        with self._lock:
            if dev_addr:
                self._dev_addrs[dev_eui] = dev_addr
        self._broadcast({"type": "join", "dev_eui": dev_eui, "dev_addr": dev_addr})

    def process_ack(self, dev_eui: str) -> None:
        """Record a confirmed downlink acknowledgement and broadcast to SSE."""
        with self._lock:
            dm = self._devices.setdefault(dev_eui, DeviceMetrics())
            dm.acked += 1
            acked = dm.acked
            downlinks_sent = dm.downlinks_sent
        pdr = acked / downlinks_sent if downlinks_sent > 0 else None
        self._broadcast(
            {
                "type": "ack",
                "dev_eui": dev_eui,
                "acked": acked,
                "downlink_pdr": pdr,
            }
        )

    def broadcast_nack(self, dev_eui: str) -> None:
        """Broadcast a NACK event (acknowledged=false in ChirpStack event/ack).

        Does NOT increment the acked counter — the operator sees the failure
        via the SSE 'nack' event and the acked/sent ratio stays accurate.
        """
        self._broadcast({"type": "nack", "dev_eui": dev_eui})

    def record_downlink_sent(self, dev_eui: str) -> None:
        with self._lock:
            dm = self._devices.setdefault(dev_eui, DeviceMetrics())
            dm.downlinks_sent += 1

    def record_downlink_txack(self, dev_eui: str) -> None:
        """Record that ChirpStack transmitted a queued downlink over the air
        (event/txack) or the device acknowledged one (event/ack) — the
        Class-A-accurate "was this actually sent" signal surfaced by the
        cockpit's Geräte-Status block (F-0006 "Trust & Sichtbarkeit").
        """
        with self._lock:
            dm = self._devices.setdefault(dev_eui, DeviceMetrics())
            dm.last_downlink_at = datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(timespec="seconds")

    def get_device_uplink_stats(self, dev_eui: str) -> dict:
        """last_uplink_at / interval_seconds / last_downlink_at for one
        device — a dedicated cheap lookup for GET /api/device/{id}/config-
        status, kept separate from get_dashboard() so that endpoint stays
        light (it must not build the full dashboard on every call).
        """
        with self._lock:
            dm = self._devices.get(dev_eui)
            if dm is None:
                return {
                    "last_uplink_at": None,
                    "interval_seconds": None,
                    "last_downlink_at": None,
                }
            return {
                "last_uplink_at": dm.last_uplink_at,
                "interval_seconds": _median_interval_seconds(dm.uplink_times),
                "last_downlink_at": dm.last_downlink_at,
            }

    # ------------------------------------------------------------------
    # Coexistence scan
    # ------------------------------------------------------------------

    def toggle_coex(self, on: bool) -> None:
        with self._lock:
            self._coex_active = on
            if on and self._coex_start is None:
                self._coex_start = datetime.datetime.now(datetime.timezone.utc)

    def is_coex_active(self) -> bool:
        with self._lock:
            return self._coex_active

    def process_coex_frame(
        self,
        sf: int,
        freq_hz: int,
        rssi: int,
        phy_payload: bytes,
        snr: Optional[float] = None,
    ) -> None:
        """Decode a gateway UplinkFrame for coexistence analysis and broadcast
        event. Always-on (F-0006 "Trust & Sichtbarkeit"): the gateway
        physically receives every LoRa frame in range regardless of any UI
        toggle, so this runs unconditionally — there is no start/stop gate
        here anymore. Also feeds the RF-environment survey (foreign-traffic
        detail) — see _record_rf_environment_frame.

        *snr* is optional (defaults to None) so existing callers/tests that
        predate the RF-environment survey keep working unchanged.
        """
        channel = freq_to_channel(freq_hz)
        key = (channel, sf)

        with self._lock:
            if self._coex_start is None:
                self._coex_start = datetime.datetime.now(datetime.timezone.utc)
            self._coex_frames[key] = self._coex_frames.get(key, 0) + 1
            count = self._coex_frames[key]
            known_addrs = set(self._dev_addrs.values())
            known_dev_euis = set(self._dev_addrs.keys())
            elapsed = (
                datetime.datetime.now(datetime.timezone.utc) - self._coex_start
            ).total_seconds()

        # Classify frame ownership (best-effort; join frames have no DevAddr)
        mtype = parse_mhdr(phy_payload)
        dev_addr: Optional[str] = None
        is_own: Optional[bool] = None
        if mtype in (2, 3, 4, 5):  # data frames
            dev_addr = parse_devaddr(phy_payload)
            if dev_addr and known_addrs:
                is_own = dev_addr in known_addrs

        with self._lock:
            if is_own is True:
                self._coex_own_frames += 1
            elif is_own is False:
                self._coex_foreign_frames += 1
            else:
                self._coex_unknown_frames += 1

        self._record_rf_environment_frame(
            mtype, dev_addr, is_own, known_dev_euis, sf, channel, rssi, snr, phy_payload
        )

        # CAF verdict requires a minimum observation window so that early
        # bursts (e.g. the first frame 1 second into the scan) don't
        # produce a spurious RED classification.
        if elapsed < _COEX_MIN_WINDOW_S:
            self._broadcast(
                {
                    "type": "coex",
                    "sf": sf,
                    "channel": channel,
                    "freq_hz": freq_hz,
                    "rssi": rssi,
                    "mtype": mtype,
                    "dev_addr": dev_addr,
                    "is_own": is_own,
                    "caf": None,
                    "traffic_light": "measuring",
                }
            )
            return

        # Compute CAF using actual payload length and stable elapsed window
        hours = elapsed / 3600.0
        frames_per_hour = count / hours
        payload_len = max(len(phy_payload), 1)
        c = calc_caf(frames_per_hour, sf, payload_len)
        light = traffic_light(c)

        self._broadcast(
            {
                "type": "coex",
                "sf": sf,
                "channel": channel,
                "freq_hz": freq_hz,
                "rssi": rssi,
                "mtype": mtype,
                "dev_addr": dev_addr,
                "is_own": is_own,
                "caf": round(c, 6),
                "traffic_light": light,
            }
        )

    def _record_rf_environment_frame(
        self,
        mtype: int,
        dev_addr: Optional[str],
        is_own: Optional[bool],
        known_dev_euis: set,
        sf: int,
        channel: int,
        rssi: int,
        snr: Optional[float],
        phy_payload: bytes,
    ) -> None:
        """Persist foreign-traffic detail to the rf_frame log (F-0006
        RF-Environment survey). GET /api/rf-environment aggregates FROM
        THAT LOG (see db.Database.get_rf_environment), not from in-memory
        state — this is what makes the survey outlive a cockpit restart and
        show its accumulated recording again after a page reload.

        Best-effort throughout: a DB error must never break the coex
        classification in process_coex_frame above, and a parse failure
        here must never raise (matches lorawan.py's parser contracts —
        malformed input returns None/partial, never raises).
        """
        if self._db is None:
            return  # no persistence configured (e.g. a unit test) — no-op

        if mtype == 0:  # join-request — no DevAddr; OUI/vendor detail instead
            join = parse_join_request(phy_payload)
            if join and join["dev_eui"] not in known_dev_euis:
                vendor = vendor_for_oui(join["dev_eui"][:6])
                try:
                    self._db.record_rf_frame(
                        dev_addr=None,
                        network=None,
                        channel=channel,
                        sf=sf,
                        rssi=rssi,
                        snr=snr,
                        mtype=mtype,
                        join_deveui=join["dev_eui"],
                        join_joineui=join["join_eui"],
                        vendor=vendor["name"],
                    )
                except Exception as e:
                    logger.warning("record_rf_frame (join) failed: %s", e)
            return

        if is_own is True:
            try:
                self._db.increment_rf_stat("own_frames")
            except Exception as e:
                logger.warning("increment_rf_stat(own_frames) failed: %s", e)

        if is_own is not False or not dev_addr:
            return  # only definitively-foreign data frames feed the survey below

        net = classify_network(dev_addr)
        try:
            self._db.record_rf_frame(
                dev_addr=dev_addr,
                network=net["label"],
                channel=channel,
                sf=sf,
                rssi=rssi,
                snr=snr,
                mtype=mtype,
                join_deveui=None,
                join_joineui=None,
                vendor=None,
            )
        except Exception as e:
            logger.warning("record_rf_frame (data) failed: %s", e)

    # ------------------------------------------------------------------
    # Dashboard snapshot
    # ------------------------------------------------------------------

    def get_dashboard(self) -> dict:
        """Return a JSON-serialisable snapshot of the current state."""
        with self._lock:
            point = self._point
            point_dict = (
                dataclasses.asdict(point) if point else None
            )
            devices = {
                dev: {
                    "rssi_dbm": dm.rssi,
                    "snr_db": dm.snr,
                    "sf": dm.sf,
                    "f_cnt": dm.f_cnt,
                    "received": dm.received,
                    "acked": dm.acked,
                    "downlinks_sent": dm.downlinks_sent,
                    "last_uplink_at": dm.last_uplink_at,
                    "interval_seconds": _median_interval_seconds(dm.uplink_times),
                }
                for dev, dm in self._devices.items()
            }
            return {
                "recording": self._recording,
                "csv_path": self._csv_path,
                "antenna": self._antenna,
                "phase": self._phase,
                "point": point_dict,
                "devices": devices,
                "pos_counts": dict(self._pos_counts),
                "coex_active": self._coex_active,
                "coex_own_frames": self._coex_own_frames,
                "coex_foreign_frames": self._coex_foreign_frames,
                "coex_unknown_frames": self._coex_unknown_frames,
                "coex_frames": {
                    f"ch{ch}_sf{sf}": cnt
                    for (ch, sf), cnt in self._coex_frames.items()
                },
            }

    # ------------------------------------------------------------------
    # SSE subscription
    # ------------------------------------------------------------------

    def subscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers.append(queue)

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                pass

    def broadcast_event(self, event: dict) -> None:
        """Push an arbitrary event to all SSE subscribers.

        Used by callers outside CampaignState (e.g. the F-0006 node/placement/
        run endpoints in main.py, backed by db.py) that need to notify the
        frontend of a change without duplicating the subscriber/loop plumbing.
        """
        self._broadcast(event)

    def _broadcast(self, event: dict) -> None:
        """Push event to all SSE subscriber queues (thread-safe).

        Uses _safe_put so a full queue drops the oldest item rather than
        raising QueueFull inside the event-loop callback.
        """
        if self._loop is None or not self._loop.is_running():
            return
        with self._lock:
            subs = list(self._subscribers)
        for queue in subs:
            try:
                self._loop.call_soon_threadsafe(_safe_put, queue, event)
            except RuntimeError:
                # Event loop closed
                pass
