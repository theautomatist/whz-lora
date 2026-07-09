# Feldtest-Cockpit

FastAPI web app for managing WHZ LoRaWAN field test campaigns. The UI is
**device-centric** (F-0006 Feldmess-Workflow): pick the device (or the
gateway) you're physically holding, place it, start a run, move on.
**No GPS anywhere** — a "placement" is floor/room/description, not
coordinates.

## Panels

Layout, top to bottom: **Übersicht** is the primary entry point right under
the header; tapping a card opens **Ausgewähltes Gerät / Gateway** directly
below it (scrolled into view); everything else is secondary and collapsed
by default.

- **Übersicht** — a card per device *and* the gateway (its own tile):
  name, current location (`Etage · Raum` or "nicht platziert"), run status
  ("● Läuft" / "kein Run" / "fertig ✓" once a run finishes), packet count,
  live RSSI/SNR/SF (colour-coded), and — for devices with a Phase B sweep —
  a progress bar with segment ticks. A small "*N* fertig" badge in the
  card title summarises finished runs. Tapping a card selects that node and
  scrolls to the detail panel below.
- **Ausgewähltes Gerät / Gateway** — current placement (floor/room/
  description + up to 3 photo thumbnails), run status + packet count + SF-
  sweep progress, live RSSI/SNR/SF/PDR (colour-coded). A compact node
  picker (`<select>`) in the card title is the secondary way to pick a node
  (besides tapping an Übersicht card). Buttons:
  - *Platzieren / Umsetzen* (device) — bottom sheet: floor, room,
    description, note, antenna (3/12 dBi), up to 3 photos captured via
    `<input type="file" capture="environment">`. If the device has an
    active run this calls `POST /api/relocate` (closes the run, opens a
    new placement, starts a new run); otherwise `POST /api/placement`
    (placement only, no run). Photos upload to the returned
    `placement_id` afterwards.
  - *Run starten — 24 h Sweep (SF7→SF9→SF12)* / *Run stoppen* — the
    primary one-tap button starts a Phase B timed SF-sweep
    (`POST /api/run/start` with `duration_seconds`/`sf_schedule`/
    `interval_minutes`); an *Anpassen* (collapsible) lets the operator
    change duration, interval and SF-order preset first. A 409 (e.g.
    missing device/gateway placement) is shown inline.
  - *Gateway umsetzen* (gateway) — bottom sheet (floor/room/description/
    note) → `POST /api/gateway/move`. On 409 (`open_runs`) the sheet shows
    the list of still-running device runs with an *Alle quittieren &
    umsetzen* button → `POST /api/gateway/move/force`.
  - *Verlauf* (device, collapsible) — run history via
    `GET /api/runs?node_id=`, each with location, status, packet count and
    a CSV download link.
- **Phase / SF-Switch** (collapsible) — switch all registered devices
  between three measurement phases by reassigning their ChirpStack device
  profile via `POST /api/phase`:

  | Button | Phase label in CSV | ChirpStack profile | ADR algorithm |
  |---|---|---|---|
  | Normal · ADR | `adr` | `WHZ-Feldtest-EU868` | `default` |
  | Phase 1 · SF9 | `sf9` | `WHZ-Feldtest-SF9` | `fixed_dr3` (DR3) |
  | Phase 2 · SF12 | `sf12` | `WHZ-Feldtest-SF12` | `fixed_dr0` (DR0) |

  The three device profiles are auto-created at startup (idempotent
  find-or-create); no manual ChirpStack provisioning is needed.
  The `phase` column appears in every per-run CSV row recorded after the
  switch. Campaign phase is only updated in memory when **all** devices
  switch successfully; a partial failure returns HTTP 502 and leaves the
  CSV label unchanged.

  **MClimate Vicki convenience downlinks** (sent to all registered devices):
  - *Intervall 5 min* — enqueues `0x0205` on FPort 1 (set keepalive period).
    Uses `count:false` so these commands do **not** inflate the DL-PDR
    denominator.
  - *HW/SW-Version lesen* — enqueues `0x04` on FPort 1 (read hardware and
    software version; elicits a confirmed reply). Uses `count:true` so
    successful ACKs are tracked in the downlink PDR.

- **Geräte-Registrierung** (collapsible) — register and list OTAA devices
  in `whz-feldtest`. Newly registered devices only appear in the Übersicht
  after a cockpit restart (node sync runs at startup).
- **Downlink-Loopback** (collapsible) — enqueue a confirmed downlink; track ACK-PDR.
- **Koexistenz-Scan** (collapsible) — decode gateway protobuf frames; compute
  per-SF/channel CAF with traffic-light classification.

The old single global "Messpunkt + CSV" and "Antenne" panels are
superseded by per-device placements/runs and are no longer part of the UI;
their backend endpoints (`POST /api/point`, `POST /api/recording`,
`POST /api/antenna`) still exist, unused, for backward compatibility.

## F-0006 Feldmess-Workflow (Phase A — backend + frontend)

Backed by SQLite (`/data/cockpit.db`, stdlib `sqlite3`, no new heavy
dependency) and photo uploads (`/data/photos/<placement_id>/<n>.<ext>`).
Both live inside the same mounted `/data` volume — reboot-safe.

At startup every ChirpStack device in `whz-feldtest` is idempotently
upserted as a `node` (kind=`device`), and the one Kerlink gateway is
upserted as a fixed `node` (kind=`gateway`, name `whz-kerlink-ifevo`, EUI
`7076ff0064071a3d` — see `docs/user/kerlink-ifemtocell-bring-up.md`).

A **placement** is a node's physical location over time (only one active
per node — creating a new one closes the previous). A **run** is one
CSV-recording session for a device, tied to the device's and the gateway's
placement at the time it started; several devices can record
simultaneously. **Relocating** a device (`POST /api/relocate`) is the core
action: it closes any active run, opens a new placement, and starts a new
run in a single call.

| Endpoint | Purpose |
|---|---|
| `GET /api/nodes` | Devices + gateway, each with current placement (incl. `photo_ids`) and (for devices) active-run summary |
| `POST /api/placement` | Close current placement, open a new one (does not start a run) |
| `POST /api/photo/{placement_id}` | Attach a photo (multipart `file`); 409 above 3 photos per placement |
| `GET /api/photo/{photo_id}` | Serve a photo |
| `POST /api/run/start` | Start a run — 409 unless both device and gateway have an active placement |
| `POST /api/run/stop` | Stop a device's active run |
| `POST /api/relocate` | Close run → new placement → new run, atomically from the caller's side |
| `POST /api/gateway/move` | Move the gateway — 409 with `open_runs` while any run is `running` |
| `POST /api/gateway/move/force` | Abort all running runs (`reason=gateway-move`, data kept), then move |
| `GET /api/runs?node_id=` | Run history for a device, newest first — each run includes flat `floor`/`room`/`description` |
| `GET /api/run/{id}/csv` | Download a run's CSV file |
| SSE `/api/events` | Emits `{"type":"nodes"}` whenever a placement or run changes — the frontend re-fetches `GET /api/nodes` on this event |

Per-run CSV columns: `timestamp_utc, dev_eui, run_id, node_name, floor,
room, description, antenna, phase, gateway_desc, rssi_dbm, snr_db, sf,
freq_hz, f_cnt, gw_eui`. Written by the MQTT ingest thread on every uplink
from a device with an active run (in addition to the existing live-metrics
update); a run's `packets` counter increments alongside it. Runs with
`ended_at IS NULL` (i.e. `status='running'`) resume recording automatically
after a restart — the state lives in SQLite, not in memory.

The pre-existing single global point/recording (`POST /api/point`,
`POST /api/recording`) still works unchanged in the backend but has no
frontend entry point anymore; per-run recording is the path forward.

## F-0006 Phase B — timed SF-sweep runs

`POST /api/run/start` gained three optional fields on top of Phase A's
`device_node_id`:

```
POST /api/run/start
{
  "device_node_id": 3,
  "duration_seconds": 86400,
  "sf_schedule": [{"sf":7,"seconds":28800},{"sf":9,"seconds":28800},{"sf":12,"seconds":28800}],
  "interval_minutes": 5
}
```

Omitting **all three** keeps the exact Phase A behaviour (a plain fixed
run, no ChirpStack side effects) — this is what every Phase A test relies
on. Giving any one of them starts a sweep; missing pieces default to
`duration_seconds=86400` (24 h), `sf_schedule`=SF7/SF9/SF12 split evenly,
`interval_minutes=5`. On start the backend also (best-effort, logged not
raised on failure):
- switches the device to the first segment's ChirpStack profile
  (`cs.set_device_profile`), and
- enqueues the Vicki send-interval downlink to put the device "im Raster"
  (`0x02` SetSendPeriod + the minute count as one hex byte, e.g. `0205` for
  5 min) via `cs.enqueue_downlink` directly — bypassing
  `POST /api/downlink`, so `campaign.record_downlink_sent` is never called
  (equivalent to `count:false`, keeps this out of the DL-PDR denominator).

SF → ChirpStack profile: **7→`WHZ-Feldtest-SF7`, 9→`WHZ-Feldtest-SF9`,
12→`WHZ-Feldtest-SF12`** (`config.SF_PROFILES`); SF7 is provisioned at
startup alongside SF9/SF12 (`adr_algorithm_id=fixed_dr5`).

A background asyncio task (started/cancelled in the lifespan, polling every
`scheduler.POLL_INTERVAL_SECONDS` ≈ 60 s) advances or finishes each running
sweep: past its current segment's `seconds` it switches the device to the
next segment's profile; past `planned_seconds` (or once the last segment
elapses) it marks the run `status='done'`, `reason='schedule-complete'`.
Each run is wrapped in its own try/except so one failure never stops the
others from being checked on the same tick. The decision itself
(`scheduler.evaluate_run_schedule`) is a pure function of
`(now, started_at, segment_started_at, segment_index, schedule,
planned_seconds)` — unit-tested directly, not "buried" in the async loop.

`GET /api/nodes` and `GET /api/runs` both merge in
`scheduler.run_summary_fields(run)`: `planned_seconds`, `elapsed_seconds`,
`current_sf`, `segment_index`, `progress` (0..1, clamped), `sf_schedule`
(parsed), `done` (`status != 'running'`) — frozen at `ended_at` for
finished runs so a completed run's progress doesn't keep advancing in the
history view. `GET /api/nodes` additionally returns `last_run` per device
(the most recent run regardless of status, alongside the unchanged
`active_run` which is `null` unless `status='running'`) — the frontend
uses it to show a "fertig ✓" badge once a sweep completes and is no longer
"active". The frontend re-computes `elapsed_seconds`/`progress`/
`current_sf` client-side from `started_at`/`planned_seconds`/`sf_schedule`
every ~30 s (`liveRunProgress` in app.js) so the progress bar moves
smoothly between the infrequent SSE `nodes` events, which still snap it
back to server truth.

The `run` table's five new columns (`planned_seconds`, `sf_schedule` (JSON
TEXT), `interval_minutes`, `segment_index`, `segment_started_at`) are
additive: `_SCHEMA` already declares them for a fresh database, and
`Database._migrate_run_columns()` adds any missing ones via guarded
`ALTER TABLE ... ADD COLUMN` on every startup (a no-op once present) — an
existing `/data/cockpit.db` upgrades in place, its Phase A runs untouched.

## Running locally (dev)

```bash
cd cockpit
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Needs `CHIRPSTACK_HOST`, `MQTT_HOST`, etc. — see `.env.example` at the repo root.

## Tests

```bash
cd cockpit
pytest tests/
```

Pure-logic tests run without a broker or gRPC server:

| File | What it covers |
|---|---|
| `test_lorawan.py` | LoRaWAN math (ToA, CAF, traffic-light, PHY parsing) |
| `test_state.py` | `CampaignState`, `build_csv_row`, CSV recording, phase/antenna |
| `test_chirpstack.py` | `set_device_profile` stub interactions (mocked gRPC) |
| `test_phase.py` | `_apply_phase_to_devices` aggregation + conditional `set_phase` |
| `test_db.py` | `db.py` primitives: nodes, placement close-on-create, photo max-3, run lifecycle, gateway-move guard primitives, per-run CSV row content, Phase B sweep columns (migration on a simulated pre-Phase-B schema, `start_run(sf_schedule=...)`, `advance_run_segment`, `get_last_run`) |
| `test_workflow.py` | F-0006 route handlers called directly (no HTTP layer): `_resolve_run_placements`, run start/stop, relocate, gateway move + force, `GET /api/nodes` (`photo_ids`/`active_run`/`last_run` shape), `GET /api/runs` (flattened floor/room/description); Phase B `_resolve_schedule` defaulting, sweep-mode `POST /api/run/start` (ChirpStack profile switch + interval downlink, mocked), `_process_run_sweep`/`_sf_sweep_tick` (segment advance, schedule-complete, per-run failure isolation) |
| `test_scheduler.py` | Pure Phase B decision logic: `evaluate_run_schedule` (segment-boundary advance, end-of-schedule/planned_seconds done, no-schedule passthrough), `run_summary_fields` (progress/elapsed/current_sf, frozen at `ended_at` for finished runs), `default_sf_schedule`, `parse_iso`/`parse_schedule` |
| `test_ingest.py` | MQTT ingest calls `db.record_uplink_for_run` on every uplink; a DB error never crashes the ingest loop |

Frontend (`app/static/{index.html,app.js,style.css}`) has no automated
tests — verified manually against the endpoints above (mobile-first, dark
theme, German UI; see `docs/developer/` for the manual verification note
if one exists for this directive).
