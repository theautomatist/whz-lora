# Cockpit Redesign — Consolidated Design Specification

**Status:** revision 2 — committee review complete, product owner decisions
recorded. This is the build contract.
**Date:** 2026-08-25

**How this was produced.** Two architects (usability, process) drafted
independently; the main session merged them; two critics (field reality,
technical risk) attacked the merge against the real code and a consistent
snapshot of the real field data. Every claim below that carries a number was
checked against `cockpit-data/cockpit.db` or a named source line. Where a
critic was wrong, that is recorded too — see §3.

---

## 1. Product owner decisions

| Question | Decision |
|---|---|
| Data model | New schema, old data migrated and viewable |
| Event granularity | **Milestones only** — no row per uplink |
| Multiple devices per room | Happens, but rarely → informational hint, never a block |
| Build approach | **Staged, safety net first** |
| Scope | Cut as the field critic proposed, **except the map keeps its own area** |
| Where to run it | Locally on the developer PC |

## 2. Why this exists

The interface reads as assembled from unrelated parts because it is. The
survey found it concretely: the same run list rendered two different ways
from the same endpoint (table vs. cards) with **different time formats**
(raw UTC vs. local time); six parallel button systems; three marker
implementations; `#main` and `#history-view` carrying identical but
duplicated rules while `#map-view` has none at all and is therefore
unbounded and gutterless; 153 inline style assignments carrying visibility
state; 34 inline `onclick` attributes carrying behaviour; four breakpoints
(480/520/720/860) with no underlying scale.

That is the visible half. The other half is worse.

## 3. What the field data actually says

This section supersedes several assumptions the first draft made. Numbers
are from the verified snapshot (`PRAGMA integrity_check` = `ok`).

**The dominant failure mode is not "I mistyped in the room". It is
"finished, and nobody noticed":**

- The last run ended **11 Jul 2026**. Today is 25 Aug — **45 days with no
  measurement at all**, while the stack ran the whole time.
- `thermostat-katia` was placed on **23 Jul and never produced a run** —
  33 days of a dead device. The only feedback was a toast, which named a
  **wrong cause** ("place the gateway first") although the gateway had been
  placed since 8 Jul.
- Run 7 ran **four hours with zero packets** and sits in the table as
  `done`.
- The device card shows **"done ✓" today** for a run that ended 45 days ago
  in a room the device has since left (`app.js:2202`).

**The real interaction is fast and correction-heavy, not deliberate:**

- Median between "placement saved" and "run started": **~5 seconds**.
- Three devices placed and started in **71 seconds** on 8 Jul.
- Placements 7 → 8 → 10 for one node within **40 seconds** — save, notice
  it's wrong, save again.
- **9 of 10 placements have empty floor *and* empty room.** The operator
  skipped that field 90 % of the time.
- All 7 runs have **identical** parameters. The "Customize" panel changed
  nothing in the entire recorded campaign.

**A correction to one critic's finding.** Critic 2 reported that no data
frames have been recorded since 1 Aug and attributed it to a silent discard
path. The observation is right; the cause is not. The running process
reports `coex_unknown_frames = 333`, `own = 0`, `foreign = 0` — and 333 is
exactly the number of join requests recorded in August. Discarded data
frames would appear in that same unknown bucket. They do not, so **no data
frames are arriving**: the gateway moved from the WHZ to a home location on
1 Aug and there is simply no LoRaWAN traffic in range. Reception works.

The discard path is nevertheless a **real latent defect** and gets its own
ticket, not a place in this redesign: when `known_addrs` is empty — the
ChirpStack pre-fetch is best-effort with silent exception handling
(`main.py:225-236`) — `is_own` stays `None` (`state.py:520-522`) and
`state.py:634` then drops every data frame. The RF survey would silently
collect nothing.

## 4. The data-loss finding — the reason this is not cosmetic

**A join of one of our own devices is only ever a toast.** It is persisted
nowhere. Own uplinks land only in per-run CSVs. Only *foreign* traffic
reaches `rf_frame`, and `state.py:607-609` explicitly excludes our own
devices from even that.

Field sequence: place the device, tap save, the 24 h sweep auto-starts, turn
towards the door — the toast is already gone. There is now no way to check
whether the join happened short of walking back. Worst case it surfaces
24 hours later at CSV export, as an empty sweep.

The `thermostat-katia` case above is this failure, realised, for 33 days.
The event table is therefore a **correctness requirement**.

## 5. Usage context

Three modes, distinguished by time pressure and posture:

| Mode | Situation | Time pressure |
|---|---|---|
| **A — on-site action** | standing in the room, one hand free | high: an error costs a second trip |
| **B — on-site check** | walking a corridor, a glance | medium |
| **C — evaluation** | seated at a desk | low; tolerates density |

Governing rule from mode A: **success or failure must be visible before the
person leaves the room.**

## 6. Hard constraints

- **Offline-capable, no CDN.** Everything ships self-contained.
- Raspberry Pi 5 (ARM), container limited to 512 MB.
- Auth stays HTTP Basic via the browser dialog.
- **No bundler.** ES modules (`<script type="module">`) served by the
  existing `StaticFiles` mount are permitted and recommended — zero build,
  no `node_modules` on an ARM host. Precedent: `chirpstack/package.json`
  exists solely so `node --check` accepts ES modules; the same two-liner
  goes under `cockpit/app/static/`.
- **Prerequisite for modules:** the 34 inline `onclick` handlers call global
  functions that module scope removes. They break silently at runtime, not
  at load. Removing them is a **separate, testable step before**
  modularisation — not a side effect of it.
- KISS is the governing principle.

## 7. RESOLVED — the leading object is the device

The critics split. The field critic wins on evidence: **45 of the last 48
days had no running run.** A run list would have been an empty screen
during exactly the period when action was most overdue. An object that does
not exist 94 % of the time cannot be the front door.

The edge case "run just finished" is not an argument for the run — it is the
proof that run *status* fails as a sort key. **"Finished" is not a state,
it is an age.** "Finished 3 minutes ago, go collect it" and "finished 45
days ago, it has been sitting there for a month" are the same status and
completely different jobs.

**Landing view = device list, sorted by computed need-for-action, each row
stating reason and age in plain words:**

```
thermostat-katia    placed 23 Jul · no run for 33 d      ← red
HomeMatic - DNT     running · 0 packets for 4 h          ← red
EVA                 finished 45 d ago · not relocated    ← amber
thermostat-maurice  running · 47 % · SF9                 ← green
```

The run remains a full data object with its own detail view and history. It
is simply not the door.

## 8. RESOLVED — no wizard

The process architect proposed merging "place" and "start run" into a
multi-step wizard. The data refutes it: the median place-to-start gap is
5 seconds, the frequent case is *correction* (three saves in 40 seconds),
the schedule step was never used, and the room field was skipped 90 % of the
time. A four-step wizard cannot beat 24 seconds per device; it can only
double it. There is also **no draft persistence anywhere** in `app.js`
(zero `localStorage`/`sessionStorage` hits), so an interrupted wizard loses
everything, whereas today the whole act is one POST.

**Instead:** the sheet stays one screen and one POST. The three decided
values appear on the device card as tappable chips — `Room ⌄` ·
`Plan ⌄` · `24 h · SF7→9→12 ⌄`. One tap opens that one field, not a
sequence. A linear flow exists only for genuine first-time setup (gateway
never placed), which occurred exactly once in the recorded data.

The wizard's *goals* still hold and are met differently: the gateway
precondition is checked and shown up front instead of as a late HTTP 409
(this is real — placements 7 and 8 were created **before** the gateway
placement and their run starts hit 409, which is why the node was placed a
third time); the hidden auto-start is removed; the modal-then-form chain
becomes one screen.

## 9. Status system

**Four states, and colour never carries meaning alone** — text and age do,
colour reinforces:

| State | Meaning |
|---|---|
| green | running, healthy |
| amber | needs attention soon (finished and not collected, PDR below threshold) |
| red | needs attention now (no run despite placement, zero packets, error) |
| grey | **deliberately retired only** (`node.retired_at`) |

Grey is not "idle". Idle-but-should-not-be is red or amber, because that is
the failure this campaign actually had.

**No fifth "awaiting server confirmation" colour.** Blue is already taken —
`--m-ok: #60a5fa` means "good signal" today (`style.css:32`) and renders on
the very cards that would reuse it — and blue against grey measures
**1.23:1** contrast in the dark theme, i.e. distinguishable by hue alone,
which glare destroys first. In-flight state is the button itself, disabled
with "Saving…" (the pattern already exists at `app.js:1249-1250`). Failure
is a **red bar with a retry button and plain text**, not a colour to
decipher.

**Note the deliberate inversion:** today a *running* run is **red**
(`style.css:501`). The new scheme makes running green. This is a learned
habit being changed on purpose; it must be called out in the release note.

Contrast target is **WCAG AA (4.5:1)**, not AAA. Measured against the card
background, the current palette already fails AAA on red (5.66), grey
(5.01) and blue (6.16), and indigo `#6366f1` — the SF12 and gateway-marker
colour — fails even AA at 3.50. AA is honest and achievable; AAA would mean
re-tuning the whole palette including chart colours hard-coded in
`app.js:1464-1468`.

## 10. Card and layout system

One card implementation per concept — one run card serving live and history,
one marker popover instead of three marker implementations.

**Density: what must go from the device card.** A card today is ~200 px; a
390×844 phone with a bottom tab bar leaves ~600 px, i.e. three cards for
five nodes — while asking "which device needs attention?". Removed:

1. the photo strip (44 px; only 3 of 10 placements have photos),
2. the `.nc-meta` row (the same two facts appear again directly below),
3. the RSSI/SNR/SF triple (PDR is the relevant figure; RSSI barely varies
   with SF).

What remains — name, reason for attention, one number — is ~72 px, so all
five nodes plus the tab bar fit one screen.

**Touch targets: 56 px for primary actions**, 8 px minimum spacing. Note the
first draft aimed at the wrong marker: the 16 px one is a read-only history
thumbnail with no handler. The actual hazard is `.map-marker-remove`
(`style.css:1093-1099`) — 18 px, positioned `top:-4px; right:-12px`, i.e.
**overlapping the 28 px drag handle**. Delete and drag sit under one
thumbprint. Fixing that is in scope; it was previously unprioritised.

**Safe area.** `index.html:5` sets `viewport-fit=cover` but `style.css` has
**zero** `safe-area` references, and `#toast` is pinned at `bottom: 24px` —
underneath a future tab bar. Tab bar, toast and any bottom action must share
that strip explicitly, with `env(safe-area-inset-bottom)` honoured.

**Manual light/dark toggle, one tap in the header** — window frontage and
basement corridor follow each other within one round, faster than any
ambient heuristic tracks.

## 11. Navigation

Bottom tab bar (thumb zone). Areas: **Devices** (landing, sorted by
need-for-action) · **Map** · **History** · **Events**.

The map keeps its own area by product owner decision. Recorded so the
implementer knows what it is today: exactly one floorplan, literally named
`Building (isometric placeholder)`, the code states three times that the
coordinates are not real, the building has multiple floors (a placement
records `floor='3'`) and there is one plan for all of them — and it
currently shows 2 of 5 nodes and no gateway (see §14). Treat it as a
placeholder area to grow into, not a finished feature.

Depth: level 1 tabs; level 2 one tap (device detail, run detail, placement
sheet, marker popover); level 3 deliberately buried (RF deep analysis, sweep
parameters, raw export, floorplan management). The nine-section RF panel
leaves the landing view — it sits today in the screen opened most often
under time pressure.

**Back navigation and draft state.** `switchView()` only toggles `display`;
there is zero `pushState`/`popstate`/`hash` and zero
`localStorage`/`sessionStorage`. With tabs, the Android back button and iOS
edge-swipe leave the app. Required: `history.pushState` per tab and detail,
and `sessionStorage` for open sheet fields. Together ~20 lines, and the
precondition for §12's "scroll position survives back-navigation".

## 12. Lists

Cut to what the data justifies, per product owner decision.

> **Amended after the operational audit (§19).** The cuts below were argued
> from "there are only 7 runs". That reasoning is sound for the *run* list
> and wrong as a blanket statement: the RF panel's lists carry 332, 53 and
> 55 423 rows. Everything in this section applies to the run and event
> lists; the RF lists are governed by §19, which supersedes the decision to
> treat that panel as "unchanged" until stage 6.

**Kept:**
- **"Load more", not infinite scroll** — infinite scroll devalues the
  scrollbar as an orientation cue. No virtualisation.
- **Keyset pagination** (`WHERE id < :cursor ORDER BY id DESC LIMIT :n`)
  **for the event log only** — that is where rows accumulate.
- **Filters as a permanently visible chip row.**
- **Empty states distinguish two cases**: genuinely empty ("No runs yet —
  start one") vs. filtered empty ("No run matches this filter — reset").
  Conflating them makes a filter look like a bug.
- **Scroll position survives back-navigation** (requires §11).

**Cut — ceremony at this data volume:**
- Pagination and "load more" for the **run list**. There are 7 runs.
- Time grouping "Today / Yesterday / This week". All 7 runs fall in ISO
  week 28; the grouping would render exactly one sticky header over the
  entire dataset.
- The **"N new events" autoscroll pill**. At milestone granularity that is
  ~4 events per device per day — mechanism without occasion.
- **Skeleton cards.** A local Pi on the same Wi-Fi returning five objects
  does not need them, and they are a second rendering of every card to keep
  in sync — against "one card implementation per concept".
- **Undo snackbar.** Another transient element in the same crowded bottom
  strip, for a loss worth one photo out of six in the whole campaign. The
  existing confirm modal already works.

**SSE stays a full-refresh trigger, not a lean per-object marker.** The
first draft proposed lean markers; the technical critic showed why that is
unsafe here: the server queue is `maxsize=200` and silently drops the
**oldest** message when full (`state.py:111-121`), and the client reconnects
after 4 s with **no resynchronisation** — no `Last-Event-ID`, no refetch on
open. Today a lost marker is harmless because every marker triggers a full
`loadNodes()`. With lean markers a lost one leaves a card permanently wrong
— in exactly mode A. **If** lean markers are wanted later, the event
table's rowid is the natural SSE id: emit `id:`, honour `Last-Event-ID`,
replay on reconnect. That is the one place where the event table genuinely
simplifies the architecture.

## 13. Feedback and destructive actions

Toast is for redundant confirmation only. Anything with lasting value —
join, run started/ended/aborted — **always** additionally writes a durable
event row **and** changes the card's state. A 24-hour sweep gets a permanent
progress indicator, never a transient one.

**Destructive dialogues state the concrete cost in their own text:**

> Moving the gateway aborts 2 running measurements (room 214: SF9 for
> 40 min; room 118: SF7 for 5 min). Continue?

The pattern already exists in exactly one place — the stop-run confirmation
names the missing SF steps (`app.js:951-972`). Rolling it out to the other
risky points is the cheapest high-value win in this document.

## 14. Data model

**Raw measurement data stays in CSV.** Query patterns are per-run
aggregates; moving raw samples into a table adds write load and index
maintenance on a 512 MB ARM host for no query anyone asks. CSV also remains
the expected raw download for research.

**Aggregates on `run`, with the corrections the technical critic forced:**

- `GET /api/runs` uses aggregate columns and never opens a CSV. That is the
  real win: today it reads *every* run's CSV on *every* request. At 200 runs
  × 300 rows that is ~60 000 CSV rows held as dicts per concurrent request
  in a 512 MB container.
- **`/api/run/{id}/stats` stays CSV-based.** Per-SF PDR buckets every
  individual row by timestamp into its SF segment; scalar sums cannot carry
  that time axis. The first draft implied these CSV paths disappear. They
  do not.
- **Carry `rssi_n` and `snr_n` as separate counters.** Rows with no usable
  measurement are filtered out today (`ingest.py:49-50` writes empty cells
  when `rxInfo` is empty); dividing by `packets` would be systematically
  low.
- **Reconcile once at run end.** CSV append and counter commit are separate
  transactions (`db.py:749-757`), so a power cut between them leaves
  CSV = N+1 and `packets` = N — on a host that has seen hard resets. Today
  the CSV is the authority and the counter is a cheap display value, so the
  two cross-check. Making the counter authoritative removes that check.
  Therefore: recompute from the CSV exactly once in `stop_run` (300 rows,
  free) and repair `status='running'` rows at start-up.

**New: `event` table.** Milestones only, per PO decision: `join`,
`run_started`, `run_stopped`, `relocated`, `gateway_moved`,
`downlink_acked`, `downlink_nacked`, `segment_changed`, `first_uplink`.
Columns: `id`, `ts`, `type`, `node_id`, `run_id`, `payload` (small JSON),
`source` (`'live'` | `'backfill'`).

**Persist joins at the ingest call site (`ingest.py:175-177`), not in
`process_join`.** Start-up calls `campaign.process_join()` once per device
purely to populate the DevAddr table (`main.py:226-236`); persisting there
would fabricate five joins on every cockpit restart — in the very list meant
to answer "did the join happen?".

**`node` gains `retired_at`** so a dead sensor leaves the picker without
losing its history, and so grey has a real meaning (§9).

**No `campaign` table.** There has only ever been one campaign, and the
proposed enforcement mechanism does not work anyway: `UNIQUE INDEX ON
campaign(ended_at) WHERE ended_at IS NULL` was tested and admitted three
active rows — NULLs never collide in SQLite. (If a campaign table is ever
needed, the correct form is `ON campaign((ended_at IS NULL)) WHERE ended_at
IS NULL`, plus a test that inserting a second active row raises
`IntegrityError`. The first draft also claimed this mirrored "one active
placement per node" — it does not; that invariant is enforced procedurally
under a lock in `create_placement`, `db.py:406-419`, with no unique index at
all.) Three denormalised foreign keys and an invariant index for 7 runs is
modelling aesthetics. When campaign 2 arrives it is an `ALTER TABLE`.

**`map_marker` is NOT dropped in this work.** The first draft assumed its
positions also exist in `placement`. For two of four nodes they exist
**only** in `map_marker`:

| node | `map_marker` | active placement |
|---|---|---|
| 1 (gateway) | 0.448 / 0.948 | **NULL** |
| 2 (EVA) | 0.260 / 0.552 | **NULL** |
| 4 (katia) | 0.584 / 0.689 | 0.370 / 0.328 |
| 5 (maurice) | 0.220 / 0.437 | 0.053 / 0.344 |

The semantics differ too: `map_marker` was a free-floating live marker,
`placement.map_x/map_y` is deliberately frozen at placement time. Writing
old live coordinates into a closed placement would retroactively falsify the
spatial attribution of a finished run. **Action:** export the four rows to
`docs/developer/analysis/` as a CSV artefact; no automatic merge; the drop
happens one release *after* the export, never in the same one.

## 15. Migration

IDs migrate unchanged. Additive only in the first pass: new `event` table,
new columns. No `DROP`.

**Backfill only what the data actually contains** — `run_started` and
`run_stopped` with the stored `reason` (or `unknown`), every synthetic row
marked `source='backfill'` so nobody later mistakes it for measurement
evidence. Specifically **not** backfilled:

- `gateway_moved` — the gateway has exactly one placement and was never
  moved. Zero source rows.
- `relocated` — EVA has three placements within 40 seconds; those are form
  corrections, not moves. A placement-boundary heuristic would invent them.
  Node 4 changed placement 12 days after its last run ended, with no run
  involved at all.
- `run.reason` is unreliable anyway: 6 × `schedule-complete`, 1 × `NULL`;
  the two discriminating values `relocated` and `gateway-move` occur **zero
  times** in the real data.

**Permanently lost, to be stated plainly:** all join, ACK and NACK events
before migration. They were never persisted.

**The photo question is settled — and the earlier count was wrong.** An
earlier revision claimed "6 rows, 12 image files". That 12 came from
counting directory entries alongside files. Reconciled properly against the
restored data: **7 files, 6 rows, exactly one orphan**
(`photos/3/1.png`, belonging to placement 3). Every one of the 6 rows has
its file; nothing is missing in the other direction.

The cause stands: `sqlite_sequence` shows `photo=7` while the lowest
surviving id is 2, and the same early-row gap appears in `placement` (from
7), `run` (from 4) and `map_marker` (4 of 16). No code path deletes them —
`DELETE FROM` appears once in `db.py`, for the `rf_frame` retention trim.
The rows were removed outside the application; the file stayed. Reconcile
by listing the directory against existing `placement.id`.

**Schema versioning.** There is none today (`PRAGMA user_version` = 0), only
`CREATE TABLE IF NOT EXISTS` plus two column-guard migrations. Introduce
`PRAGMA user_version` with numbered steps, each in a transaction, and take a
`.backup` first. Rollback matters: if the image is rolled back, the old
`_SCHEMA` would silently recreate a dropped table **empty**, and the
operator would see an intact application with missing data.

**Protect the snapshot.** `docker-compose.yml:172` bind-mounts
`./cockpit-data:/data`, which is exactly where the only consistent copy of
the field data sits. A local `docker compose up` writes into it. A pristine
second copy is held at `_backup/pristine-cockpit-2026-08-25.db` alongside
the full tarball; migrations on the Pi must take a `.backup` as their first
step, not as a runbook sentence.

## 16. Build order

**Stage 0 — safety net. No visible result, not negotiable.**
`pytest cockpit/tests` as a CI job and a quickcheck step (it is stdlib +
sqlite, runs in seconds; today it runs only when someone remembers).
`tests/test_http.py` with `fastapi.TestClient` — there is currently **not
one** test that goes through the HTTP layer, so routing, auth, status codes,
response shapes and SSE wiring are entirely uncovered, and that is precisely
the layer this work touches. A golden test pinning `_compute_run_stats` to
today's exact numbers, so the aggregate change is provably identical. A
migration test against an anonymised copy with the same id gaps as the real
data.

**Stage 1 — event table and event list. Smallest independently useful and
showable stage.** Purely additive schema, persistence at the ingest call
sites, `GET /api/events/log` with keyset pagination, list in the UI. The
product owner can start the stack, trigger a join, reload, and see the event
still there — §4's gap closed and verifiable in one pass.

**Stage 2 — one status and card system.** Frontend only, no schema.
Precondition: inline `onclick` removed, `type="module"` introduced,
`cockpit/app/static/package.json` added. Immediately visible.

**Stage 3 — aggregates.** With the golden test as proof the numbers are
unchanged; `rssi_n`/`snr_n`; reconcile at `stop_run`; `/stats` stays CSV.

**Stage 4 — navigation rebuild** (bottom tabs, device list sorted by
need-for-action, history/back state). The large piece; requires stage 2.

**Stage 5 — `map_marker` export, then drop; photo reconciliation.**
Destructive, smallest benefit, goes last. Export is its own commit.

**Stage 6 — light/dark, RF deep analysis.**

## 17. Separate tickets — not part of this redesign

1. **`/api/relocate` starts a run with no schedule.** `main.py:1340` calls
   `start_run` without `sf_schedule`, `planned_seconds` or
   `interval_minutes`; `scheduler.evaluate_run_schedule` treats an empty
   schedule as "no sweep". So relocating a running device starts a run with
   no SF stepping, no downlink test and **no automatic end** — it runs until
   stopped by hand — while the placement path next to it starts a full 24 h
   sweep. Two paths, two entirely different measurements, identical
   labelling. Never triggered in the recorded data; latent, not harmless.
2. **The `known_addrs` discard path** (§3) — silent loss of the whole RF
   survey when the ChirpStack pre-fetch yields nothing.
3. **Photo filename collision.** `main.py:995-996` derives the filename from
   `count_photos(placement_id) + 1`; after any deleted row the counter
   points at an existing name and the next upload overwrites the file while
   the old row still references it.
4. **Legacy state machinery.** Removing the six dead routes does not remove
   what sits behind them (`state.py` point/recording/antenna, `_apply_phase_to_devices`),
   which ~35 test references still cover. Decide explicitly: leave the state
   code (then "removed" is half the truth) or remove it too (then the scope
   is larger than stated).
5. **`CLAUDE.md` says `py -3.12`**, which no longer exists on the developer
   host (3.14, 3.13, 3.10 are installed).

## 18. What the committee endorsed without reservation

The data-loss finding (§4) and its framing as a correctness requirement, not
a feature. Keyset over offset pagination where volume exists. "Load more"
over infinite scroll, and the reasoned refusal of virtualisation. Keeping
raw data in CSV. Distinguishing genuinely-empty from filtered-empty. And the
observation that the stop-run confirmation already models the right
cost-naming pattern and simply needs rolling out.

---

## 19. Operational audit — what reading the code missed

**Process correction.** Revisions 1 and 2 of this document were produced by
reading source and querying the database. Nobody ever *operated* the
interface. The product owner pointed at `#rf-vendors` and was right: it is a
very long list you cannot scroll inside its card, cannot sort, cannot filter
and cannot search. None of the four agents that examined this codebase found
it, because it is invisible in the source and obvious after one look.

Looking is now a repeatable step: `scripts/ui_audit.py` drives a real
browser against a running cockpit and reports overflow, list containment and
control inventory per view, at phone and desktop widths. Re-run it after
every UI stage.

```
python scripts/ui_audit.py --url http://localhost:8000 --user admin --password <pw>
```

### 19.1 Findings, measured

**`#rf-vendors` is unbounded — 332 rows, 8885 px, 10.5 phone screenfuls.**
It has no `max-height` and `overflow-y: visible`, so it grows to fit and
takes up 68 % of a 13 000 px page. The damning part: **the fix already
exists in the same panel.** Its two sibling lists are properly contained —
`#rf-devices` (53 rows) has `max-height: 220px; overflow-y: auto`, and
`#rf-frame-log` has `200px`. One list out of three simply never got it.
This is the "assembled from unrelated parts" complaint, measured.

**The list is mostly noise.** Sorted by join count, the informative part is
four rows (717, 264, 44, 6 joins). The remaining ~328 rows each read
"1 join". Worse, for the long tail the vendor name is unresolved, so the
name column renders `OUI 18b79e` next to an OUI column reading `18b79e` —
two columns showing the same value, 300+ times.

**34 px of horizontal overflow on a 390 px phone viewport, in every view.**
Rows are cut off at the right edge. The outermost causes are in the header:
`#pill-node`, `#pill-run`, `#dot-sse` and `#btn-help` extend to 402–440 px.
Everything below inherits the widened layout. Desktop is unaffected, which
is why it survived — the primary target device is the phone.

**Sorting and filtering exist exactly once in the whole application**, in
History (`#hist-device-filter`, `#hist-sort`). **Search exists nowhere** —
there is not a single `input[type=search]` in the interface. The lists that
most need these controls (332 vendors, 53 foreign devices) have none.

### 19.2 What follows for the plan

- **Bounded height is a rule, not a per-list decision.** Any data-driven
  list gets a cap and scrolls in place. `#card-dashboard` also exceeds a
  screenful and is covered by §10's density cuts.
- **Long tails collapse.** `#rf-vendors` shows its meaningful head and folds
  the single-join remainder behind one row ("328 further vendors, 1 join
  each"), expandable. This is information design, not pagination.
- **Redundant columns go.** Where the vendor is unresolved, show the OUI
  once.
- **Sort, filter and search belong to the list component**, not to whichever
  view someone remembered. Whatever is built in stage 2 provides them once
  and every list inherits them — that is the whole point of "one card
  implementation per concept" (§10).
- **The RF panel moves out of stage 6.** Its lists are the ones with real
  volume; deferring them was a mistake that followed from never having seen
  them. The horizontal overflow is a defect to fix immediately, independent
  of any redesign stage.

### 19.3 Photos are served at full camera resolution

Measured against the restored field data: `/api/photo/{id}` returns
**2.1–4.0 MB per image**, straight from what the phone camera wrote. There
is no thumbnail path and no downscaling anywhere —
`POST /api/photo/{placement_id}` (`main.py:988-1005`) writes the uploaded
bytes verbatim.

A placement with the permitted maximum of three photos therefore transfers
roughly **7 MB** to render one card, and the device card carries a photo
strip that loads them. On a phone inside a building, on the same Wi-Fi the
operator is walking in and out of, that is the difference between a card
that appears and a card that hangs.

Consequence for the plan: generate and serve a bounded thumbnail (the strip
and any list only ever need a few hundred pixels), keep the original behind
an explicit full-size request. This also removes one of the reasons §10
cuts the photo strip from the device card — with thumbnails the strip could
plausibly stay, which is a decision for the design variants rather than a
foregone conclusion.

### 19.4 A self-inflicted incident worth recording

While preparing the local working copy, `rm -rf cockpit-data` failed with
"Device or resource busy". It was **not** a no-op: it had already deleted
the directory's contents and only failed on the directory itself. The
follow-up step restored `cockpit.db` alone, so `photos/`, `floorplans/` and
all run CSVs stayed deleted — noticed by the product owner, not by the
tooling, when the interface showed no images.

Everything was recoverable from the tarball. Two lessons, both cheap:

- A failed destructive command is not necessarily a command that did
  nothing. Verify the resulting state, do not infer it from the exit
  message.
- The working copy needs a fixture check. Any migration or restore step
  should end by reconciling `photo` and `floorplan` rows against files on
  disk — the same reconciliation §15 already requires for orphans, run as
  an assertion rather than as a one-off investigation.
