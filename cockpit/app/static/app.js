/* app.js — Field-Test Cockpit frontend (vanilla JS, no framework)
   F-0006 field-measurement workflow — device-centric, no GPS.
   Visual/UX layer applies 6 psychology principles (smart defaults,
   goal-gradient, reciprocity, endowment/IKEA, loss aversion, contrast/
   anchoring) on top of the unchanged backend contracts. */
'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const _devMetrics = {};   // { dev_eui: { rssi, snr, sf, f_cnt, pdr, acked, downlinks_sent, dl_pdr, lastUplinkAt, intervalSeconds } }
let _currentDevices = []; // last /api/devices (ChirpStack) result — used by Vicki bulk

let _nodes      = [];     // last /api/nodes result
let _nodesById  = {};
let _selectedNodeId = null;
let _prevDone   = {};     // { nodeId: bool } — tracks last_run.status==='done' to fire the celebration once

let _devConfigStatus = null; // { nodeId, last_uplink_at, interval_seconds, queued, last_downlink_at } — Device status (Trust & visibility), fetched only for the selected device

let _sheetMode    = null; // 'device' | 'gateway'
let _sheetAntenna = '3dbi';
let _sheetPhotos  = [];   // File[] queued for upload after the placement is created
let _gatewayForce = false; // set by onMoveGatewayClick() before opening the gateway
                            // sheet — true when the pre-flight conflict check already
                            // got the operator's "end the running measurements" OK, so
                            // submitSheet() must call /api/gateway/move/force, not the
                            // plain /api/gateway/move. Reset on sheet open (device mode)
                            // and close — see openPlaceSheet()/closeSheet().
// F-0008 Map / Placement Editor — the sheet's optional "Position on floor
// plan" control. _sheetFloorplan is the current floorplan (or null — hides
// the control), fetched fresh on every sheet open; _sheetMapPosition is
// the pending {x,y} tap (or null — no position), submitted as map_x/map_y
// alongside floor/room/photos. See loadSheetMapPosition()/onSheetMapTap().
let _sheetFloorplan    = null;
let _sheetMapPosition  = null;

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

function toast(msg, ms = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), ms);
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiFetch(path, opts = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const res = await fetch(path, Object.assign(defaults, opts));
  if (res.status === 401) { toast('Not authenticated — use the browser dialog.'); throw new Error('401'); }
  return res;
}

async function apiJSON(path, opts = {}) {
  const res = await apiFetch(path, opts);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

/** Extract a human-readable message from a FastAPI error response body. */
async function extractDetail(res) {
  try {
    const body = await res.json();
    const d = body.detail;
    return typeof d === 'string' ? d : JSON.stringify(d);
  } catch (_) {
    return `HTTP ${res.status}`;
  }
}

/** Upload a photo file to a placement — must NOT set Content-Type manually
 * (the browser sets the multipart boundary). */
async function uploadPhoto(placementId, file) {
  const fd = new FormData();
  fd.append('file', file, file.name || 'photo.jpg');
  const res = await fetch(`/api/photo/${placementId}`, { method: 'POST', body: fd });
  if (res.status === 401) { toast('Not authenticated.'); throw new Error('401'); }
  if (!res.ok) throw new Error(await extractDetail(res));
  return res.json();
}

// ---------------------------------------------------------------------------
// Campaign status (Hero) — goal-gradient, never zero (principle 2)
// ---------------------------------------------------------------------------

const HERO_RING_R    = 52;
const HERO_RING_CIRC = 2 * Math.PI * HERO_RING_R;

function initHeroRing() {
  const ringFill = document.getElementById('hero-ring-fill');
  if (!ringFill) return;
  ringFill.style.strokeDasharray = `${HERO_RING_CIRC}`;
  ringFill.style.strokeDashoffset = `${HERO_RING_CIRC}`; // start fully empty, animates in on first render
}

/** Per-device progress term (0..1) feeding the campaign ring below, plus
 * enough detail (state/fraction/live run) for the hero's per-device
 * breakdown list (renderHeroDeviceList). Mutually exclusive states:
 *   not-placed -> 0
 *   placed     -> 0.4  (placed, never run)
 *   running    -> 0.4 + 0.6 x live elapsed/planned fraction (0..1, clamped;
 *                 0 when the run has no planned duration to extrapolate
 *                 against — e.g. a Phase A run with no sweep)
 *   done       -> 1.0  (a completed last_run and nothing running now)
 * liveRunProgress (defined below) does the wall-clock extrapolation, so
 * this stays accurate between /api/nodes refreshes too. */
function deviceProgressTerm(n) {
  if (n.active_run && n.active_run.status === 'running') {
    const live = liveRunProgress(n.active_run);
    const frac = live.progress != null ? Math.max(0, Math.min(1, live.progress)) : 0;
    return { state: 'running', value: 0.4 + 0.6 * frac, run: n.active_run, live, frac };
  }
  if (n.last_run && n.last_run.status === 'done') {
    return { state: 'done', value: 1, run: n.last_run };
  }
  if (n.placement) {
    return { state: 'placed', value: 0.4, run: null };
  }
  return { state: 'not-placed', value: 0, run: null };
}

/** progress = (1 [Setup] + gatewayPlaced + Σ per-device term) / (2 + N_devices)
 * Setup contributes a flat 1 so the ring is never 0 — the operator always
 * sees credit for showing up and getting the app running. Each device's
 * term (see deviceProgressTerm) is fine-grained while a run is actually in
 * progress rather than a fixed step, so the ring moves smoothly. */
function computeCampaignProgress() {
  const gateway = _nodes.find(n => n.kind === 'gateway');
  const devices = _nodes.filter(n => n.kind === 'device');
  const gatewayPlaced = !!(gateway && gateway.placement);

  let deviceSum = 0, doneCount = 0, runningCount = 0, placedCount = 0;
  const deviceTerms = devices.map(n => {
    const term = deviceProgressTerm(n);
    deviceSum += term.value;
    if (term.state === 'done') doneCount++;
    if (term.state === 'running') runningCount++;
    if (n.placement) placedCount++;
    return Object.assign({ node: n }, term);
  });

  const numerator = 1 + (gatewayPlaced ? 1 : 0) + deviceSum;
  const denominator = 2 + devices.length;
  const progress = denominator > 0 ? Math.max(0, Math.min(1, numerator / denominator)) : 0.5;

  return { progress, gatewayPlaced, deviceCount: devices.length, doneCount, runningCount, placedCount, deviceTerms };
}

function renderHero() {
  const pctEl     = document.getElementById('hero-pct');
  const ringFill  = document.getElementById('hero-ring-fill');
  const subEl     = document.getElementById('hero-sub');
  if (!pctEl || !ringFill || !subEl) return;

  const { progress, gatewayPlaced, deviceCount, doneCount, runningCount, deviceTerms } = computeCampaignProgress();

  pctEl.textContent = `${Math.round(progress * 100)}%`;
  ringFill.style.strokeDashoffset = `${HERO_RING_CIRC * (1 - progress)}`;

  const parts = [gatewayPlaced ? 'Gateway ✓' : 'Gateway not placed yet'];
  if (deviceCount > 0) parts.push(`${doneCount}/${deviceCount} done`);
  if (runningCount > 0) parts.push(`${runningCount} running`);
  subEl.textContent = parts.join(' · ');

  renderHeroDeviceList(deviceTerms);
}

// running first (live, worth watching), then placed (ready/todo), then
// done (finished), then not-placed (needs setup first) — see
// renderHeroDeviceList below.
const HERO_DEVICE_STATE_ORDER = { running: 0, placed: 1, done: 2, 'not-placed': 3 };

/** "47% · 14 h of 24 h" while running (falls back to just "running" when
 * the run has no planned duration to show progress against); "done ✓" /
 * "placed" / "not placed" otherwise. */
function deviceProgressLabel(term) {
  if (term.state === 'done') return 'done ✓';
  if (term.state === 'placed') return 'placed';
  if (term.state === 'not-placed') return 'not placed';
  if (!term.run || !term.run.planned_seconds) return 'running';
  const pct = Math.round((term.frac || 0) * 100);
  return `${pct}% · ${fmtHoursOfTotal(term.live.elapsedSeconds || 0, term.run.planned_seconds)}`;
}

/** Compact per-device slice of the ring above — a thin bar per device so
 * the operator can see each device's individual progress and how much is
 * left to 100%, not just the aggregate ring. */
function renderHeroDeviceList(deviceTerms) {
  const wrap = document.getElementById('hero-devices');
  if (!wrap) return;
  if (!deviceTerms.length) { wrap.innerHTML = ''; return; }

  const sorted = deviceTerms.slice().sort(
    (a, b) => HERO_DEVICE_STATE_ORDER[a.state] - HERO_DEVICE_STATE_ORDER[b.state]
  );

  wrap.innerHTML = sorted.map(term => `
    <div class="hdev-row hdev-${term.state}">
      <div class="hdev-hdr">
        <span class="hdev-name">${esc(term.node.name)}</span>
        <span class="hdev-label">${esc(deviceProgressLabel(term))}</span>
      </div>
      <div class="hdev-bar-track"><div class="hdev-bar-fill" style="width:${Math.round(term.value * 100)}%"></div></div>
    </div>
  `).join('');
}

// ---------------------------------------------------------------------------
// Node selection + Overview (GET /api/nodes)
// ---------------------------------------------------------------------------

async function loadNodes() {
  try {
    const data = await apiJSON('/api/nodes');
    _nodes = data.nodes || [];
    _nodesById = {};
    for (const n of _nodes) _nodesById[n.id] = n;

    if (_selectedNodeId == null || !_nodesById[_selectedNodeId]) {
      const firstDevice = _nodes.find(n => n.kind === 'device');
      const fallback = firstDevice || _nodes[0];
      _selectedNodeId = fallback ? fallback.id : null;
    }

    renderHero();
    renderNodeSelect();
    renderSelectedNode();
    renderNodeDashboard();
    refreshDeviceStatus(); // fire-and-forget — Device status (Trust & visibility)
  } catch (e) {
    toast(`Error loading devices: ${e.message}`);
  }
}

function renderNodeSelect() {
  const sel = document.getElementById('node-select');
  if (!_nodes.length) {
    sel.innerHTML = '<option value="">— no devices —</option>';
    return;
  }
  sel.innerHTML = _nodes.map(n =>
    `<option value="${n.id}">${n.kind === 'gateway' ? 'Gateway: ' : ''}${esc(n.name)}</option>`
  ).join('');
  if (_selectedNodeId != null) sel.value = String(_selectedNodeId);
}

function onNodeSelect() {
  const sel = document.getElementById('node-select');
  const id = parseInt(sel.value, 10);
  if (!isNaN(id)) selectNode(id);
}

/** Select a node. When *scroll* is true (card tap in the Overview), the
 * "Selected device / gateway" detail panel is scrolled into view. */
function selectNode(id, scroll = false) {
  _selectedNodeId = id;
  const sel = document.getElementById('node-select');
  if (sel) sel.value = String(id);
  renderSelectedNode();
  renderNodeDashboard();
  refreshDeviceStatus(); // fire-and-forget — Device status (Trust & visibility)
  if (scroll) {
    const panel = document.getElementById('card-selected');
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ---------------------------------------------------------------------------
// Reciprocity — live signal shown immediately on selection (principle 3)
// ---------------------------------------------------------------------------

/** excellent / good / marginal / poor — same thresholds as rssiClass,
 * labelled so the number is never shown "bare" (contrast/anchoring). */
function rssiQualityLabel(v) {
  if (v == null) return { cls: '', label: '—' };
  if (v > -80)  return { cls: 'm-good', label: 'excellent' };
  if (v > -110) return { cls: 'm-ok',   label: 'good' };
  if (v > -120) return { cls: 'm-warn', label: 'marginal' };
  return { cls: 'm-bad', label: 'poor' };
}

function fmtAgo(ms) {
  if (ms == null) return '';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return `${h} h ago`;
}

/** ≥60 -> "~N min" (rounded), else "~N s"; null -> "—". Shows the actual
 * measured cadence so the operator can confirm a Vicki interval change
 * (e.g. the 5-min downlink) has really taken effect. */
function fmtInterval(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `~${Math.round(seconds)} s`;
  const minutes = seconds / 60;
  // Hours once we're well past the minute range (e.g. a Vicki device still
  // on its ~4 h factory default, before the 5-min command has taken effect)
  // — "~240 min" is technically correct but much less glanceable than "~4 h".
  if (minutes < 60) return `~${Math.round(minutes)} min`;
  return `~${Math.round(minutes / 60)} h`;
}

function ageFromUplinkAt(lastUplinkAt) {
  if (!lastUplinkAt) return '—';
  return fmtAgo(Date.now() - new Date(lastUplinkAt).getTime());
}

/** "Last packet: 12 s ago · Send interval: ~5 min" — small muted
 * metadata line shown on each Overview card (the selected-device panel
 * shows the same two facts, more prominently, in the Device status block
 * instead — not repeated here). */
function metaLineText(m) {
  const age = m ? ageFromUplinkAt(m.lastUplinkAt) : '—';
  const interval = m ? fmtInterval(m.intervalSeconds) : '—';
  return `Last packet: ${age} · Send interval: ${interval}`;
}

/** Big RSSI number + quality label only — "Last packet"/"Send interval"
 * live exclusively in the Device status block below (no duplication). */
function renderSignalHero(node) {
  const wrap = document.getElementById('signal-hero');
  if (!wrap) return;
  if (!node || node.kind !== 'device') { wrap.style.display = 'none'; return; }

  const m = _devMetrics[node.eui];
  if (!m || m.rssi == null) { wrap.style.display = 'none'; return; }

  wrap.style.display = '';
  const numEl = document.getElementById('signal-hero-rssi');
  const qEl   = document.getElementById('signal-hero-quality');

  numEl.textContent = fmtNum(m.rssi);
  const q = rssiQualityLabel(m.rssi);
  qEl.textContent = q.label;
  qEl.className = 'signal-hero-quality ' + q.cls;
}

let _signalAgeTimer = null;

/** Cheap 1 s ticker — updates every visible Overview card's "Xs ago" meta
 * line and the Device status block's age text, no re-render (plain
 * textContent updates / renderDeviceStatusBlock is itself cheap). */
function startSignalAgeTicker() {
  if (_signalAgeTimer) return;
  _signalAgeTimer = setInterval(() => {
    for (const n of _nodes) {
      if (n.kind !== 'device') continue;
      const m = _devMetrics[n.eui];
      const el = document.getElementById(`nc-meta-${n.id}`);
      if (el && m) el.textContent = metaLineText(m);
    }
    renderDeviceStatusBlock(); // cheap re-render of "Xs ago" text, no fetch
  }, 1000);
}

// ---------------------------------------------------------------------------
// Selected device / gateway
// ---------------------------------------------------------------------------

/** Location block markup — floor/room/description/note[/antenna]. Shared by
 * the Selected-device panel and the History detail view (F-0007, both the
 * device AND the gateway placement there). */
function placeInfoHtml(p, opts = {}) {
  const emptyText = opts.emptyText || 'Not placed yet.';
  if (!p) return `<div class="place-empty">${esc(emptyText)}</div>`;
  const antennaLine = opts.showAntenna && p.antenna
    ? `<div class="place-note">Antenna: ${esc(p.antenna === '12dbi' ? '12 dBi' : '3 dBi')}</div>`
    : '';
  return `<div class="place-loc">${esc(p.floor || '—')} · ${esc(p.room || '—')}</div>
    <div class="place-desc">${esc(p.description || '—')}</div>
    ${p.note ? `<div class="place-note">${esc(p.note)}</div>` : ''}
    ${antennaLine}`;
}

/** Larger photo thumbnails (not the small Overview-card photoStripHtml) —
 * "your collection" (endowment), shared by the Selected-device panel and
 * the History detail view. */
function photoThumbsHtml(photoIds) {
  if (!photoIds || !photoIds.length) return '';
  return photoIds.map(id => `<div class="pthumb view"><img src="/api/photo/${id}" alt="Photo" loading="lazy"></div>`).join('');
}

function renderSelectedNode() {
  const node          = _nodesById[_selectedNodeId];
  const nameEl        = document.getElementById('sel-name');
  const euiEl         = document.getElementById('sel-eui');
  const runPill       = document.getElementById('sel-run-pill');
  const placeInfo     = document.getElementById('sel-place-info');
  const photosEl      = document.getElementById('sel-photos');
  const metricsEl     = document.getElementById('sel-metrics');
  const progressEl    = document.getElementById('sel-progress');
  const btnPlace      = document.getElementById('btn-place');
  const runStartBlock = document.getElementById('run-start-block');
  const btnStop       = document.getElementById('btn-run-stop');
  const btnGwMove     = document.getElementById('btn-gw-move');
  const histDetails   = document.getElementById('history-details');
  const devStatusBlock = document.getElementById('dev-status-block');

  updateHeaderPills(node);
  renderSignalHero(node);

  if (!node) {
    nameEl.textContent = 'No devices available';
    euiEl.textContent = '';
    runPill.style.display = 'none';
    placeInfo.innerHTML = '<div class="place-empty">First register a device in ChirpStack (below) and restart the cockpit.</div>';
    photosEl.innerHTML = '';
    metricsEl.style.display = 'none';
    progressEl.style.display = 'none';
    btnPlace.style.display = 'none';
    runStartBlock.style.display = 'none';
    btnStop.style.display = 'none';
    btnGwMove.style.display = 'none';
    histDetails.style.display = 'none';
    if (devStatusBlock) devStatusBlock.style.display = 'none';
    loadSelectedChart();
    loadSelectedPdrStats();
    return;
  }

  nameEl.textContent = node.name;
  euiEl.textContent = node.eui;

  const isDevice = node.kind === 'device';
  histDetails.style.display = isDevice ? '' : 'none';

  // Placement
  const p = node.placement;
  placeInfo.innerHTML = placeInfoHtml(p);

  // Photos of the current placement — "your collection" (endowment)
  photosEl.innerHTML = photoThumbsHtml(p && p.photo_ids);

  if (isDevice) {
    const run = node.active_run;
    const lastRun = node.last_run;
    const justDone = !run && lastRun && lastRun.status === 'done';

    runPill.style.display = '';
    if (run) {
      runPill.textContent = `● Running — ${run.packets} packets`;
      runPill.className = 'pill on';
    } else if (justDone) {
      runPill.textContent = 'done ✓';
      runPill.className = 'pill';
    } else {
      runPill.textContent = 'No run';
      runPill.className = 'pill';
    }

    metricsEl.style.display = '';
    metricsEl.innerHTML = selMetricsHtml(_devMetrics[node.eui] || {});

    // Sweep timeline only while a run is actually active — a finished run's
    // progress is already conveyed by the "done ✓" pill above and its own
    // chart in History below, not repeated here.
    const progressHtml = run ? runProgressHtml(run, { compact: false }) : '';
    progressEl.style.display = progressHtml ? '' : 'none';
    progressEl.innerHTML = progressHtml;

    btnPlace.textContent = 'Place / Relocate';
    btnPlace.style.display = '';
    btnGwMove.style.display = 'none';
    runStartBlock.style.display = run ? 'none' : '';
    btnStop.style.display = run ? '' : 'none';

    if (devStatusBlock) devStatusBlock.style.display = '';
    renderDeviceStatusBlock();
  } else {
    runPill.style.display = 'none';
    metricsEl.style.display = 'none';
    progressEl.style.display = 'none';
    btnPlace.style.display = 'none';
    runStartBlock.style.display = 'none';
    btnStop.style.display = 'none';
    btnGwMove.style.display = '';
    if (devStatusBlock) devStatusBlock.style.display = 'none';
  }

  loadSelectedChart();
  loadSelectedPdrStats();
  setMsg(document.getElementById('selected-msg'), '');
}

function updateHeaderPills(node) {
  const nodePill = document.getElementById('pill-node');
  const runPill  = document.getElementById('pill-run');
  if (!node) {
    nodePill.textContent = '—';
    runPill.style.display = 'none';
    return;
  }
  nodePill.textContent = node.name;
  if (node.kind === 'device') {
    const running = !!(node.active_run && node.active_run.status === 'running');
    runPill.style.display = '';
    runPill.textContent = running ? '● Running' : 'No run';
    runPill.className = 'pill' + (running ? ' on' : '');
  } else {
    runPill.style.display = 'none';
  }
}

/** Compact, muted single line under the signal hero — SNR/SF only; the big
 * number in #signal-hero is the one and only place RSSI is shown, and PDR
 * now lives in the "PDR per SF" headline block (per-SF, not this single
 * always-empty legacy figure — see renderPdrSfBlock). */
function selMetricsHtml(m) {
  return `
    <span class="${snrClass(m.snr)}">SNR&nbsp;${fmtNum(m.snr)}&nbsp;dB</span>
    <span>${m.sf != null ? 'SF' + m.sf : '—'}</span>
  `;
}

function updateSelectedMetrics(eui) {
  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device' || node.eui !== eui) return;
  const metricsEl = document.getElementById('sel-metrics');
  if (metricsEl) metricsEl.innerHTML = selMetricsHtml(_devMetrics[eui] || {});
  renderSignalHero(node);
  const numEl = document.getElementById('signal-hero-rssi');
  if (numEl) {
    numEl.classList.remove('roll');
    void numEl.offsetWidth; // reflow to restart the animation
    numEl.classList.add('roll');
  }
}

// ---------------------------------------------------------------------------
// Device status — "is the configuration working?" (Trust & visibility)
//
// LoRaWAN Class A only delivers a queued downlink right after the device's
// own next uplink — a silent device means nothing has reached it yet. This
// block makes that visible: last packet age, measured vs. target send
// interval, and whether a config downlink is still queued or already sent.
// ---------------------------------------------------------------------------

/** Target interval (minutes) = the active run's interval_minutes, else the
 * 5-min default (matches the default sweep / Vicki keep-alive command). */
function targetIntervalMinutes(node) {
  const run = node && node.active_run;
  return (run && run.interval_minutes) ? run.interval_minutes : 5;
}

/** Duration without the "ago"/"silent for" wrapper, e.g. "12 s", "4 h". */
function fmtDuration(ms) {
  if (ms == null) return '';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h`;
}

/** Most prominent/colored line in the block: never sent, silent, or fine. */
function deviceStatusLastPacket(m, node) {
  if (!m || !m.lastUplinkAt) {
    return { text: 'waiting for first packet ⚠', cls: 'm-warn' };
  }
  const ageMs = Date.now() - new Date(m.lastUplinkAt).getTime();
  const targetSeconds = targetIntervalMinutes(node) * 60;
  if (ageMs > targetSeconds * 2000) {
    return { text: `silent for ${fmtDuration(ageMs)} ⚠`, cls: 'm-bad' };
  }
  return { text: fmtAgo(ageMs), cls: 'm-good' };
}

/** "~5 min ✓ (target reached)" vs. "~4 h ⚠ (still default)" — tolerance of
 * ±20 % (min. ±1 min) around the target counts as "reached". */
function deviceStatusInterval(m, node) {
  if (!m || m.intervalSeconds == null) return { text: '—', cls: '' };
  const target = targetIntervalMinutes(node);
  const measuredMin = m.intervalSeconds / 60;
  const tolerance = Math.max(1, target * 0.2);
  const reached = Math.abs(measuredMin - target) <= tolerance;
  const text = `${fmtInterval(m.intervalSeconds)} ${reached ? '✓ (target reached)' : '⚠ (still default)'}`;
  return { text, cls: reached ? 'm-good' : 'm-warn' };
}

/** "5-min command queued" (still waiting for the device's next uplink) vs.
 * "sent ✓ 12 s ago" (txack/ack seen) vs. "—" (no config downlink involved). */
function deviceStatusConfigDl(status) {
  if (!status) return { text: '—', cls: '' };
  const queuedInterval = (status.queued || []).find(
    q => q.f_port === 1 && /^02[0-9a-f]{2}$/i.test(q.data_hex || '')
  );
  if (queuedInterval) {
    const minutes = parseInt(queuedInterval.data_hex.slice(2, 4), 16);
    return { text: `${minutes}-min command queued`, cls: 'm-warn' };
  }
  if (status.last_downlink_at) {
    return { text: `sent ✓ ${ageFromUplinkAt(status.last_downlink_at)}`, cls: 'm-good' };
  }
  return { text: '—', cls: '' };
}

/** Re-render the block from the currently cached _devMetrics/_devConfigStatus
 * — cheap, called every second by the signal-age ticker for smooth "Xs ago"
 * text, with no network call. */
function renderDeviceStatusBlock() {
  const block = document.getElementById('dev-status-block');
  if (!block) return;
  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') { block.style.display = 'none'; return; }

  const m = _devMetrics[node.eui] || {};
  const status = (_devConfigStatus && _devConfigStatus.nodeId === node.id) ? _devConfigStatus : null;

  const last = deviceStatusLastPacket(m, node);
  const lastEl = document.getElementById('ds-last-packet');
  if (lastEl) { lastEl.textContent = last.text; lastEl.className = 'dstatus-value ' + last.cls; }

  const interval = deviceStatusInterval(m, node);
  const intervalEl = document.getElementById('ds-interval');
  if (intervalEl) { intervalEl.textContent = interval.text; intervalEl.className = 'dstatus-value ' + interval.cls; }

  const cfgDl = deviceStatusConfigDl(status);
  const cfgEl = document.getElementById('ds-config-dl');
  if (cfgEl) { cfgEl.textContent = cfgDl.text; cfgEl.className = 'dstatus-value ' + cfgDl.cls; }
}

/** Fetch GET /api/device/{id}/config-status for the selected device only
 * (never embedded in loadNodes()/GET /api/nodes — keeps that call light).
 * Guards against a stale response landing after the selection changed. */
async function refreshDeviceStatus() {
  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') { renderDeviceStatusBlock(); return; }
  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/device/${nodeId}/config-status`);
    if (_selectedNodeId !== nodeId) return; // selection changed while awaiting
    _devConfigStatus = Object.assign({ nodeId }, data);
  } catch (e) {
    if (_selectedNodeId !== nodeId) return;
    _devConfigStatus = null;
  }
  renderDeviceStatusBlock();
}

async function setDeviceInterval5() {
  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') return;
  try {
    await apiJSON(`/api/device/${node.id}/set-interval`, {
      method: 'POST',
      body: JSON.stringify({ minutes: 5 }),
    });
    toast("5-minute command queued — takes effect on the device's next uplink.");
    await refreshDeviceStatus();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

async function wakeDeviceTest() {
  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') return;
  try {
    // 0x04 = read HW/SW version (confirmed) — reuses the existing loopback.
    await apiJSON('/api/downlink', {
      method: 'POST',
      body: JSON.stringify({ dev_eui: node.eui, f_port: 1, data_hex: '04', count: true }),
    });
    toast('Test downlink queued — device replies on its next uplink.');
    await refreshDeviceStatus();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Run progress — smooth client-side ticking between SSE events, snapped
// back to server truth (segment_index/current_sf/done) whenever a fresh
// /api/nodes payload arrives (loadNodes(), triggered by the 'nodes' SSE
// event or the 30 s ticker).
// ---------------------------------------------------------------------------

/** Recompute elapsed/progress/current segment from wall-clock time for a
 * *running* sweep; done/finished runs just echo the frozen server values. */
function liveRunProgress(run) {
  if (!run) return { elapsedSeconds: null, progress: null, currentSf: null, segmentIndex: null };
  if (run.status !== 'running' || !run.planned_seconds || !run.started_at) {
    return {
      elapsedSeconds: run.elapsed_seconds,
      progress: run.progress,
      currentSf: run.current_sf,
      segmentIndex: run.segment_index,
    };
  }

  const startedMs = new Date(run.started_at).getTime();
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
  const progress = Math.max(0, Math.min(1, elapsedSeconds / run.planned_seconds));

  let segmentIndex = run.segment_index;
  let currentSf = run.current_sf;
  if (run.sf_schedule && run.sf_schedule.length) {
    let acc = 0;
    for (let i = 0; i < run.sf_schedule.length; i++) {
      acc += run.sf_schedule[i].seconds;
      if (elapsedSeconds < acc || i === run.sf_schedule.length - 1) {
        segmentIndex = i;
        currentSf = run.sf_schedule[i].sf;
        break;
      }
    }
  }
  return { elapsedSeconds, progress, currentSf, segmentIndex };
}

/** Whole-hours "elapsed of total" — anchors the part against the whole
 * plan (contrast/anchoring), e.g. "14 h of 24 h" instead of a bare
 * "10 h left" that hides how big the plan actually is. */
function fmtHoursOfTotal(elapsedSeconds, totalSeconds) {
  const eh = Math.floor(Math.max(0, elapsedSeconds) / 3600);
  const th = Math.max(1, Math.round(totalSeconds / 3600));
  return `${eh} h of ${th} h`;
}

/** Glowing segmented SF-sweep timeline (wow factor) + an anchored label:
 * "SF9 · 2 of 3 SF stages · 14 h of 24 h". Returns '' for a run with no
 * schedule (Phase A fixed run) — caller decides what to show instead. */
function runProgressHtml(run, opts = {}) {
  if (!run || !run.planned_seconds || !run.sf_schedule || !run.sf_schedule.length) return '';
  const compact = !!opts.compact;

  const live = liveRunProgress(run);
  const idx = live.segmentIndex ?? 0;
  const total = run.sf_schedule.length;
  const sfLabel = live.currentSf != null ? `SF${live.currentSf}` : '—';
  const stepsLabel = `${Math.min(idx + 1, total)} of ${total} SF stages`;
  const timeLabel = fmtHoursOfTotal(live.elapsedSeconds || 0, run.planned_seconds);

  const segs = run.sf_schedule.map((seg, i) => {
    let state = 'future';
    let fillPct = 0;
    if (run.done || i < idx) {
      state = 'done'; fillPct = 100;
    } else if (i === idx) {
      state = 'current';
      const segStart = run.sf_schedule.slice(0, i).reduce((a, s) => a + s.seconds, 0);
      const segElapsed = Math.max(0, (live.elapsedSeconds || 0) - segStart);
      fillPct = Math.max(0, Math.min(100, (segElapsed / seg.seconds) * 100));
    }
    return `
      <div class="sweep-seg ${state}">
        <div class="sweep-seg-track"><div class="sweep-seg-fill" style="width:${fillPct.toFixed(0)}%"></div></div>
        <div class="sweep-seg-label">SF${seg.sf}${state === 'done' ? ' ✓' : ''}</div>
      </div>`;
  }).join('');

  const label = run.done
    ? `<strong>done ✓</strong> · ${esc(stepsLabel)} · ${esc(timeLabel)}`
    : `<strong>${esc(sfLabel)}</strong> · ${esc(stepsLabel)} · ${esc(timeLabel)}`;

  return `
    <div class="sweep-timeline${compact ? ' compact' : ''}">${segs}</div>
    <div class="run-progress-label${run.done ? ' done' : ''}">${label}</div>
  `;
}

// ---------------------------------------------------------------------------
// "done ✓" celebration — one-shot pop/glow on the transition to done
// ---------------------------------------------------------------------------

function checkCelebration(node) {
  if (!node || node.kind !== 'device') return;
  const isDone = !!(node.last_run && node.last_run.status === 'done');
  const was = _prevDone[node.id];
  _prevDone[node.id] = isDone;
  if (isDone && was === false) fireCelebration(node.id);
}

function fireCelebration(nodeId) {
  const card = document.getElementById(`nc-${nodeId}`);
  if (card) {
    card.classList.remove('celebrate-glow');
    void card.offsetWidth;
    card.classList.add('celebrate-glow');
  }
  if (nodeId === _selectedNodeId) {
    const pill = document.getElementById('sel-run-pill');
    if (pill) {
      pill.classList.remove('celebrate');
      void pill.offsetWidth;
      pill.classList.add('celebrate');
    }
  }
}

// ---------------------------------------------------------------------------
// Loss aversion — status text shared by the stop-run confirm and the
// gateway-move conflict list (principle 5)
// ---------------------------------------------------------------------------

/** "SF7 ✓, SF9 running — SF12 missing · 142 packets" */
function sweepStatusText(run) {
  if (!run) return '';
  if (!run.sf_schedule || !run.sf_schedule.length) return `${run.packets} packets`;
  const idx = run.segment_index ?? 0;
  const doneParts = run.sf_schedule.slice(0, idx).map(s => `SF${s.sf} ✓`);
  const current = run.sf_schedule[idx] ? [`SF${run.sf_schedule[idx].sf} running`] : [];
  const missing = run.sf_schedule.slice(idx + 1).map(s => `SF${s.sf}`);
  let text = doneParts.concat(current).join(', ');
  if (missing.length) text += ` — ${missing.join('/')} missing`;
  return `${text} · ${run.packets} packets`;
}

/** One row of the loss-framed list — shared by the gateway-move pre-flight
 * confirm modal (onMoveGatewayClick) and the in-sheet fallback conflict box
 * (showGatewayConflict). */
function _lossRowHtml(name, detail) {
  return `
    <div class="loss-row">
      <div class="loss-name">${esc(name)}</div>
      <div class="loss-detail">${esc(detail)}</div>
    </div>`;
}

function _gatewayLossTitle(count) {
  return count === 1 ? '1 running measurement will be lost' : `${count} running measurements will be lost`;
}

// ---------------------------------------------------------------------------
// Generic confirm modal (reused for stop-run + gateway-force loss prompts)
// ---------------------------------------------------------------------------

let _confirmResolve = null;

function confirmModal({ title, message, icon = '⚠️', okLabel = 'Confirm', cancelLabel = 'Cancel', listHtml = '' }) {
  return new Promise(resolve => {
    _confirmResolve = resolve;
    document.getElementById('confirm-icon').textContent = icon;
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').innerHTML = message;
    document.getElementById('confirm-list').innerHTML = listHtml;
    document.getElementById('confirm-ok-btn').textContent = okLabel;
    document.getElementById('confirm-cancel-btn').textContent = cancelLabel;
    document.getElementById('confirm-ov').classList.add('open');
    document.body.style.overflow = 'hidden';
  });
}

function _resolveConfirm(result) {
  document.getElementById('confirm-ov').classList.remove('open');
  document.body.style.overflow = '';
  const resolve = _confirmResolve;
  _confirmResolve = null;
  if (resolve) resolve(result);
}

function closeConfirmBackdrop(e) {
  if (e.target === document.getElementById('confirm-ov')) _resolveConfirm(false);
}

// ---------------------------------------------------------------------------
// Start / stop run (selected device) — timed SF-sweep
// ---------------------------------------------------------------------------

const RUN_PRESETS = {
  sf7_sf9_sf12: [7, 9, 12],
  sf9_sf12:     [9, 12],
  sf9:          [9],
  sf12:         [12],
};

/** Whether the "Downlink test" toggle is checked — read fresh on every run
 * start (the checkbox itself isn't reset between renders, see index.html). */
function isDownlinkTestEnabled() {
  const el = document.getElementById('run-downlink-test');
  return el ? el.checked : true;
}

/** Primary one-tap button: 24 h sweep SF7 -> SF9 -> SF12, 5-min interval. */
async function startSweepDefault() {
  const totalSeconds = 24 * 3600;
  const per = Math.floor(totalSeconds / 3);
  const schedule = [
    { sf: 7,  seconds: per },
    { sf: 9,  seconds: per },
    { sf: 12, seconds: totalSeconds - 2 * per },
  ];
  await startRunWithSchedule({
    duration_seconds: totalSeconds,
    sf_schedule: schedule,
    interval_minutes: 5,
    downlink_test: isDownlinkTestEnabled(),
  });
}

/** "Customize" submit: build a schedule from the duration/interval/preset fields. */
async function startSweepCustom() {
  const hours       = parseFloat(document.getElementById('run-duration-h').value) || 24;
  const intervalMin = parseInt(document.getElementById('run-interval-min').value, 10) || 5;
  const presetKey   = document.getElementById('run-preset').value;
  const sfList      = RUN_PRESETS[presetKey] || RUN_PRESETS.sf7_sf9_sf12;

  const totalSeconds = Math.max(1, Math.round(hours * 3600));
  const per = Math.floor(totalSeconds / sfList.length);
  const schedule = sfList.map((sf, i) => ({
    sf,
    seconds: i === sfList.length - 1 ? totalSeconds - per * (sfList.length - 1) : per,
  }));

  await startRunWithSchedule({
    duration_seconds: totalSeconds,
    sf_schedule: schedule,
    interval_minutes: intervalMin,
    downlink_test: isDownlinkTestEnabled(),
  });
}

async function startRunWithSchedule(payload) {
  const msg = document.getElementById('selected-msg');
  if (_selectedNodeId == null) return;
  try {
    const res = await apiFetch('/api/run/start', {
      method: 'POST',
      body: JSON.stringify(Object.assign({ device_node_id: _selectedNodeId }, payload)),
    });
    if (res.ok) {
      toast('Run started — good luck with the measurement!');
      setMsg(msg, '');
      await loadNodes();
    } else {
      setMsg(msg, `Run not started: ${await extractDetail(res)}`, 'err');
    }
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  }
}

/** Loss aversion: stopping a sweep early is framed as a concrete loss —
 * which SF stages are still missing — before it happens. */
async function stopSelectedRun() {
  const msg = document.getElementById('selected-msg');
  if (_selectedNodeId == null) return;
  const node = _nodesById[_selectedNodeId];
  const run = node && node.active_run;

  if (run && run.sf_schedule && run.sf_schedule.length) {
    const idx = run.segment_index ?? 0;
    const missing = run.sf_schedule.slice(idx + 1).map(s => `SF${s.sf}`);
    const statusText = sweepStatusText(run);
    const warnLine = missing.length
      ? `Stopping now will leave the <strong>${esc(missing.join('/'))}</strong> data missing.`
      : 'The last stage is almost complete.';
    const ok = await confirmModal({
      icon: '⚠️',
      title: 'Really end the measurement?',
      message: `<p>${esc(statusText)}</p><p>${warnLine} Really end it?</p>`,
      okLabel: 'End measurement',
      cancelLabel: 'Keep running',
    });
    if (!ok) return;
  }

  try {
    await apiJSON('/api/run/stop', {
      method: 'POST',
      body: JSON.stringify({ device_node_id: _selectedNodeId }),
    });
    toast('Run stopped.');
    setMsg(msg, '');
    await loadNodes();
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  }
}

// ---------------------------------------------------------------------------
// Place / Relocate / Move gateway — Bottom Sheet
// Smart defaults (principle 1) + outcome-stating submit labels (principle 4)
// ---------------------------------------------------------------------------

/** "Place / Relocate" button — the confirm gate sits BEFORE the data-entry
 * sheet: a running measurement is a real loss if relocated, so confirm
 * first; a never-run/no-run device has nothing to lose, so it's just a
 * placement — open the sheet directly. */
async function onPlaceOrRelocateClick() {
  const node = _nodesById[_selectedNodeId];
  if (!node) return;
  const run = node.active_run;

  if (run && run.status === 'running') {
    const ok = await confirmModal({
      icon: '⚠️',
      title: 'Stop the running measurement?',
      message: `<p>${esc(sweepStatusText(run))}</p><p>Relocating will stop it and start a new protocol.</p>`,
      okLabel: 'Stop & relocate',
      cancelLabel: 'Cancel',
    });
    if (!ok) return;
  }
  openPlaceSheet('device');
}

/** "Move gateway" button — same confirm-before-sheet ordering as
 * onPlaceOrRelocateClick above: check for running measurements FIRST (from
 * the already-loaded _nodes, no extra API call) and confirm the loss before
 * the data-entry sheet even opens, rather than opening the sheet and only
 * discovering the 409 conflict on submit. _gatewayForce then tells
 * submitSheet() which endpoint to call. */
async function onMoveGatewayClick() {
  const runningDevices = _nodes.filter(
    n => n.kind === 'device' && n.active_run && n.active_run.status === 'running'
  );

  if (runningDevices.length) {
    const listHtml = runningDevices.map(n => _lossRowHtml(n.name, sweepStatusText(n.active_run))).join('');
    const ok = await confirmModal({
      icon: '⚠️',
      title: _gatewayLossTitle(runningDevices.length),
      message: '',
      listHtml,
      okLabel: 'Move anyway — end measurements',
      cancelLabel: 'Cancel',
    });
    if (!ok) return;
    _gatewayForce = true;
  } else {
    _gatewayForce = false;
  }
  openPlaceSheet('gateway');
}

function openPlaceSheet(mode) {
  const node = _nodesById[_selectedNodeId];
  if (!node) return;

  _sheetMode = mode;
  _sheetPhotos = [];
  renderSheetPhotoThumbs();
  // _gatewayForce is set by onMoveGatewayClick() right before opening the
  // gateway sheet — nothing to do with the device path, reset it there so
  // it can never leak a stale 'true' into an unrelated device placement.
  if (mode !== 'gateway') _gatewayForce = false;

  // F-0008 — hide the map-position control until loadSheetMapPosition()
  // (async) resolves, so a re-open never briefly shows the previous node's
  // state; it also decides whether to show the control at all (hidden with
  // no current floorplan).
  _sheetMapPosition = null;
  const mapFieldEl = document.getElementById('sheet-map-field');
  if (mapFieldEl) mapFieldEl.style.display = 'none';
  loadSheetMapPosition();

  document.getElementById('sheet-conflict').style.display = 'none';
  document.getElementById('sheet-form').style.display = '';
  setMsg(document.getElementById('sheet-msg'), '');

  const p = node.placement;
  let floor = p ? (p.floor || '') : '';
  let room  = p ? (p.room || '') : '';
  // Smart default: a never-placed device has no placement to pre-fill from
  // (placements are never deleted, only superseded — so node.placement is
  // only null the very first time) — fall back to the gateway's floor.
  if (!floor && !room && mode === 'device') {
    const gw = _nodes.find(n => n.kind === 'gateway');
    if (gw && gw.placement) floor = gw.placement.floor || '';
  }
  document.getElementById('sheet-floor').value = floor;
  document.getElementById('sheet-room').value  = room;
  document.getElementById('sheet-desc').value  = p ? (p.description || '') : '';
  document.getElementById('sheet-note').value  = p ? (p.note || '') : '';

  const hasRun = !!(node.active_run && node.active_run.status === 'running');
  const submitBtn = document.getElementById('sheet-submit-btn');
  if (mode === 'gateway') {
    document.getElementById('sheet-title').textContent = 'Move gateway';
    submitBtn.textContent = 'Save location';
  } else if (hasRun) {
    document.getElementById('sheet-title').textContent = 'Relocate device';
    submitBtn.textContent = 'Relocate — close current protocol';
  } else {
    document.getElementById('sheet-title').textContent = 'Place device';
    submitBtn.textContent = 'Place & start measurement';
  }
  // Antenna is a per-device attribute (the gateway has none); photos apply
  // to both — a site photo of the gateway's mounting spot is just as
  // useful as one of a device's.
  document.getElementById('sheet-antenna-field').style.display = mode === 'gateway' ? 'none' : '';
  document.getElementById('sheet-photo-field').style.display   = '';

  // Smart default: last-used antenna (from the current placement), else 3 dBi.
  _sheetAntenna = (p && p.antenna) || '3dbi';
  applySheetAntennaUI();

  openSheetOverlay();
}

function selectSheetAntenna(type) {
  _sheetAntenna = type;
  applySheetAntennaUI();
}

function applySheetAntennaUI() {
  document.getElementById('sheet-ant-3dbi').classList.toggle('active', _sheetAntenna === '3dbi');
  document.getElementById('sheet-ant-12dbi').classList.toggle('active', _sheetAntenna === '12dbi');
}

function openSheetOverlay() {
  document.getElementById('place-ov').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeSheet() {
  document.getElementById('place-ov').classList.remove('open');
  document.body.style.overflow = '';
  _gatewayForce = false;
  _sheetMapPosition = null;
}

function closeSheetBackdrop(e) {
  if (e.target === document.getElementById('place-ov')) closeSheet();
}

// --- Photo capture (up to 3) — two entry points feed the same queue:
// "Upload photo" (plain file/gallery picker, multi-select) and
// "Take Picture" (capture="environment" opens the live camera on a phone,
// one shot per tap). ---

function onSheetPhotoSelected(e) {
  const files = Array.from(e.target.files || []);
  e.target.value = ''; // allow re-selecting the same file again
  for (const file of files) {
    if (_sheetPhotos.length >= 3) break;
    _sheetPhotos.push(file);
  }
  renderSheetPhotoThumbs();
}

function removeSheetPhoto(idx) {
  _sheetPhotos.splice(idx, 1);
  renderSheetPhotoThumbs();
}

function renderSheetPhotoThumbs() {
  const wrap = document.getElementById('sheet-photo-thumbs');
  wrap.innerHTML = _sheetPhotos.map((f, i) => `
    <div class="pthumb">
      <img src="${URL.createObjectURL(f)}" alt="Photo ${i + 1}">
      <button type="button" class="pthumb-x" onclick="removeSheetPhoto(${i})">×</button>
    </div>
  `).join('');
  const atCap = _sheetPhotos.length >= 3;
  const btnRow = document.getElementById('sheet-photo-btn-row');
  if (btnRow) btnRow.style.display = atCap ? 'none' : '';
  const capHint = document.getElementById('sheet-photo-cap-hint');
  if (capHint) capHint.style.display = atCap ? '' : 'none';
}

// --- Position on floor plan (F-0008) — optional, alongside photos. A
// compact embedded floorplan preview; tap it to drop/move this node's
// marker (touch and mouse both fire a regular 'click'). Submitted as
// map_x/map_y with the placement/relocate/gateway-move call in
// submitSheet() — captured WITH the placement, not a live marker. ---

/** Fetch the current floorplan and decide whether to show the control at
 * all; when shown, pre-fill from the node's previous placement position —
 * but only if that position was captured against this SAME floorplan
 * image (an older position from a since-replaced map would be
 * meaningless overlaid on the new one). */
async function loadSheetMapPosition() {
  const fieldEl = document.getElementById('sheet-map-field');
  if (!fieldEl) return;
  try {
    const data = await apiJSON('/api/floorplan');
    _sheetFloorplan = data.floorplan;
  } catch (e) {
    _sheetFloorplan = null;
  }

  if (!_sheetFloorplan) {
    fieldEl.style.display = 'none';
    return;
  }
  fieldEl.style.display = '';

  const node = _nodesById[_selectedNodeId];
  const p = node ? node.placement : null;
  _sheetMapPosition = (p && p.map_x != null && p.map_y != null && p.floorplan_id === _sheetFloorplan.id)
    ? { x: p.map_x, y: p.map_y }
    : null;
  renderSheetMap();
}

function renderSheetMap() {
  const img = document.getElementById('sheet-map-image');
  if (img && _sheetFloorplan) img.src = _sheetFloorplan.image_url;

  const markerEl = document.getElementById('sheet-map-marker');
  if (!markerEl) return;
  markerEl.classList.toggle('gateway', _sheetMode === 'gateway');
  if (_sheetMapPosition) {
    markerEl.style.display = '';
    markerEl.style.left = `${(_sheetMapPosition.x * 100).toFixed(2)}%`;
    markerEl.style.top = `${(_sheetMapPosition.y * 100).toFixed(2)}%`;
  } else {
    markerEl.style.display = 'none';
  }
}

function onSheetMapTap(e) {
  const stage = document.getElementById('sheet-map-stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  _sheetMapPosition = { x, y };
  renderSheetMap();
}

function clearSheetMapPosition() {
  _sheetMapPosition = null;
  renderSheetMap();
}

// --- Submit ---

async function submitSheet() {
  const msg = document.getElementById('sheet-msg');
  const floor       = document.getElementById('sheet-floor').value.trim();
  const room        = document.getElementById('sheet-room').value.trim();
  const description = document.getElementById('sheet-desc').value.trim();
  const note        = document.getElementById('sheet-note').value.trim();
  // F-0008 — optional map position, merged into whichever request body
  // below; {} (no keys added) when the control is hidden/untouched.
  const mapPos = _sheetMapPosition ? { map_x: _sheetMapPosition.x, map_y: _sheetMapPosition.y } : {};

  const btn = document.getElementById('sheet-submit-btn');
  btn.disabled = true;
  setMsg(msg, 'Saving…');

  try {
    if (_sheetMode === 'gateway') {
      // onMoveGatewayClick() already ran the loss-framed confirm and set
      // _gatewayForce before this sheet even opened — call the matching
      // endpoint directly instead of trying the plain move first.
      const endpoint = _gatewayForce ? '/api/gateway/move/force' : '/api/gateway/move';
      const res = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify(Object.assign({ floor, room, description, note }, mapPos)),
      });
      if (res.ok) {
        const result = await res.json();
        for (const file of _sheetPhotos) {
          try {
            await uploadPhoto(result.placement_id, file);
          } catch (e) {
            toast(`Photo upload failed: ${e.message}`);
          }
        }
        toast(_gatewayForce ? 'All runs acknowledged, gateway moved.' : 'Gateway moved.');
        closeSheet();
        await loadNodes();
      } else if (res.status === 409 && !_gatewayForce) {
        // Defensive fallback: a run started between the pre-flight check
        // and this submit — fall back to the existing in-sheet conflict
        // handling (forceGatewayMove() re-POSTs with /force on confirm).
        const body = await res.json();
        const openRuns = (body.detail && body.detail.open_runs) || [];
        showGatewayConflict(openRuns);
      } else {
        setMsg(msg, `Error: ${await extractDetail(res)}`, 'err');
      }
    } else {
      const node = _nodesById[_selectedNodeId];
      if (!node) { setMsg(msg, 'No device selected.', 'err'); return; }

      const hasRun = !!node.active_run;
      let placementId;
      if (hasRun) {
        const result = await apiJSON('/api/relocate', {
          method: 'POST',
          body: JSON.stringify(Object.assign(
            { device_node_id: node.id, floor, room, description, note, antenna: _sheetAntenna },
            mapPos,
          )),
        });
        placementId = result.placement_id;
      } else {
        const result = await apiJSON('/api/placement', {
          method: 'POST',
          body: JSON.stringify(Object.assign(
            { node_id: node.id, floor, room, description, note, antenna: _sheetAntenna },
            mapPos,
          )),
        });
        placementId = result.placement_id;
      }

      for (const file of _sheetPhotos) {
        try {
          await uploadPhoto(placementId, file);
        } catch (e) {
          toast(`Photo upload failed: ${e.message}`);
        }
      }

      if (hasRun) {
        // /api/relocate already closed the old run and opened a new one.
        toast('Relocated — new protocol started.');
      } else {
        // The sheet button promises "… & start measurement" — actually start it,
        // so the operator never needs a second tap.
        const total = 24 * 3600, per = Math.floor(total / 3);
        try {
          await apiJSON('/api/run/start', {
            method: 'POST',
            body: JSON.stringify({
              device_node_id: node.id,
              duration_seconds: total,
              sf_schedule: [
                { sf: 7, seconds: per },
                { sf: 9, seconds: per },
                { sf: 12, seconds: total - 2 * per },
              ],
              interval_minutes: 5,
            }),
          });
          toast('Placed — measurement started (24 h sweep).');
        } catch (e) {
          // Most likely: gateway not placed yet (run/start → 409).
          toast('Placed, but measurement NOT started — place the gateway first.');
        }
      }
      closeSheet();
      await loadNodes();
    }
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
  }
}

/** Loss aversion — defensive-fallback path only: a plain /api/gateway/move
 * still 409ed (a run started between the pre-flight check in
 * onMoveGatewayClick and this submit), so fall back to the same in-sheet
 * conflict box as before, using the 409 body's open_runs (device-level
 * detail comes from the last loadNodes() cache, same as onMoveGatewayClick;
 * the 409 body itself doesn't carry sweep detail). */
function showGatewayConflict(openRuns) {
  document.getElementById('sheet-form').style.display = 'none';
  const box = document.getElementById('sheet-conflict');
  box.style.display = '';

  document.getElementById('sheet-conflict-title').textContent = _gatewayLossTitle(openRuns.length);

  const list = document.getElementById('sheet-conflict-list');
  list.innerHTML = openRuns.length
    ? openRuns.map(r => {
        const liveRun = (_nodesById[r.device_node_id] && _nodesById[r.device_node_id].active_run) || null;
        const detail = liveRun ? sweepStatusText(liveRun) : `${r.packets} packets · since ${fmtTime(r.started_at)}`;
        return _lossRowHtml(r.name, detail);
      }).join('')
    : '<div class="hint">No details available.</div>';
}

async function forceGatewayMove() {
  const floor       = document.getElementById('sheet-floor').value.trim();
  const room        = document.getElementById('sheet-room').value.trim();
  const description = document.getElementById('sheet-desc').value.trim();
  const note        = document.getElementById('sheet-note').value.trim();
  try {
    const result = await apiJSON('/api/gateway/move/force', {
      method: 'POST',
      body: JSON.stringify({ floor, room, description, note }),
    });
    for (const file of _sheetPhotos) {
      try {
        await uploadPhoto(result.placement_id, file);
      } catch (e) {
        toast(`Photo upload failed: ${e.message}`);
      }
    }
    toast('All runs acknowledged, gateway moved.');
    closeSheet();
    await loadNodes();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// History (run history)
// ---------------------------------------------------------------------------

function onHistoryToggle(details) {
  if (details.open) loadHistory();
}

async function loadHistory() {
  const body = document.getElementById('history-body');
  if (!body || _selectedNodeId == null) return;
  body.innerHTML = '<p class="hint">Loading…</p>';
  try {
    const data = await apiJSON(`/api/runs?node_id=${_selectedNodeId}`);
    renderHistory(data.runs || []);
  } catch (e) {
    body.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

function renderHistory(runs) {
  const body = document.getElementById('history-body');
  // The active run's chart already lives at #sel-chart (always visible) —
  // History only lists past/completed runs to avoid showing it twice.
  const pastRuns = runs.filter(r => r.status !== 'running');
  if (!pastRuns.length) { body.innerHTML = '<p class="hint">No completed runs yet.</p>'; return; }
  body.innerHTML = `
    <div style="overflow-x:auto">
      <table class="dtbl">
        <thead><tr><th>Location</th><th>Status</th><th>Packets</th><th>Start</th><th>CSV</th></tr></thead>
        <tbody>
          ${pastRuns.map(r => `
            <tr>
              <td>${esc(r.floor || '—')} · ${esc(r.room || '—')}</td>
              <td class="hist-${esc(r.status)}">${histStatusLabel(r.status)}</td>
              <td>${r.packets}</td>
              <td>${fmtTime(r.started_at)}</td>
              <td><a class="btn btn-g" href="/api/run/${r.id}/csv" target="_blank">↓</a></td>
            </tr>
            <tr class="hist-chart-row">
              <td colspan="5"><div class="hist-chart" id="hist-chart-${r.id}"><p class="hint">Loading…</p></div></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>`;
  // Charts are always expanded now — fetch each run's series right away.
  for (const r of pastRuns) loadRunChart(r.id);
}

function histStatusLabel(s) {
  return { running: 'Running', done: 'Done', aborted: 'Aborted' }[s] || s;
}

// ---------------------------------------------------------------------------
// History — per-run RSSI/SNR/SF line chart (hand-rolled inline SVG, no
// chart library / CDN). SF-stage colors mirror style.css's --sfN-color
// tokens as literal hex (inline SVG stroke/fill attributes don't reliably
// resolve CSS custom properties on every mobile browser).
// ---------------------------------------------------------------------------

const RUN_CHART_SF_COLORS = {
  7:  '#22d3ee', // mirrors style.css --sf7-color
  9:  '#fb923c', // mirrors style.css --sf9-color
  12: '#6366f1', // mirrors style.css --sf12-color
};
const RUN_CHART_DEFAULT_COLOR = '#8593a6'; // mirrors style.css --adr-color / --muted

/** Charts in History are always expanded (no click-to-reveal) —
 * fetch + render straight into the container renderHistory() already laid
 * out for this run. */
async function loadRunChart(runId) {
  const container = document.getElementById(`hist-chart-${runId}`);
  if (!container) return;
  try {
    const data = await apiJSON(`/api/run/${runId}/series`);
    container.innerHTML = buildRunChartHtml(data);
  } catch (e) {
    container.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

let _selChartDebounce = null;

/** Debounced re-fetch of the selected-device chart AND PDR-per-SF block —
 * called on every SSE 'uplink' event for that device, so a burst of near-
 * simultaneous events (e.g. several devices reporting close together)
 * collapses into a single pair of requests instead of one per event. */
function scheduleSelectedRunRefresh() {
  if (_selChartDebounce) clearTimeout(_selChartDebounce);
  _selChartDebounce = setTimeout(() => {
    _selChartDebounce = null;
    loadSelectedChart();
    loadSelectedPdrStats();
  }, 1500);
}

/** Always-visible RSSI/SNR chart in the selected-device panel — the
 * device's active run, falling back to its most recent run, falling back
 * to the "no packets yet" empty state when it has never run at all.
 * Called directly (not debounced) from renderSelectedNode() so switching
 * devices feels instant; SSE-driven refreshes go through the debounced
 * scheduleSelectedRunRefresh() above. */
async function loadSelectedChart() {
  const wrap = document.getElementById('sel-chart-wrap');
  const container = document.getElementById('sel-chart');
  if (!wrap || !container) return;

  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') { wrap.style.display = 'none'; return; }
  wrap.style.display = '';

  const run = node.active_run || node.last_run;
  if (!run) {
    container.innerHTML = '<p class="hint">No packets in this run yet.</p>';
    return;
  }

  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/run/${run.id}/series`);
    if (_selectedNodeId !== nodeId) return; // selection changed while awaiting
    container.innerHTML = buildRunChartHtml(data);
  } catch (e) {
    if (_selectedNodeId !== nodeId) return;
    container.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

// ---------------------------------------------------------------------------
// PDR per SF — HEADLINE: delivery reliability per SF is the coverage metric
// that actually matters (RSSI barely changes with SF, PDR does). Uplink PDR
// from the run's CSV vs. its commanded interval; Downlink PDR from confirmed
// downlink ACKs (GET /api/run/{id}/stats). Same active/last-run resolution
// and staleness guard as loadSelectedChart() above.
// ---------------------------------------------------------------------------

async function loadSelectedPdrStats() {
  const block = document.getElementById('pdr-sf-block');
  if (!block) return;

  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') { block.style.display = 'none'; return; }

  const run = node.active_run || node.last_run;
  if (!run) { block.style.display = 'none'; return; }
  block.style.display = '';

  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/run/${run.id}/stats`);
    if (_selectedNodeId !== nodeId) return; // selection changed while awaiting
    renderPdrSfBlock(data);
  } catch (e) {
    if (_selectedNodeId !== nodeId) return;
    const grid = document.getElementById('pdr-sf-grid');
    if (grid) grid.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

/** Renders into #pdr-sf-grid/#pdr-sf-overall/#pdr-sf-hint by default (the
 * Selected-device panel); pass *ids* ({grid,overall,hint}) to target a
 * different set of elements — the History detail view (F-0007) reuses this
 * same builder for its own #hist-pdr-sf-* elements. */
function renderPdrSfBlock(data, ids = {}) {
  const grid = document.getElementById(ids.grid || 'pdr-sf-grid');
  const overallEl = document.getElementById(ids.overall || 'pdr-sf-overall');
  const hintEl = document.getElementById(ids.hint || 'pdr-sf-hint');
  if (!grid) return;

  if (!data.sf_stats || !data.sf_stats.length) {
    grid.innerHTML = '<p class="hint">No SF sweep in this run — no SF comparison available.</p>';
    if (overallEl) overallEl.textContent = '';
    if (hintEl) hintEl.textContent = '';
    return;
  }

  grid.innerHTML = data.sf_stats.map(pdrSfCellHtml).join('');

  const o = data.overall;
  if (overallEl) {
    overallEl.textContent = o.expected ? `Overall ${Math.round(o.pdr * 100)} %` : '';
  }
  if (hintEl) {
    hintEl.textContent = data.downlink_test
      ? ''
      : 'Downlink test was disabled for this run — no downlink PDR.';
  }
}

/** One SF's card: Uplink PDR (received/expected) and Downlink PDR
 * (ACK rate), both colored via the shared pdrClass tiers; Avg RSSI/Avg SNR
 * as small secondary context. "—" (not 0 %) while a segment hasn't started
 * yet or no downlink test has fired for it. */
function pdrSfCellHtml(s) {
  const upKnown = s.expected > 0;
  const upText = upKnown
    ? `${Math.round(s.pdr * 100)} % <small>(${s.received}/${s.expected})</small>`
    : '—';
  const upCls = upKnown ? pdrClass(s.pdr) : '';

  const dlKnown = s.dl_sent > 0;
  const dlText = dlKnown
    ? `${Math.round(s.dl_pdr * 100)} % <small>(${s.dl_acked}/${s.dl_sent})</small>`
    : '—';
  const dlCls = dlKnown ? pdrClass(s.dl_pdr) : '';

  return `
    <div class="pdr-sf-cell">
      <div class="pdr-sf-sf">SF${s.sf}</div>
      <div class="pdr-sf-row">
        <span class="pdr-sf-lbl">Uplink</span>
        <span class="pdr-sf-val ${upCls}">${upText}</span>
      </div>
      <div class="pdr-sf-row">
        <span class="pdr-sf-lbl">Downlink</span>
        <span class="pdr-sf-val ${dlCls}">${dlText}</span>
      </div>
      <div class="pdr-sf-sub">
        <span class="${rssiClass(s.rssi_avg)}">Avg&nbsp;${fmtNum(s.rssi_avg)}&nbsp;dBm</span>
        · <span class="${snrClass(s.snr_avg)}">Avg&nbsp;${fmtNum(s.snr_avg)}&nbsp;dB</span>
      </div>
    </div>`;
}

/** Build the inline-SVG chart + legend markup for one run's series response
 * (GET /api/run/{id}/series). Pure w.r.t. the DOM — returns an HTML string. */
function buildRunChartHtml(data) {
  const points = data.points || [];
  if (!points.length) {
    return '<p class="hint">No packets in this run yet.</p>';
  }

  const W = 600, H = 200;
  const padL = 38, padR = 8, padT = 10, padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxT = Math.max(data.planned_seconds || 0, points[points.length - 1].t || 0, 1);
  const xOf = t => padL + Math.min(1, Math.max(0, t / maxT)) * plotW;

  // Y axis (RSSI): auto-scaled to the data, clamped to a sane dBm window.
  const rssiVals = points.map(p => p.rssi).filter(v => v != null);
  let yMin = rssiVals.length ? Math.min(...rssiVals) : -110;
  let yMax = rssiVals.length ? Math.max(...rssiVals) : -60;
  const yPad = Math.max(3, (yMax - yMin) * 0.15);
  yMin = Math.max(-130, yMin - yPad);
  yMax = Math.min(-30, yMax + yPad);
  if (yMax - yMin < 10) { const mid = (yMax + yMin) / 2; yMin = mid - 5; yMax = mid + 5; }
  const yOf = rssi => padT + (1 - (rssi - yMin) / (yMax - yMin)) * plotH;

  // SNR: own (normalized) scale — no numeric axis, just a muted trend line.
  const snrVals = points.map(p => p.snr).filter(v => v != null);
  const snrMin = snrVals.length ? Math.min(...snrVals) : -20;
  const snrMax = snrVals.length ? Math.max(...snrVals) : 10;
  const snrRange = Math.max(1, snrMax - snrMin);
  const yOfSnr = snr => padT + (1 - (snr - snrMin) / snrRange) * plotH;

  // Gridlines + Y-axis labels (RSSI, dBm)
  const yTicks = 4;
  let gridSvg = '', yLabelsSvg = '';
  for (let i = 0; i <= yTicks; i++) {
    const val = yMin + (i / yTicks) * (yMax - yMin);
    const y = yOf(val);
    gridSvg += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" class="rc-grid"/>`;
    yLabelsSvg += `<text x="${padL - 5}" y="${(y + 3).toFixed(1)}" class="rc-axis-label" text-anchor="end">${Math.round(val)}</text>`;
  }

  // X-axis labels (hours since run start)
  const xTicks = 4;
  let xLabelsSvg = '';
  for (let i = 0; i <= xTicks; i++) {
    const tSec = (i / xTicks) * maxT;
    xLabelsSvg += `<text x="${xOf(tSec).toFixed(1)}" y="${H - padB + 14}" class="rc-axis-label" text-anchor="middle">${(tSec / 3600).toFixed(1)} h</text>`;
  }

  // RSSI — connected segments colored by the SF stage at the segment start.
  let rssiSvg = '';
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    if (a.rssi == null || b.rssi == null) continue;
    const color = RUN_CHART_SF_COLORS[a.sf] || RUN_CHART_DEFAULT_COLOR;
    rssiSvg += `<line x1="${xOf(a.t).toFixed(1)}" y1="${yOf(a.rssi).toFixed(1)}" x2="${xOf(b.t).toFixed(1)}" y2="${yOf(b.rssi).toFixed(1)}" stroke="${color}" class="rc-line-rssi"/>`;
  }
  if (points.length === 1 && points[0].rssi != null) {
    const p = points[0];
    rssiSvg += `<circle cx="${xOf(p.t).toFixed(1)}" cy="${yOf(p.rssi).toFixed(1)}" r="3" fill="${RUN_CHART_SF_COLORS[p.sf] || RUN_CHART_DEFAULT_COLOR}"/>`;
  }

  // SNR — single thin muted line, its own normalized scale.
  const snrPts = points.filter(p => p.snr != null).map(p => `${xOf(p.t).toFixed(1)},${yOfSnr(p.snr).toFixed(1)}`);
  const snrSvg = snrPts.length > 1 ? `<polyline points="${snrPts.join(' ')}" class="rc-line-snr"/>` : '';

  const svg = `
    <svg viewBox="0 0 ${W} ${H}" class="rc-svg" preserveAspectRatio="xMidYMid meet" role="img" aria-label="RSSI and SNR over time">
      <g>${gridSvg}</g>
      ${snrSvg}
      <g>${rssiSvg}</g>
      <g>${yLabelsSvg}</g>
      <g>${xLabelsSvg}</g>
    </svg>`;

  const legend = `
    <div class="rc-legend">
      <span class="lgrow"><span class="lgdot" style="background:${RUN_CHART_SF_COLORS[7]}"></span>SF7</span>
      <span class="lgrow"><span class="lgdot" style="background:${RUN_CHART_SF_COLORS[9]}"></span>SF9</span>
      <span class="lgrow"><span class="lgdot" style="background:${RUN_CHART_SF_COLORS[12]}"></span>SF12</span>
      <span class="lgrow"><span class="rc-legend-swatch rssi"></span>RSSI</span>
      <span class="lgrow"><span class="rc-legend-swatch snr"></span>SNR</span>
    </div>`;

  return svg + legend;
}

// ---------------------------------------------------------------------------
// F-0007 Measurement History / Analysis view (Phase 1) — top-level Live |
// History switch (header), a browsable/filterable-by-device list of every
// run (GET /api/runs, no node_id), and a left(device)/right(gateway) run
// detail (GET /api/run/{id}/detail + the existing /stats, /series, /csv).
// A read/browse view — reuses buildRunChartHtml, renderPdrSfBlock,
// placeInfoHtml, photoThumbsHtml, histStatusLabel, pdrClass unchanged.
// ---------------------------------------------------------------------------

let _currentView = 'live';

function switchView(view) {
  if (view === _currentView) return;
  _currentView = view;
  const liveBtn = document.getElementById('vsw-live');
  const histBtn = document.getElementById('vsw-history');
  const mapBtn = document.getElementById('vsw-map');
  if (liveBtn) liveBtn.classList.toggle('active', view === 'live');
  if (histBtn) histBtn.classList.toggle('active', view === 'history');
  if (mapBtn) mapBtn.classList.toggle('active', view === 'map');
  const mainEl = document.getElementById('main');
  const histEl = document.getElementById('history-view');
  const mapEl = document.getElementById('map-view');
  if (mainEl) mainEl.style.display = view === 'live' ? '' : 'none';
  if (histEl) histEl.style.display = view === 'history' ? '' : 'none';
  if (mapEl) mapEl.style.display = view === 'map' ? '' : 'none';
  if (view === 'history') {
    closeHistoryDetail(); // always land on the list, never a stale detail
    loadHistoryList();
  } else if (view === 'map') {
    loadMapView();
  }
}

let _historyRuns = [];

async function loadHistoryList() {
  const body = document.getElementById('history-list-body');
  if (!body) return;
  body.innerHTML = '<p class="hint">Loading…</p>';
  try {
    const data = await apiJSON('/api/runs');
    _historyRuns = data.runs || [];
    populateHistoryDeviceFilter();
    renderHistoryList();
  } catch (e) {
    body.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

/** Device options built from the runs themselves — no extra request. Keeps
 * the previous selection across a reload when that device still has runs. */
function populateHistoryDeviceFilter() {
  const sel = document.getElementById('hist-device-filter');
  if (!sel) return;
  const prev = sel.value;
  const seen = new Map(); // eui -> name
  for (const r of _historyRuns) {
    if (r.device && r.device.eui && !seen.has(r.device.eui)) seen.set(r.device.eui, r.device.name);
  }
  const devices = Array.from(seen.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  sel.innerHTML = '<option value="">All devices</option>' +
    devices.map(([eui, name]) => `<option value="${esc(eui)}">${esc(name)}</option>`).join('');
  if (devices.some(([eui]) => eui === prev)) sel.value = prev;
}

function renderHistoryList() {
  const body = document.getElementById('history-list-body');
  if (!body) return;
  const filterSel = document.getElementById('hist-device-filter');
  const filterEui = filterSel ? filterSel.value : '';
  const runs = filterEui ? _historyRuns.filter(r => r.device && r.device.eui === filterEui) : _historyRuns;

  if (!runs.length) {
    body.innerHTML = _historyRuns.length
      ? '<p class="hint">No measurements for this device yet.</p>'
      : '<p class="hint">No measurements recorded yet — place a device and start a run.</p>';
    return;
  }
  body.innerHTML = runs.map(historyRowHtml).join('');
}

/** One row: device · location · date/time · status · packets · PDR
 * summary. Tap -> openHistoryDetail(). */
function historyRowHtml(r) {
  const o = r.overall || {};
  const pdrKnown = o.expected != null && o.expected > 0;
  const pdrText = pdrKnown ? `${Math.round(o.pdr * 100)}% PDR` : '—';
  const pdrCls = pdrKnown ? pdrClass(o.pdr) : '';
  const deviceName = r.device ? r.device.name : '—';
  return `
    <div class="hist-row" onclick="openHistoryDetail(${r.run_id})">
      <div class="hist-row-main">
        <span class="hist-row-device">${esc(deviceName)}</span>
        <span class="hist-row-loc">${esc(r.floor || '—')} · ${esc(r.room || '—')}</span>
      </div>
      <div class="hist-row-meta">
        <span class="hist-row-time">${fmtTime(r.started_at)}</span>
        <span class="hist-badge hist-${esc(r.status)}">${histStatusLabel(r.status)}</span>
        <span>${r.packets} pkts</span>
        <span class="hist-row-pdr ${pdrCls}">${pdrText}</span>
      </div>
    </div>`;
}

function openHistoryDetail(runId) {
  const listView = document.getElementById('history-list-view');
  const detailView = document.getElementById('history-detail-view');
  if (listView) listView.style.display = 'none';
  if (detailView) detailView.style.display = '';
  loadHistoryDetail(runId);
}

function closeHistoryDetail() {
  const listView = document.getElementById('history-list-view');
  const detailView = document.getElementById('history-detail-view');
  if (detailView) detailView.style.display = 'none';
  if (listView) listView.style.display = '';
}

let _histDetailRunId = null; // guards against a stale response after a quick second tap

async function loadHistoryDetail(runId) {
  _histDetailRunId = runId;
  document.getElementById('hist-detail-title').textContent = 'Loading…';
  document.getElementById('hist-detail-device-place').innerHTML = '<div class="place-empty">Loading…</div>';
  document.getElementById('hist-detail-gateway-place').innerHTML = '<div class="place-empty">Loading…</div>';
  document.getElementById('hist-detail-device-photos').innerHTML = '';
  document.getElementById('hist-detail-gateway-photos').innerHTML = '';
  document.getElementById('hist-detail-device-map').innerHTML = '';
  document.getElementById('hist-detail-gateway-map').innerHTML = '';
  document.getElementById('hist-detail-chart').innerHTML = '<p class="hint">Loading…</p>';
  document.getElementById('hist-pdr-sf-grid').innerHTML = '';
  document.getElementById('hist-detail-meta').innerHTML = '';
  document.getElementById('hist-detail-csv-link').href = `/api/run/${runId}/csv`;

  try {
    const [detail, stats, series] = await Promise.all([
      apiJSON(`/api/run/${runId}/detail`),
      apiJSON(`/api/run/${runId}/stats`),
      apiJSON(`/api/run/${runId}/series`),
    ]);
    if (_histDetailRunId !== runId) return; // a newer tap superseded this fetch
    renderHistoryDetail(detail, stats, series);
  } catch (e) {
    if (_histDetailRunId !== runId) return;
    document.getElementById('hist-detail-chart').innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

/** F-0008 — small read-only floorplan thumbnail with one marker, showing
 * where a placement stood at the time (frozen map_x/map_y + the floorplan
 * it's relative to). '' when the placement has no map position — nothing
 * to show, the caller's container just stays empty. */
function mapThumbnailHtml(placement, isGateway) {
  if (!placement || !placement.floorplan || placement.map_x == null || placement.map_y == null) return '';
  return `
    <div class="map-thumb">
      <img src="${esc(placement.floorplan.image_url)}" alt="Floor plan" loading="lazy">
      <div class="map-marker-sm${isGateway ? ' gateway' : ''}"
           style="left:${(placement.map_x * 100).toFixed(2)}%;top:${(placement.map_y * 100).toFixed(2)}%"></div>
    </div>`;
}

function renderHistoryDetail(detail, stats, series) {
  const run = detail.run;
  const device = detail.device;
  const devicePlacement = detail.device_placement;
  const gatewayPlacement = detail.gateway_placement;

  document.getElementById('hist-detail-title').textContent =
    device ? `${device.name} — ${fmtTime(run.started_at)}` : `Run #${run.id}`;

  document.getElementById('hist-detail-device-place').innerHTML =
    placeInfoHtml(devicePlacement, { showAntenna: true });
  document.getElementById('hist-detail-device-photos').innerHTML =
    photoThumbsHtml(devicePlacement && devicePlacement.photo_ids);
  document.getElementById('hist-detail-device-map').innerHTML = mapThumbnailHtml(devicePlacement, false);

  document.getElementById('hist-detail-gateway-place').innerHTML = placeInfoHtml(gatewayPlacement);
  document.getElementById('hist-detail-gateway-photos').innerHTML =
    photoThumbsHtml(gatewayPlacement && gatewayPlacement.photo_ids);
  document.getElementById('hist-detail-gateway-map').innerHTML = mapThumbnailHtml(gatewayPlacement, true);

  renderPdrSfBlock(stats, { grid: 'hist-pdr-sf-grid', overall: 'hist-pdr-sf-overall', hint: 'hist-pdr-sf-hint' });

  document.getElementById('hist-detail-chart').innerHTML = buildRunChartHtml(series);

  document.getElementById('hist-detail-meta').innerHTML = `
    <div><strong>Status:</strong> ${histStatusLabel(run.status)}</div>
    <div><strong>Started:</strong> ${fmtTime(run.started_at)}</div>
    <div><strong>Ended:</strong> ${run.ended_at ? fmtTime(run.ended_at) : '—'}</div>
    <div><strong>Packets:</strong> ${run.packets}</div>`;
}

// ---------------------------------------------------------------------------
// F-0008 Map / Placement Editor — drag node markers onto an uploaded map
// image. Explicitly a placeholder: the first map is an isometric building
// view whose perspective distorts real coordinates, so x/y are fractions
// (0..1) of the image, not real-world positions — this is about the editor
// UX + persistence, not accurate positioning yet.
//
// The map position is a PLACEMENT attribute (frozen per measurement, same
// idea as floor/room/photos — see the Place/Relocate sheet's own "Position
// on floor plan" control above). Dragging a marker here edits the node's
// CURRENT ACTIVE placement in place (PUT /api/marker) — it never creates
// one, so the palette below only ever offers already-placed nodes.
// ---------------------------------------------------------------------------

let _mapFloorplan = null; // {id, name, image_url} | null
let _mapMarkers = [];     // [{node_id, name, kind, x, y}]

async function loadMapView() {
  try {
    const data = await apiJSON('/api/floorplan');
    _mapFloorplan = data.floorplan;
    _mapMarkers = data.markers || [];
    renderMapView();
  } catch (e) {
    toast(`Error loading map: ${e.message}`);
  }
}

function renderMapView() {
  const emptyEl = document.getElementById('map-empty');
  const withEl = document.getElementById('map-with-image');
  if (!emptyEl || !withEl) return;

  if (!_mapFloorplan) {
    emptyEl.style.display = '';
    withEl.style.display = 'none';
    return;
  }
  emptyEl.style.display = 'none';
  withEl.style.display = '';

  const img = document.getElementById('map-image');
  if (img) img.src = _mapFloorplan.image_url;
  const nameEl = document.getElementById('map-name');
  if (nameEl) nameEl.textContent = _mapFloorplan.name;

  renderMapMarkers();
  renderMapUnplacedList();
  initMapDrag();
}

/** Upload (empty state) or replace (with a map already) — same handler,
 * both file inputs feed it. */
async function onMapImageSelected(e) {
  const file = e.target.files && e.target.files[0];
  e.target.value = ''; // allow re-selecting the same file again
  if (!file) return;

  const msg = document.getElementById('map-upload-msg');
  if (msg) setMsg(msg, 'Uploading…');
  try {
    const fd = new FormData();
    fd.append('file', file, file.name || 'map.jpg');
    const res = await fetch('/api/floorplan', { method: 'POST', body: fd });
    if (res.status === 401) { toast('Not authenticated.'); return; }
    if (!res.ok) throw new Error(await extractDetail(res));
    if (msg) setMsg(msg, '');
    toast('Map uploaded.');
    await loadMapView();
  } catch (err) {
    toast(`Upload failed: ${err.message}`);
    if (msg) setMsg(msg, `Error: ${err.message}`, 'err');
  }
}

/** Gateway vs. device markers are visually distinct (dot color + icon);
 * both carry the node name label and a small remove ("x") action. Absolute
 * positions (left/top %) come straight from x/y (fractions of the image). */
function renderMapMarkers() {
  const el = document.getElementById('map-markers');
  if (!el) return;
  el.innerHTML = _mapMarkers.map(m => `
    <div class="map-marker map-marker-${esc(m.kind)}" data-node-id="${m.node_id}"
         style="left:${(m.x * 100).toFixed(2)}%;top:${(m.y * 100).toFixed(2)}%">
      <button type="button" class="map-marker-remove" onclick="removeMapMarker(${m.node_id})" title="Remove from map">×</button>
      <div class="map-marker-dot">${m.kind === 'gateway' ? '⌂' : '●'}</div>
      <div class="map-marker-label">${esc(m.name)}</div>
    </div>`).join('');
}

/** Nodes with an active placement but no map position yet — tap one to
 * place it at the map's center (a drag then fine-tunes the position). A
 * node with no active placement at all never appears here — placing it
 * (Place / Relocate) is a separate step, since dragging a marker only ever
 * edits an EXISTING placement, never creates one. */
function renderMapUnplacedList() {
  const el = document.getElementById('map-unplaced-list');
  if (!el) return;
  const placedIds = new Set(_mapMarkers.map(m => m.node_id));
  const unplaced = _nodes.filter(n => n.placement && !placedIds.has(n.id));
  if (!unplaced.length) {
    el.innerHTML = '<p class="hint">All placed nodes are already on the map.</p>';
    return;
  }
  el.innerHTML = unplaced.map(n => `
    <button type="button" class="map-unplaced-chip" onclick="addNodeToMap(${n.id})">
      <span class="map-unplaced-dot ${n.kind === 'gateway' ? 'gw' : ''}"></span>${esc(n.name)}
    </button>`).join('');
}

async function addNodeToMap(nodeId) {
  const ok = await saveMarkerPosition(nodeId, 0.5, 0.5); // "place at center"
  if (ok) {
    renderMapMarkers();
    renderMapUnplacedList();
  }
}

async function removeMapMarker(nodeId) {
  try {
    await apiJSON(`/api/marker/${nodeId}`, { method: 'DELETE' });
    _mapMarkers = _mapMarkers.filter(m => m.node_id !== nodeId);
    renderMapMarkers();
    renderMapUnplacedList();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

/** PUT /api/marker (sets the node's CURRENT ACTIVE placement's map
 * position — never creates a placement) + keep the in-memory _mapMarkers
 * cache in sync (adding an entry the first time a node is positioned).
 * Returns true on success so callers can decide whether to re-render or
 * snap back. */
async function saveMarkerPosition(nodeId, x, y) {
  try {
    await apiJSON('/api/marker', {
      method: 'PUT',
      body: JSON.stringify({ node_id: nodeId, x, y }),
    });
    const existing = _mapMarkers.find(m => m.node_id === nodeId);
    if (existing) {
      existing.x = x;
      existing.y = y;
    } else {
      const node = _nodesById[nodeId];
      _mapMarkers.push({ node_id: nodeId, name: node ? node.name : '', kind: node ? node.kind : 'device', x, y });
    }
    return true;
  } catch (e) {
    toast(`Could not save position: ${e.message}`);
    return false;
  }
}

/** Mouse + touch drag via the unified Pointer Events API, delegated on the
 * stable #map-markers container (so it keeps working across re-renders —
 * markers are replaced wholesale on every renderMapMarkers() call). Only
 * ever wired once (subsequent loadMapView() calls reuse it). touch-action:
 * none (CSS) on the stage/markers keeps a drag from also scrolling the
 * page on a phone. */
let _mapDragInitialized = false;

function initMapDrag() {
  if (_mapDragInitialized) return;
  const markersEl = document.getElementById('map-markers');
  const stageEl = document.getElementById('map-stage');
  if (!markersEl || !stageEl) return;
  _mapDragInitialized = true;

  let dragEl = null;
  let dragNodeId = null;
  let pendingXY = null;

  markersEl.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.map-marker-remove')) return; // let its own click fire, don't drag
    const marker = e.target.closest('.map-marker');
    if (!marker) return;
    dragEl = marker;
    dragNodeId = parseInt(marker.dataset.nodeId, 10);
    pendingXY = null;
    marker.classList.add('dragging');
    marker.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  markersEl.addEventListener('pointermove', (e) => {
    if (!dragEl) return;
    const rect = stageEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    dragEl.style.left = `${(x * 100).toFixed(2)}%`;
    dragEl.style.top = `${(y * 100).toFixed(2)}%`;
    pendingXY = { x, y };
  });

  function endDrag() {
    if (!dragEl) return;
    dragEl.classList.remove('dragging');
    const nodeId = dragNodeId;
    const xy = pendingXY;
    dragEl = null;
    dragNodeId = null;
    pendingXY = null;
    if (xy) {
      saveMarkerPosition(nodeId, xy.x, xy.y).then(ok => {
        if (!ok) renderMapMarkers(); // snap back to the last known-good position
      });
    }
  }

  markersEl.addEventListener('pointerup', endDrag);
  markersEl.addEventListener('pointercancel', endDrag);
}

// ---------------------------------------------------------------------------
// Overview — Node dashboard (device cards)
// ---------------------------------------------------------------------------

function renderNodeDashboard() {
  const grid = document.getElementById('node-grid');
  if (!_nodes.length) {
    grid.innerHTML = '<div class="hint" style="padding:20px 0;text-align:center">No devices found.</div>';
    return;
  }
  const gateways = _nodes.filter(n => n.kind === 'gateway');
  const devices  = _nodes.filter(n => n.kind === 'device');
  grid.innerHTML = gateways.map(gatewayCardHtml).join('') + devices.map(deviceCardHtml).join('');

  for (const n of devices) checkCelebration(n);

  const doneCount = devices.filter(n => n.last_run && n.last_run.status === 'done').length;
  const summaryEl = document.getElementById('overview-summary');
  if (summaryEl) {
    summaryEl.style.display = doneCount > 0 ? '' : 'none';
    summaryEl.textContent = doneCount > 0 ? `${doneCount} done` : '';
  }
}

function gatewayCardHtml(n) {
  const loc = n.placement
    ? `${esc(n.placement.floor || '—')} · ${esc(n.placement.room || '—')}`
    : 'not placed';
  return `
    <div class="node-card gw-card ${n.id === _selectedNodeId ? 'selected' : ''}" id="nc-${n.id}" onclick="selectNode(${n.id}, true)">
      <div class="nc-top">
        <span class="nc-name">${esc(n.name)}</span>
        <span class="nc-tag">Gateway</span>
      </div>
      <div class="nc-loc">${loc}</div>
      ${photoStripHtml(n.placement)}
    </div>`;
}

function deviceCardHtml(n) {
  const running = !!(n.active_run && n.active_run.status === 'running');
  const justDone = !running && n.last_run && n.last_run.status === 'done';
  const loc = n.placement
    ? `${esc(n.placement.floor || '—')} · ${esc(n.placement.room || '—')}`
    : 'not placed';
  const m = _devMetrics[n.eui] || {};
  const progressRun = n.active_run || n.last_run;

  const statusHtml = justDone
    ? `<span class="nc-done">done ✓</span>`
    : `<span class="nc-run ${running ? 'on' : ''}">${running ? '● Running' : 'no run'}</span>`;

  return `
    <div class="node-card ${running ? 'running' : ''} ${n.id === _selectedNodeId ? 'selected' : ''}" id="nc-${n.id}" onclick="selectNode(${n.id}, true)">
      <div class="nc-top">
        <span class="nc-name">${esc(n.name)}</span>
        ${statusHtml}
      </div>
      <div class="nc-loc">${loc}</div>
      ${running ? `<div class="nc-packets">${n.active_run.packets} packets</div>` : ''}
      <div class="nc-metrics">${nodeCardMetricsHtml(m)}</div>
      <div class="nc-meta" id="nc-meta-${n.id}">${esc(metaLineText(m))}</div>
      ${progressRun ? runProgressHtml(progressRun, { compact: true }) : ''}
      ${photoStripHtml(n.placement)}
    </div>`;
}

/** Endowment/IKEA: your own captured photos shown as a growing collection,
 * right on the overview card. */
function photoStripHtml(placement) {
  if (!placement || !placement.photo_ids || !placement.photo_ids.length) return '';
  return `<div class="photo-strip">${placement.photo_ids.slice(0, 3).map(id =>
    `<img src="/api/photo/${id}" alt="Photo" loading="lazy">`
  ).join('')}</div>`;
}

/** RSSI / SNR / SF only, per the Overview card spec (PDR stays in the
 * "Selected device" detail panel via selMetricsHtml). */
function nodeCardMetricsHtml(m) {
  return `
    <span class="${rssiClass(m.rssi)}">${fmtNum(m.rssi)}&nbsp;dBm</span>
    <span class="${snrClass(m.snr)}">${fmtNum(m.snr)}&nbsp;dB</span>
    <span>${m.sf != null ? 'SF' + m.sf : '—'}</span>
  `;
}

function updateNodeCardMetrics(eui) {
  const node = _nodes.find(n => n.eui === eui);
  if (!node) return;
  const card = document.getElementById(`nc-${node.id}`);
  if (!card) return;
  const m = _devMetrics[eui] || {};
  const metricsEl = card.querySelector('.nc-metrics');
  if (metricsEl) metricsEl.innerHTML = nodeCardMetricsHtml(m);
  card.classList.remove('flash');
  void card.offsetWidth; // reflow
  card.classList.add('flash');
}

// ---------------------------------------------------------------------------
// Color helpers (reused across selected panel + dashboard cards)
// ---------------------------------------------------------------------------

function rssiClass(v) {
  if (v == null) return '';
  if (v > -80)   return 'm-good';
  if (v > -110)  return 'm-ok';
  if (v > -120)  return 'm-warn';
  return 'm-bad';
}

function snrClass(v) {
  if (v == null) return '';
  if (v >= 0)    return 'm-good';
  if (v >= -10)  return 'm-ok';
  if (v >= -15)  return 'm-warn';
  return 'm-bad';
}

function pdrClass(v) {
  if (v == null) return '';
  if (v >= 0.99) return 'm-good';
  if (v >= 0.80) return 'm-ok';
  if (v >= 0.50) return 'm-warn';
  return 'm-bad';
}

// ---------------------------------------------------------------------------
// Device registration (ChirpStack device list, Vicki bulk)
// ---------------------------------------------------------------------------

async function registerDevice() {
  const name     = document.getElementById('dev-name').value.trim();
  const dev_eui  = document.getElementById('dev-eui').value.trim().toLowerCase();
  const app_key  = document.getElementById('dev-appkey').value.trim().toLowerCase();
  const join_eui = document.getElementById('dev-joineui').value.trim() || '0000000000000000';
  const msg      = document.getElementById('dev-msg');

  if (!name || !dev_eui || !app_key) {
    setMsg(msg, 'Name, DevEUI and AppKey are required.', 'err');
    return;
  }
  try {
    const data = await apiJSON('/api/devices', {
      method: 'POST',
      body: JSON.stringify({ name, dev_eui, app_key, join_eui }),
    });
    setMsg(msg, `Registered: ${data.dev_eui}`);
    toast('Device registered.');
    loadDevices();
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  }
}

async function loadDevices() {
  try {
    const data = await apiJSON('/api/devices');
    renderDeviceList(data.devices || []);
  } catch (e) {
    setMsg(document.getElementById('dev-msg'), `Error loading: ${e.message}`, 'err');
  }
}

function renderDeviceList(devices) {
  _currentDevices = devices;
  const tbody = document.getElementById('dev-list-body');
  if (!devices.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:12px 0">— no devices —</td></tr>';
    return;
  }
  tbody.innerHTML = devices.map(d => `
    <tr>
      <td class="mono">${esc(d.dev_eui)}</td>
      <td>${esc(d.name)}</td>
      <td>${esc(d.device_profile_name || '—')}</td>
      <td>${d.last_seen_at ? d.last_seen_at.replace('T', ' ').substring(0, 19) : '—'}</td>
    </tr>
  `).join('');
}

async function sendVickiKeepalive() {
  const msg = document.getElementById('vicki-msg');
  if (!_currentDevices.length) {
    setMsg(msg, 'No devices — load the device list first (above).', 'err');
    return;
  }
  let ok = 0, fail = 0, firstErr = null;
  for (const d of _currentDevices) {
    try {
      // 0x02 SetSendPeriod, 0x05 = 5 minutes
      // count:false — interval command doesn't count towards the DL-PDR denominator
      await apiJSON('/api/downlink', {
        method: 'POST',
        body: JSON.stringify({ dev_eui: d.dev_eui, f_port: 1, data_hex: '0205', count: false }),
      });
      ok++;
    } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  const txt = `Interval queued: ${ok} ok` + (fail ? `, ${fail} failed: ${firstErr}` : '') + '.';
  setMsg(msg, txt, fail ? 'err' : '');
  toast(`Vicki interval: ${ok} queued.`);
}

async function sendVickiLoopback() {
  const msg = document.getElementById('vicki-msg');
  if (!_currentDevices.length) {
    setMsg(msg, 'No devices — load the device list first (above).', 'err');
    return;
  }
  let ok = 0, fail = 0, firstErr = null;
  for (const d of _currentDevices) {
    try {
      // 0x04 = read HW/SW version (confirmed, counts towards DL-PDR; count:true)
      await apiJSON('/api/downlink', {
        method: 'POST',
        body: JSON.stringify({ dev_eui: d.dev_eui, f_port: 1, data_hex: '04', count: true }),
      });
      ok++;
    } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  const txt = `HW/SW version queued: ${ok} ok` + (fail ? `, ${fail} failed: ${firstErr}` : '') + '.';
  setMsg(msg, txt, fail ? 'err' : '');
  toast(`Vicki HW/SW version: ${ok} queued.`);
}

// ---------------------------------------------------------------------------
// RF Environment — full spectrum survey of the FOREIGN LoRaWAN traffic the
// gateway overhears (F-0006). Always-on, passive: no start/stop — the
// gateway hears every frame in range regardless of any toggle. Fetches
// GET /api/rf-environment (own/foreign totals, a channel×SF heatmap,
// networks, foreign devices, vendors from joins, band busyness), throttled
// re-fetch on SSE 'coex' events (see scheduleRfEnvironmentRefresh below).
// ---------------------------------------------------------------------------

const RF_HEATMAP_CHANNELS = [0, 1, 2, 3, 4, 5, 6, 7]; // the 8 EU868 LoRa channels
const RF_HEATMAP_SFS = [7, 8, 9, 10, 11, 12];

let _rfEnvLoading = false;
let _rfEnvPending = false;

/** Fetch + render the full survey. Coalesces overlapping calls (a pending
 * fetch already in flight just gets one more run queued after it, not a
 * pile of parallel requests). */
async function loadRfEnvironment() {
  if (_rfEnvLoading) { _rfEnvPending = true; return; }
  _rfEnvLoading = true;
  try {
    const data = await apiJSON('/api/rf-environment');
    renderRfEnvironment(data);
  } catch (e) {
    // Best-effort — leave the panel showing its last-known state rather
    // than blanking it on a transient error.
  } finally {
    _rfEnvLoading = false;
    if (_rfEnvPending) { _rfEnvPending = false; loadRfEnvironment(); }
  }
}

let _rfEnvDebounce = null;

/** Throttled re-fetch — SSE 'coex' events can arrive many times per second
 * during a burst of foreign traffic; collapse them into at most one
 * /api/rf-environment request every few seconds. */
function scheduleRfEnvironmentRefresh() {
  if (_rfEnvDebounce) return;
  _rfEnvDebounce = setTimeout(() => {
    _rfEnvDebounce = null;
    loadRfEnvironment();
  }, 3000);
}

function renderRfEnvironment(data) {
  const ownEl = document.getElementById('coex-own-count');
  const foreignEl = document.getElementById('coex-foreign-count');
  if (ownEl) ownEl.textContent = data.own_frames || 0;
  if (foreignEl) foreignEl.textContent = data.foreign_frames || 0;

  const heatmapEl = document.getElementById('rf-heatmap');
  if (heatmapEl) heatmapEl.innerHTML = buildRfHeatmapHtml(data.channel_sf_matrix || {});

  const timelineEl = document.getElementById('rf-timeline');
  if (timelineEl) timelineEl.innerHTML = buildRfTimelineSvg(data.timeline || []);

  const rateEl = document.getElementById('rf-frames-per-min');
  if (rateEl) rateEl.textContent = (data.frames_per_min || 0).toFixed(1);
  const sparkEl = document.getElementById('rf-sparkline');
  if (sparkEl) sparkEl.innerHTML = buildRfSparklineSvg(data.frames_per_min_sparkline || []);

  renderRfMtypeBreakdown(data.mtype_counts || {});
  renderRfNetworks(data.networks || {});
  renderRfDevices(data.foreign_devices || {});
  renderRfVendors(data.vendors || {});
  renderRfSfDistribution(data.sf_distribution || {});
  renderRfRssiDistribution(data.rssi_distribution || []);
  renderRfFrameLog(data.recent_frames || []);
}

/** Channel × SF grid, cells shaded by foreign-frame count (a single accent
 * color at varying opacity — flat, no gradient/glow) relative to the
 * loudest cell currently observed. */
function buildRfHeatmapHtml(matrix) {
  const counts = RF_HEATMAP_CHANNELS.flatMap(
    ch => RF_HEATMAP_SFS.map(sf => matrix[`ch${ch}_sf${sf}`] || 0)
  );
  const max = Math.max(1, ...counts);
  if (!counts.some(c => c > 0)) {
    return '<p class="hint">No foreign frames observed yet.</p>';
  }

  let html = '<div class="rf-heat-grid">';
  html += '<div class="rf-heat-hdr"></div>';
  for (const sf of RF_HEATMAP_SFS) html += `<div class="rf-heat-hdr">SF${sf}</div>`;
  for (const ch of RF_HEATMAP_CHANNELS) {
    html += `<div class="rf-heat-hdr rf-heat-rowhdr">CH${ch}</div>`;
    for (const sf of RF_HEATMAP_SFS) {
      const count = matrix[`ch${ch}_sf${sf}`] || 0;
      const alpha = count === 0 ? 0 : Math.max(0.15, count / max);
      html += `<div class="rf-heat-cell" style="background:rgba(34,211,238,${alpha.toFixed(2)})" title="CH${ch} / SF${sf}: ${count} foreign frame${count === 1 ? '' : 's'}">${count || ''}</div>`;
    }
  }
  html += '</div>';
  return html;
}

/** Small bar-chart sparkline (oldest -> newest, left to right) — a tiny,
 * self-contained inline SVG, no library. */
function buildRfSparklineSvg(sparkline) {
  if (!sparkline.length) return '';
  const W = 100, H = 24;
  const max = Math.max(1, ...sparkline);
  const barW = W / sparkline.length;
  return sparkline.map((v, i) => {
    const h = v > 0 ? Math.max(2, (v / max) * H) : 0.5;
    const x = i * barW;
    const y = H - h;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barW * 0.7).toFixed(1)}" height="${h.toFixed(1)}" class="rf-spark-bar"/>`;
  }).join('');
}

/** Foreign-frame traffic timeline — one bar per hour, oldest -> newest
 * (last 24 h, left to right); pairs with the heatmap (heatmap = where/
 * what-SF, timeline = when). Same tiny self-contained inline-SVG-bars
 * pattern as the busyness sparkline above, with a <title> tooltip per bar
 * since there's no room for per-bucket text labels at this size. */
function buildRfTimelineSvg(timeline) {
  if (!timeline || !timeline.length) return '';
  const W = 100, H = 32;
  const max = Math.max(1, ...timeline.map(b => b.count));
  const barW = W / timeline.length;
  return timeline.map((b, i) => {
    const h = b.count > 0 ? Math.max(2, (b.count / max) * H) : 0.5;
    const x = i * barW;
    const y = H - h;
    const tip = `${fmtTime(b.bucket)}: ${b.count} frame${b.count === 1 ? '' : 's'}`;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(barW * 0.7).toFixed(1)}" height="${h.toFixed(1)}" class="rf-timeline-bar"><title>${esc(tip)}</title></rect>`;
  }).join('');
}

const RF_MTYPE_LABELS = { join: 'Joins', data_up: 'Data up', data_down: 'Data down', other: 'Other' };

function renderRfMtypeBreakdown(counts) {
  const el = document.getElementById('rf-mtype-breakdown');
  if (!el) return;
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  if (!total) { el.innerHTML = '<p class="hint">No data yet.</p>'; return; }
  el.innerHTML = Object.entries(RF_MTYPE_LABELS)
    .map(([key, label]) => `<span class="rf-mtype-chip">${label}: ${counts[key] || 0}</span>`)
    .join('');
}

function renderRfNetworks(networks) {
  const el = document.getElementById('rf-networks');
  if (!el) return;
  const entries = Object.entries(networks);
  if (!entries.length) { el.innerHTML = '<p class="hint">No foreign devices observed yet.</p>'; return; }
  entries.sort((a, b) => b[1].frames - a[1].frames);
  const maxFrames = Math.max(1, ...entries.map(([, v]) => v.frames));
  el.innerHTML = entries.map(([label, v]) => `
    <div class="rf-net-row">
      <div class="rf-net-hdr">
        <span class="rf-net-label">${esc(label)}</span>
        <span class="rf-net-count">${v.devices} device${v.devices === 1 ? '' : 's'} · ${v.frames} frame${v.frames === 1 ? '' : 's'}</span>
      </div>
      <div class="rf-net-bar-track"><div class="rf-net-bar-fill" style="width:${Math.max(4, (v.frames / maxFrames) * 100).toFixed(0)}%"></div></div>
    </div>`).join('');
}

function renderRfDevices(devices) {
  const el = document.getElementById('rf-devices');
  const countEl = document.getElementById('rf-device-count');
  if (!el) return;
  const entries = Object.entries(devices);
  if (countEl) countEl.textContent = entries.length ? `(${entries.length})` : '';
  if (!entries.length) { el.innerHTML = '<p class="hint">No foreign devices observed yet.</p>'; return; }
  entries.sort((a, b) => new Date(b[1].last_seen || 0) - new Date(a[1].last_seen || 0));
  el.innerHTML = entries.map(([devAddr, d]) => `
    <div class="rf-dev-row">
      <span class="mono">${esc(devAddr)}</span>
      <span class="rf-dev-net">${esc(d.network || 'other')}</span>
      <span>${d.last_sf != null ? 'SF' + d.last_sf : '—'}</span>
      <span class="${rssiClass(d.last_rssi)}">${fmtNum(d.last_rssi)}&nbsp;dBm</span>
      <span class="hint">${ageFromUplinkAt(d.last_seen)}</span>
    </div>`).join('');
}

function renderRfVendors(vendors) {
  const el = document.getElementById('rf-vendors');
  if (!el) return;
  const entries = Object.entries(vendors);
  if (!entries.length) { el.innerHTML = '<p class="hint">No joins observed yet.</p>'; return; }
  entries.sort((a, b) => b[1].joins - a[1].joins);
  el.innerHTML = entries.map(([oui, v]) => `
    <div class="rf-vendor-row">
      <span>${esc(v.name)}</span>
      <span class="hint mono">${esc(oui)}</span>
      <span>${v.joins} join${v.joins === 1 ? '' : 's'}</span>
    </div>`).join('');
}

/** Small horizontal bar row shared by the SF and RSSI distributions —
 * label · thin bar (width relative to the loudest bucket) · count. */
function _rfDistRowsHtml(entries) {
  const max = Math.max(1, ...entries.map(([, c]) => c));
  return entries.map(([label, c]) => `
    <div class="rf-dist-row">
      <span class="rf-dist-label">${esc(label)}</span>
      <div class="rf-dist-bar-track"><div class="rf-dist-bar-fill" style="width:${c ? Math.max(4, (c / max) * 100).toFixed(0) : 0}%"></div></div>
      <span class="rf-dist-count">${c}</span>
    </div>`).join('');
}

function renderRfSfDistribution(sfDist) {
  const el = document.getElementById('rf-sf-dist');
  if (!el) return;
  const entries = Object.entries(sfDist).map(([sf, c]) => [`SF${sf}`, c]);
  const total = entries.reduce((a, [, c]) => a + c, 0);
  if (!total) { el.innerHTML = '<p class="hint">No data yet.</p>'; return; }
  el.innerHTML = _rfDistRowsHtml(entries);
}

function renderRfRssiDistribution(buckets) {
  const el = document.getElementById('rf-rssi-dist');
  if (!el) return;
  const total = buckets.reduce((a, b) => a + b.count, 0);
  if (!total) { el.innerHTML = '<p class="hint">No data yet.</p>'; return; }
  el.innerHTML = _rfDistRowsHtml(buckets.map(b => [b.label, b.count]));
}

/** "HH:MM:SS" from a stored ts (already UTC, same raw-substring approach as
 * fmtTime — no local-timezone conversion anywhere else in this app). */
function fmtHms(iso) {
  if (!iso) return '—';
  const t = String(iso).split('T')[1] || '';
  return t.substring(0, 8);
}

/** Compact live log — last ~20 foreign frames, newest first (recent_frames
 * is already ordered that way by the backend). A join-request has no
 * DevAddr, shown as "join" instead. */
function renderRfFrameLog(frames) {
  const el = document.getElementById('rf-frame-log');
  if (!el) return;
  if (!frames.length) { el.innerHTML = '<p class="hint">No foreign frames recorded yet.</p>'; return; }
  el.innerHTML = frames.map(f => `
    <div class="rf-log-row">
      <span class="rf-log-time">${fmtHms(f.ts)}</span>
      <span class="rf-log-addr mono">${f.dev_addr ? esc(f.dev_addr) : 'join'}</span>
      <span class="rf-log-net">${esc(f.network || (f.dev_addr ? 'other' : '—'))}</span>
      <span class="rf-log-sf">${f.sf != null ? 'SF' + f.sf : '—'}</span>
      <span class="rf-log-rssi ${rssiClass(f.rssi)}">${fmtNum(f.rssi)}&nbsp;dBm</span>
    </div>`).join('');
}

// ---------------------------------------------------------------------------
// SSE — live event stream
// ---------------------------------------------------------------------------

function initSSE() {
  const dot = document.getElementById('dot-sse');

  function connect() {
    const es = new EventSource('/api/events');

    es.onopen = () => { dot.classList.add('ok'); };

    es.onmessage = (e) => {
      try { handleEvent(JSON.parse(e.data)); } catch (_) {}
    };

    es.onerror = () => {
      dot.classList.remove('ok');
      es.close();
      setTimeout(connect, 4000);
    };
  }

  connect();
}

function handleEvent(ev) {
  switch (ev.type) {
    case 'uplink': {
      const eui  = ev.dev_eui;
      const prev = _devMetrics[eui] || {};
      _devMetrics[eui] = {
        rssi:            ev.rssi_dbm,
        snr:             ev.snr_db,
        sf:              ev.sf,
        f_cnt:           ev.f_cnt,
        pdr:             ev.pdr,
        downlinks_sent:  prev.downlinks_sent,
        acked:           prev.acked,
        dl_pdr:          prev.dl_pdr,
        lastUplinkAt:    ev.last_uplink_at,
        intervalSeconds: ev.interval_seconds,
      };
      updateNodeCardMetrics(eui);
      updateSelectedMetrics(eui);
      renderHero(); // a fresh packet can advance a run's live progress fraction
      const selNode = _nodesById[_selectedNodeId];
      if (selNode && selNode.kind === 'device' && selNode.eui === eui) {
        scheduleSelectedRunRefresh();
      }
      break;
    }
    case 'ack': {
      const eui = ev.dev_eui;
      if (_devMetrics[eui]) {
        _devMetrics[eui].acked  = ev.acked;
        _devMetrics[eui].dl_pdr = ev.downlink_pdr;
      }
      break;
    }
    case 'join':
      toast(`Join: ${ev.dev_eui} → DevAddr ${ev.dev_addr}`);
      break;
    case 'coex':
      scheduleRfEnvironmentRefresh();
      break;
    case 'nodes':
      loadNodes();
      break;
  }
}

// ---------------------------------------------------------------------------
// Run-progress ticker — recomputes the progress bars/labels from
// wall-clock time every ~30 s so they move smoothly between SSE 'nodes'
// events; loadNodes() (triggered by that event) snaps them back to server
// truth (segment_index/current_sf/done).
// ---------------------------------------------------------------------------

let _progressTimer = null;

function startProgressTicker() {
  if (_progressTimer) return;
  _progressTimer = setInterval(() => {
    renderHero(); // smooth ring/per-device movement from the live elapsed÷planned extrapolation
    renderNodeDashboard();
    renderSelectedNode();
    refreshDeviceStatus(); // periodic refresh — queue/last-downlink can change without an SSE 'nodes' event
    loadRfEnvironment(); // periodic safety-net refresh alongside the throttled SSE-driven one
  }, 30000);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

async function init() {
  initHeroRing();
  try {
    const state = await apiJSON('/api/state');
    applyInitialState(state);
  } catch (_) {}
  await loadNodes();
  initSSE();
  loadDevices();
  loadRfEnvironment();
  startProgressTicker();
  startSignalAgeTicker();
}

function applyInitialState(s) {
  for (const [eui, m] of Object.entries(s.devices || {})) {
    _devMetrics[eui] = {
      rssi:            m.rssi_dbm,
      snr:             m.snr_db,
      sf:              m.sf,
      f_cnt:           m.f_cnt,
      pdr:             null, // populated by the next uplink SSE event
      downlinks_sent:  m.downlinks_sent,
      acked:           m.acked,
      dl_pdr:          m.acked && m.downlinks_sent ? m.acked / m.downlinks_sent : null,
      lastUplinkAt:    m.last_uplink_at != null ? m.last_uplink_at : null,
      intervalSeconds: m.interval_seconds != null ? m.interval_seconds : null,
    };
  }

  // RF Environment (always-on) — seed the own/foreign totals instantly from
  // this lightweight snapshot; the richer survey (heatmap, networks,
  // devices, vendors) loads separately via loadRfEnvironment() in init().
  const ownEl = document.getElementById('coex-own-count');
  const foreignEl = document.getElementById('coex-foreign-count');
  if (ownEl) ownEl.textContent = s.coex_own_frames || 0;
  if (foreignEl) foreignEl.textContent = s.coex_foreign_frames || 0;
}

// ---------------------------------------------------------------------------
// Help overlay
// ---------------------------------------------------------------------------

function openHelp() {
  document.getElementById('help-ov').classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeHelp() {
  document.getElementById('help-ov').classList.remove('open');
  document.body.style.overflow = '';
}

function closeHelpBdrop(e) {
  if (e.target === document.getElementById('help-ov')) closeHelp();
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function setMsg(el, text, cls = '') {
  if (!el) return;
  el.textContent = text;
  el.className = 'msg' + (cls ? ' ' + cls : '');
}

function fmtNum(v) { return v != null ? Number(v).toFixed(1) : '—'; }

function fmtTime(iso) {
  if (!iso) return '—';
  return String(iso).replace('T', ' ').substring(0, 16);
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', init);
