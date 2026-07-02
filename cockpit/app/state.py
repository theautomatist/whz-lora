"""state.py — CampaignState: in-memory field-test state + CSV recording + SSE fan-out.

No external package imports at module level — importable without grpc/fastapi installed.
All public methods are thread-safe (called from MQTT ingest thread and asyncio handlers).
"""
import asyncio
import csv
import dataclasses
import datetime
import logging
import os
import threading
from typing import Optional

from .lorawan import caf as calc_caf, freq_to_channel, parse_devaddr, parse_mhdr, traffic_light

logger = logging.getLogger(__name__)

# Minimum observation window before the coex CAF / traffic-light verdict is
# considered stable.  Below this threshold the event carries status="measuring"
# to signal that the rate estimate is not yet reliable.
_COEX_MIN_WINDOW_S: int = 60

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


# ---------------------------------------------------------------------------
# Standalone CSV-row builder (testable without a running CampaignState)
# ---------------------------------------------------------------------------


def build_csv_row(
    metrics: dict,
    point: Optional[PointMeta],
    antenna: str,
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

        # Coex scan state
        self._coex_active: bool = False
        self._coex_start: Optional[datetime.datetime] = None
        # {(channel, sf): frame_count}
        self._coex_frames: dict[tuple, int] = {}

        # SSE subscriber queues and the asyncio loop they belong to
        self._subscribers: list[asyncio.Queue] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register the asyncio event loop; required before SSE fan-out works."""
        self._loop = loop

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
                row = build_csv_row(metrics, self._point, self._antenna)
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
        self, sf: int, freq_hz: int, rssi: int, phy_payload: bytes
    ) -> None:
        """Decode a gateway UplinkFrame for coexistence analysis and broadcast event."""
        channel = freq_to_channel(freq_hz)
        key = (channel, sf)

        with self._lock:
            if not self._coex_active:
                return
            if self._coex_start is None:
                self._coex_start = datetime.datetime.now(datetime.timezone.utc)
            self._coex_frames[key] = self._coex_frames.get(key, 0) + 1
            count = self._coex_frames[key]
            known_addrs = set(self._dev_addrs.values())
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
                }
                for dev, dm in self._devices.items()
            }
            return {
                "recording": self._recording,
                "csv_path": self._csv_path,
                "antenna": self._antenna,
                "point": point_dict,
                "devices": devices,
                "pos_counts": dict(self._pos_counts),
                "coex_active": self._coex_active,
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
