/* app.js — Feldtest-Cockpit frontend (vanilla JS, kein Framework)
   F-0006 Feldmess-Workflow — device-centric, no GPS.
   Visual/UX layer applies 6 psychology principles (smart defaults,
   goal-gradient, reciprocity, endowment/IKEA, loss aversion, contrast/
   anchoring) on top of the unchanged backend contracts. */
'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const _devMetrics = {};   // { dev_eui: { rssi, snr, sf, f_cnt, pdr, acked, downlinks_sent, dl_pdr, lastUplinkAt, intervalSeconds } }
const _coexData   = {};   // { "ch<n>_sf<n>": { channel, sf, frames, caf, tl } }
let _coexOwn     = 0;      // running total of frames classified as ours (Funkumgebung, always-on)
let _coexForeign = 0;      // running total of frames classified as foreign networks
let _currentDevices = []; // last /api/devices (ChirpStack) result — used by Vicki bulk

let _nodes      = [];     // last /api/nodes result
let _nodesById  = {};
let _selectedNodeId = null;
let _prevDone   = {};     // { nodeId: bool } — tracks last_run.status==='done' to fire the celebration once

let _devConfigStatus = null; // { nodeId, last_uplink_at, interval_seconds, queued, last_downlink_at } — Geräte-Status (Trust & Sichtbarkeit), fetched only for the selected device

let _sheetMode    = null; // 'device' | 'gateway'
let _sheetAntenna = '3dbi';
let _sheetPhotos  = [];   // File[] queued for upload after the placement is created

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
// API-Helfer
// ---------------------------------------------------------------------------

async function apiFetch(path, opts = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const res = await fetch(path, Object.assign(defaults, opts));
  if (res.status === 401) { toast('Nicht authentifiziert — Browser-Dialog verwenden.'); throw new Error('401'); }
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
  if (res.status === 401) { toast('Nicht authentifiziert.'); throw new Error('401'); }
  if (!res.ok) throw new Error(await extractDetail(res));
  return res.json();
}

// ---------------------------------------------------------------------------
// Kampagnen-Status (Hero) — goal-gradient, never zero (principle 2)
// ---------------------------------------------------------------------------

const HERO_RING_R    = 52;
const HERO_RING_CIRC = 2 * Math.PI * HERO_RING_R;

function initHeroRing() {
  const ringFill = document.getElementById('hero-ring-fill');
  if (!ringFill) return;
  ringFill.style.strokeDasharray = `${HERO_RING_CIRC}`;
  ringFill.style.strokeDashoffset = `${HERO_RING_CIRC}`; // start fully empty, animates in on first render
}

/** progress = (1 [Setup] + gatewayPlaced + Σ per-device[placed .4 + running .3 + done .3]) / (2 + N_devices)
 * Setup contributes a flat 1 so the ring is never 0 — the operator always
 * sees credit for showing up and getting the app running. */
function computeCampaignProgress() {
  const gateway = _nodes.find(n => n.kind === 'gateway');
  const devices = _nodes.filter(n => n.kind === 'device');
  const gatewayPlaced = !!(gateway && gateway.placement);

  let deviceSum = 0, doneCount = 0, runningCount = 0, placedCount = 0;
  for (const n of devices) {
    let v = 0;
    if (n.placement) { v += 0.4; placedCount++; }
    if (n.active_run && n.active_run.status === 'running') { v += 0.3; runningCount++; }
    if (n.last_run && n.last_run.status === 'done') { v += 0.3; doneCount++; }
    deviceSum += v;
  }

  const numerator = 1 + (gatewayPlaced ? 1 : 0) + deviceSum;
  const denominator = 2 + devices.length;
  const progress = denominator > 0 ? Math.max(0, Math.min(1, numerator / denominator)) : 0.5;

  return { progress, gatewayPlaced, deviceCount: devices.length, doneCount, runningCount, placedCount };
}

function renderHero() {
  const pctEl     = document.getElementById('hero-pct');
  const ringFill  = document.getElementById('hero-ring-fill');
  const subEl     = document.getElementById('hero-sub');
  if (!pctEl || !ringFill || !subEl) return;

  const { progress, gatewayPlaced, deviceCount, doneCount, runningCount } = computeCampaignProgress();

  pctEl.textContent = `${Math.round(progress * 100)}%`;
  ringFill.style.strokeDashoffset = `${HERO_RING_CIRC * (1 - progress)}`;

  const parts = [gatewayPlaced ? 'Gateway steht ✓' : 'Gateway noch nicht platziert'];
  if (deviceCount > 0) parts.push(`${doneCount}/${deviceCount} Geräte vermessen`);
  if (runningCount > 0) parts.push(`${runningCount} ${runningCount === 1 ? 'läuft' : 'laufen'}`);
  subEl.textContent = parts.join(' · ');
}

// ---------------------------------------------------------------------------
// Node-Auswahl + Übersicht (GET /api/nodes)
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
    refreshDeviceStatus(); // fire-and-forget — Geräte-Status (Trust & Sichtbarkeit)
  } catch (e) {
    toast(`Fehler beim Laden der Geräte: ${e.message}`);
  }
}

function renderNodeSelect() {
  const sel = document.getElementById('node-select');
  if (!_nodes.length) {
    sel.innerHTML = '<option value="">— keine Geräte —</option>';
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

/** Select a node. When *scroll* is true (card tap in the Übersicht), the
 * "Ausgewähltes Gerät / Gateway" detail panel is scrolled into view. */
function selectNode(id, scroll = false) {
  _selectedNodeId = id;
  const sel = document.getElementById('node-select');
  if (sel) sel.value = String(id);
  renderSelectedNode();
  renderNodeDashboard();
  refreshDeviceStatus(); // fire-and-forget — Geräte-Status (Trust & Sichtbarkeit)
  if (scroll) {
    const panel = document.getElementById('card-selected');
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ---------------------------------------------------------------------------
// Reciprocity — live signal shown immediately on selection (principle 3)
// ---------------------------------------------------------------------------

/** sehr gut / gut / grenzwertig / schlecht — same thresholds as rssiClass,
 * labelled so the number is never shown "bare" (contrast/anchoring). */
function rssiQualityLabel(v) {
  if (v == null) return { cls: '', label: '—' };
  if (v > -80)  return { cls: 'm-good', label: 'sehr gut' };
  if (v > -110) return { cls: 'm-ok',   label: 'gut' };
  if (v > -120) return { cls: 'm-warn', label: 'grenzwertig' };
  return { cls: 'm-bad', label: 'schlecht' };
}

function fmtAgo(ms) {
  if (ms == null) return '';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 5) return 'gerade eben';
  if (s < 60) return `vor ${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `vor ${m} min`;
  const h = Math.floor(m / 60);
  return `vor ${h} h`;
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

/** "Letztes Paket: vor 12 s · Sendeintervall: ~5 min" — small muted
 * metadata line shown on each Übersicht card (the selected-device panel
 * shows the same two facts, more prominently, in the Geräte-Status block
 * instead — not repeated here). */
function metaLineText(m) {
  const age = m ? ageFromUplinkAt(m.lastUplinkAt) : '—';
  const interval = m ? fmtInterval(m.intervalSeconds) : '—';
  return `Letztes Paket: ${age} · Sendeintervall: ${interval}`;
}

/** Big RSSI number + quality label only — "Letztes Paket"/"Sendeintervall"
 * live exclusively in the Geräte-Status block below (no duplication). */
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

/** Cheap 1 s ticker — updates every visible Übersicht card's "vor Xs" meta
 * line and the Geräte-Status block's age text, no re-render (plain
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
    renderDeviceStatusBlock(); // cheap re-render of "vor X" text, no fetch
  }, 1000);
}

// ---------------------------------------------------------------------------
// Ausgewähltes Gerät / Gateway
// ---------------------------------------------------------------------------

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
    nameEl.textContent = 'Keine Geräte verfügbar';
    euiEl.textContent = '';
    runPill.style.display = 'none';
    placeInfo.innerHTML = '<div class="place-empty">Zuerst ein Gerät in ChirpStack registrieren (unten) und das Cockpit neu starten.</div>';
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
    return;
  }

  nameEl.textContent = node.name;
  euiEl.textContent = node.eui;

  const isDevice = node.kind === 'device';
  histDetails.style.display = isDevice ? '' : 'none';

  // Placement
  const p = node.placement;
  placeInfo.innerHTML = p
    ? `<div class="place-loc">${esc(p.floor || '—')} · ${esc(p.room || '—')}</div>
       <div class="place-desc">${esc(p.description || '—')}</div>
       ${p.note ? `<div class="place-note">${esc(p.note)}</div>` : ''}`
    : `<div class="place-empty">Noch nicht platziert.</div>`;

  // Photos of the current placement — "deine Sammlung" (endowment)
  photosEl.innerHTML = (p && p.photo_ids && p.photo_ids.length)
    ? p.photo_ids.map(id => `<div class="pthumb view"><img src="/api/photo/${id}" alt="Foto" loading="lazy"></div>`).join('')
    : '';

  if (isDevice) {
    const run = node.active_run;
    const lastRun = node.last_run;
    const justDone = !run && lastRun && lastRun.status === 'done';

    runPill.style.display = '';
    if (run) {
      runPill.textContent = `● Läuft — ${run.packets} Pakete`;
      runPill.className = 'pill on';
    } else if (justDone) {
      runPill.textContent = 'fertig ✓';
      runPill.className = 'pill';
    } else {
      runPill.textContent = 'Kein Run';
      runPill.className = 'pill';
    }

    metricsEl.style.display = '';
    metricsEl.innerHTML = selMetricsHtml(_devMetrics[node.eui] || {});

    // Sweep timeline only while a run is actually active — a finished run's
    // progress is already conveyed by the "fertig ✓" pill above and its own
    // chart in Verlauf below, not repeated here.
    const progressHtml = run ? runProgressHtml(run, { compact: false }) : '';
    progressEl.style.display = progressHtml ? '' : 'none';
    progressEl.innerHTML = progressHtml;

    btnPlace.textContent = 'Platzieren / Umsetzen';
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
    runPill.textContent = running ? '● Läuft' : 'Kein Run';
    runPill.className = 'pill' + (running ? ' on' : '');
  } else {
    runPill.style.display = 'none';
  }
}

/** Compact, muted single line under the signal hero — SNR/SF/PDR only; the
 * big number in #signal-hero is the one and only place RSSI is shown. */
function selMetricsHtml(m) {
  return `
    <span class="${snrClass(m.snr)}">SNR&nbsp;${fmtNum(m.snr)}&nbsp;dB</span>
    <span>${m.sf != null ? 'SF' + m.sf : '—'}</span>
    <span class="${pdrClass(m.pdr)}">PDR&nbsp;${m.pdr != null ? (m.pdr * 100).toFixed(1) + ' %' : '—'}</span>
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
// Geräte-Status — "arbeitet die Konfiguration?" (Trust & Sichtbarkeit)
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

/** Duration without the "vor "/"seit " prefix, e.g. "12 s", "4 h". */
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
    return { text: 'wartet auf erstes Paket ⚠', cls: 'm-warn' };
  }
  const ageMs = Date.now() - new Date(m.lastUplinkAt).getTime();
  const targetSeconds = targetIntervalMinutes(node) * 60;
  if (ageMs > targetSeconds * 2000) {
    return { text: `seit ${fmtDuration(ageMs)} still ⚠`, cls: 'm-bad' };
  }
  return { text: fmtAgo(ageMs), cls: 'm-good' };
}

/** "~5 min ✓ (Ziel erreicht)" vs. "~4 h ⚠ (noch Standard)" — tolerance of
 * ±20 % (min. ±1 min) around the target counts as "reached". */
function deviceStatusInterval(m, node) {
  if (!m || m.intervalSeconds == null) return { text: '—', cls: '' };
  const target = targetIntervalMinutes(node);
  const measuredMin = m.intervalSeconds / 60;
  const tolerance = Math.max(1, target * 0.2);
  const reached = Math.abs(measuredMin - target) <= tolerance;
  const text = `${fmtInterval(m.intervalSeconds)} ${reached ? '✓ (Ziel erreicht)' : '⚠ (noch Standard)'}`;
  return { text, cls: reached ? 'm-good' : 'm-warn' };
}

/** "5-min-Befehl in Queue" (still waiting for the device's next uplink) vs.
 * "gesendet ✓ vor X" (txack/ack seen) vs. "—" (no config downlink involved). */
function deviceStatusConfigDl(status) {
  if (!status) return { text: '—', cls: '' };
  const queuedInterval = (status.queued || []).find(
    q => q.f_port === 1 && /^02[0-9a-f]{2}$/i.test(q.data_hex || '')
  );
  if (queuedInterval) {
    const minutes = parseInt(queuedInterval.data_hex.slice(2, 4), 16);
    return { text: `${minutes}-min-Befehl in Queue`, cls: 'm-warn' };
  }
  if (status.last_downlink_at) {
    return { text: `gesendet ✓ ${ageFromUplinkAt(status.last_downlink_at)}`, cls: 'm-good' };
  }
  return { text: '—', cls: '' };
}

/** Re-render the block from the currently cached _devMetrics/_devConfigStatus
 * — cheap, called every second by the signal-age ticker for smooth "vor X"
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
    toast('5-Minuten-Befehl eingereiht — wirkt beim nächsten Uplink des Geräts.');
    await refreshDeviceStatus();
  } catch (e) {
    toast(`Fehler: ${e.message}`);
  }
}

async function wakeDeviceTest() {
  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') return;
  try {
    // 0x04 = HW/SW-Version lesen (bestätigt) — reuses the existing loopback.
    await apiJSON('/api/downlink', {
      method: 'POST',
      body: JSON.stringify({ dev_eui: node.eui, f_port: 1, data_hex: '04', count: true }),
    });
    toast('Test-Downlink eingereiht — Gerät antwortet beim nächsten Uplink.');
    await refreshDeviceStatus();
  } catch (e) {
    toast(`Fehler: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Run-Fortschritt — smooth client-side ticking between SSE events, snapped
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
 * plan (contrast/anchoring), e.g. "14 h von 24 h" instead of a bare
 * "noch 10 h" that hides how big the plan actually is. */
function fmtHoursOfTotal(elapsedSeconds, totalSeconds) {
  const eh = Math.floor(Math.max(0, elapsedSeconds) / 3600);
  const th = Math.max(1, Math.round(totalSeconds / 3600));
  return `${eh} h von ${th} h`;
}

/** Glowing segmented SF-sweep timeline (wow factor) + an anchored label:
 * "SF9 · 2 von 3 SF-Stufen · 14 h von 24 h". Returns '' for a run with no
 * schedule (Phase A fixed run) — caller decides what to show instead. */
function runProgressHtml(run, opts = {}) {
  if (!run || !run.planned_seconds || !run.sf_schedule || !run.sf_schedule.length) return '';
  const compact = !!opts.compact;

  const live = liveRunProgress(run);
  const idx = live.segmentIndex ?? 0;
  const total = run.sf_schedule.length;
  const sfLabel = live.currentSf != null ? `SF${live.currentSf}` : '—';
  const stepsLabel = `${Math.min(idx + 1, total)} von ${total} SF-Stufen`;
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
    ? `<strong>fertig ✓</strong> · ${esc(stepsLabel)} · ${esc(timeLabel)}`
    : `<strong>${esc(sfLabel)}</strong> · ${esc(stepsLabel)} · ${esc(timeLabel)}`;

  return `
    <div class="sweep-timeline${compact ? ' compact' : ''}">${segs}</div>
    <div class="run-progress-label${run.done ? ' done' : ''}">${label}</div>
  `;
}

// ---------------------------------------------------------------------------
// "fertig ✓" celebration — one-shot pop/glow on the transition to done
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

/** "SF7 ✓, SF9 läuft — SF12 fehlt · 142 Pakete" */
function sweepStatusText(run) {
  if (!run) return '';
  if (!run.sf_schedule || !run.sf_schedule.length) return `${run.packets} Pakete`;
  const idx = run.segment_index ?? 0;
  const doneParts = run.sf_schedule.slice(0, idx).map(s => `SF${s.sf} ✓`);
  const current = run.sf_schedule[idx] ? [`SF${run.sf_schedule[idx].sf} läuft`] : [];
  const missing = run.sf_schedule.slice(idx + 1).map(s => `SF${s.sf}`);
  let text = doneParts.concat(current).join(', ');
  if (missing.length) text += ` — ${missing.join('/')} fehlt`;
  return `${text} · ${run.packets} Pakete`;
}

// ---------------------------------------------------------------------------
// Generic confirm modal (reused for stop-run + gateway-force loss prompts)
// ---------------------------------------------------------------------------

let _confirmResolve = null;

function confirmModal({ title, message, icon = '⚠️', okLabel = 'Bestätigen', cancelLabel = 'Abbrechen' }) {
  return new Promise(resolve => {
    _confirmResolve = resolve;
    document.getElementById('confirm-icon').textContent = icon;
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').innerHTML = message;
    document.getElementById('confirm-list').innerHTML = '';
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
// Run starten / stoppen (selected device) — timed SF-sweep
// ---------------------------------------------------------------------------

const RUN_PRESETS = {
  sf7_sf9_sf12: [7, 9, 12],
  sf9_sf12:     [9, 12],
  sf9:          [9],
  sf12:         [12],
};

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
  });
}

/** "Anpassen" submit: build a schedule from the duration/interval/preset fields. */
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
      toast('Run gestartet — viel Erfolg mit der Messung!');
      setMsg(msg, '');
      await loadNodes();
    } else {
      setMsg(msg, `Run nicht gestartet: ${await extractDetail(res)}`, 'err');
    }
  } catch (e) {
    setMsg(msg, `Fehler: ${e.message}`, 'err');
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
      ? `Beim Abbruch fehlen die <strong>${esc(missing.join('/'))}</strong>-Daten.`
      : 'Der letzte Abschnitt ist fast abgeschlossen.';
    const ok = await confirmModal({
      icon: '⚠️',
      title: 'Messung wirklich beenden?',
      message: `<p>${esc(statusText)}</p><p>${warnLine} Wirklich beenden?</p>`,
      okLabel: 'Messung beenden',
      cancelLabel: 'Weiterlaufen lassen',
    });
    if (!ok) return;
  }

  try {
    await apiJSON('/api/run/stop', {
      method: 'POST',
      body: JSON.stringify({ device_node_id: _selectedNodeId }),
    });
    toast('Run gestoppt.');
    setMsg(msg, '');
    await loadNodes();
  } catch (e) {
    setMsg(msg, `Fehler: ${e.message}`, 'err');
  }
}

// ---------------------------------------------------------------------------
// Platzieren / Umsetzen / Gateway umsetzen — Bottom Sheet
// Smart defaults (principle 1) + outcome-stating submit labels (principle 4)
// ---------------------------------------------------------------------------

function openPlaceSheet(mode) {
  const node = _nodesById[_selectedNodeId];
  if (!node) return;

  _sheetMode = mode;
  _sheetPhotos = [];
  renderSheetPhotoThumbs();

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
    document.getElementById('sheet-title').textContent = 'Gateway umsetzen';
    submitBtn.textContent = 'Standort speichern';
  } else if (hasRun) {
    document.getElementById('sheet-title').textContent = 'Gerät umsetzen';
    submitBtn.textContent = 'Umsetzen — altes Protokoll schließen';
  } else {
    document.getElementById('sheet-title').textContent = 'Gerät platzieren';
    submitBtn.textContent = 'Platzieren & Messung starten';
  }
  document.getElementById('sheet-antenna-field').style.display = mode === 'gateway' ? 'none' : '';
  document.getElementById('sheet-photo-field').style.display   = mode === 'gateway' ? 'none' : '';

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
}

function closeSheetBackdrop(e) {
  if (e.target === document.getElementById('place-ov')) closeSheet();
}

// --- Foto-Aufnahme (bis zu 3) ---

function onSheetPhotoSelected(e) {
  const file = e.target.files && e.target.files[0];
  e.target.value = ''; // allow re-selecting the same file again
  if (!file) return;
  if (_sheetPhotos.length >= 3) return;
  _sheetPhotos.push(file);
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
      <img src="${URL.createObjectURL(f)}" alt="Foto ${i + 1}">
      <button type="button" class="pthumb-x" onclick="removeSheetPhoto(${i})">×</button>
    </div>
  `).join('');
  const addBtn = document.getElementById('sheet-photo-add-btn');
  if (addBtn) addBtn.style.display = _sheetPhotos.length >= 3 ? 'none' : '';
}

// --- Absenden ---

async function submitSheet() {
  const msg = document.getElementById('sheet-msg');
  const floor       = document.getElementById('sheet-floor').value.trim();
  const room        = document.getElementById('sheet-room').value.trim();
  const description = document.getElementById('sheet-desc').value.trim();
  const note        = document.getElementById('sheet-note').value.trim();

  const btn = document.getElementById('sheet-submit-btn');
  btn.disabled = true;
  setMsg(msg, 'Speichere…');

  try {
    if (_sheetMode === 'gateway') {
      const res = await apiFetch('/api/gateway/move', {
        method: 'POST',
        body: JSON.stringify({ floor, room, description, note }),
      });
      if (res.ok) {
        toast('Gateway umgesetzt.');
        closeSheet();
        await loadNodes();
      } else if (res.status === 409) {
        const body = await res.json();
        const openRuns = (body.detail && body.detail.open_runs) || [];
        showGatewayConflict(openRuns);
      } else {
        setMsg(msg, `Fehler: ${await extractDetail(res)}`, 'err');
      }
    } else {
      const node = _nodesById[_selectedNodeId];
      if (!node) { setMsg(msg, 'Kein Gerät ausgewählt.', 'err'); return; }

      const hasRun = !!node.active_run;
      let placementId;
      if (hasRun) {
        const result = await apiJSON('/api/relocate', {
          method: 'POST',
          body: JSON.stringify({
            device_node_id: node.id, floor, room, description, note, antenna: _sheetAntenna,
          }),
        });
        placementId = result.placement_id;
      } else {
        const result = await apiJSON('/api/placement', {
          method: 'POST',
          body: JSON.stringify({
            node_id: node.id, floor, room, description, note, antenna: _sheetAntenna,
          }),
        });
        placementId = result.placement_id;
      }

      for (const file of _sheetPhotos) {
        try {
          await uploadPhoto(placementId, file);
        } catch (e) {
          toast(`Foto-Upload fehlgeschlagen: ${e.message}`);
        }
      }

      if (hasRun) {
        // /api/relocate already closed the old run and opened a new one.
        toast('Umgesetzt — neues Protokoll gestartet.');
      } else {
        // The sheet button promises "… & Messung starten" — actually start it,
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
          toast('Platziert — Messung gestartet (24 h Sweep).');
        } catch (e) {
          // Most likely: gateway not placed yet (run/start → 409).
          toast('Platziert, aber Messung NICHT gestartet — Gateway zuerst platzieren.');
        }
      }
      closeSheet();
      await loadNodes();
    }
  } catch (e) {
    setMsg(msg, `Fehler: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
  }
}

/** Loss aversion: "⚠️ N laufende Messungen gehen verloren", each device's
 * captured/at-risk SF stages spelled out — using data already cached from
 * the last loadNodes() (no extra API call; the 409 body doesn't carry
 * sweep detail). */
function showGatewayConflict(openRuns) {
  document.getElementById('sheet-form').style.display = 'none';
  const box = document.getElementById('sheet-conflict');
  box.style.display = '';

  const titleEl = document.getElementById('sheet-conflict-title');
  titleEl.textContent = openRuns.length === 1
    ? '1 laufende Messung geht verloren'
    : `${openRuns.length} laufende Messungen gehen verloren`;

  const list = document.getElementById('sheet-conflict-list');
  list.innerHTML = openRuns.length
    ? openRuns.map(r => {
        const liveRun = (_nodesById[r.device_node_id] && _nodesById[r.device_node_id].active_run) || null;
        const detail = liveRun ? sweepStatusText(liveRun) : `${r.packets} Pakete · seit ${fmtTime(r.started_at)}`;
        return `
          <div class="loss-row">
            <div class="loss-name">${esc(r.name)}</div>
            <div class="loss-detail">${esc(detail)}</div>
          </div>`;
      }).join('')
    : '<div class="hint">Keine Details verfügbar.</div>';
}

async function forceGatewayMove() {
  const floor       = document.getElementById('sheet-floor').value.trim();
  const room        = document.getElementById('sheet-room').value.trim();
  const description = document.getElementById('sheet-desc').value.trim();
  const note        = document.getElementById('sheet-note').value.trim();
  try {
    await apiJSON('/api/gateway/move/force', {
      method: 'POST',
      body: JSON.stringify({ floor, room, description, note }),
    });
    toast('Alle Runs quittiert, Gateway umgesetzt.');
    closeSheet();
    await loadNodes();
  } catch (e) {
    toast(`Fehler: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Verlauf (run history)
// ---------------------------------------------------------------------------

function onHistoryToggle(details) {
  if (details.open) loadHistory();
}

async function loadHistory() {
  const body = document.getElementById('history-body');
  if (!body || _selectedNodeId == null) return;
  body.innerHTML = '<p class="hint">Lädt…</p>';
  try {
    const data = await apiJSON(`/api/runs?node_id=${_selectedNodeId}`);
    renderHistory(data.runs || []);
  } catch (e) {
    body.innerHTML = `<p class="hint">Fehler: ${esc(e.message)}</p>`;
  }
}

function renderHistory(runs) {
  const body = document.getElementById('history-body');
  // The active run's chart already lives at #sel-chart (always visible) —
  // Verlauf only lists past/completed runs to avoid showing it twice.
  const pastRuns = runs.filter(r => r.status !== 'running');
  if (!pastRuns.length) { body.innerHTML = '<p class="hint">Noch keine abgeschlossenen Runs.</p>'; return; }
  body.innerHTML = `
    <div style="overflow-x:auto">
      <table class="dtbl">
        <thead><tr><th>Standort</th><th>Status</th><th>Pakete</th><th>Start</th><th>CSV</th></tr></thead>
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
              <td colspan="5"><div class="hist-chart" id="hist-chart-${r.id}"><p class="hint">Lädt…</p></div></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>`;
  // Charts are always expanded now — fetch each run's series right away.
  for (const r of pastRuns) loadRunChart(r.id);
}

function histStatusLabel(s) {
  return { running: 'Läuft', done: 'Fertig', aborted: 'Abgebrochen' }[s] || s;
}

// ---------------------------------------------------------------------------
// Verlauf — per-run RSSI/SNR/SF line chart (hand-rolled inline SVG, no
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

/** Charts in the Verlauf list are always expanded (no click-to-reveal) —
 * fetch + render straight into the container renderHistory() already laid
 * out for this run. */
async function loadRunChart(runId) {
  const container = document.getElementById(`hist-chart-${runId}`);
  if (!container) return;
  try {
    const data = await apiJSON(`/api/run/${runId}/series`);
    container.innerHTML = buildRunChartHtml(data);
  } catch (e) {
    container.innerHTML = `<p class="hint">Fehler: ${esc(e.message)}</p>`;
  }
}

let _selChartDebounce = null;

/** Debounced re-fetch of the selected-device chart — called on every SSE
 * 'uplink' event for that device, so a burst of near-simultaneous events
 * (e.g. several devices reporting close together) collapses into a single
 * request instead of one per event. */
function scheduleSelectedChartRefresh() {
  if (_selChartDebounce) clearTimeout(_selChartDebounce);
  _selChartDebounce = setTimeout(() => {
    _selChartDebounce = null;
    loadSelectedChart();
  }, 1500);
}

/** Always-visible RSSI/SNR chart in the selected-device panel — the
 * device's active run, falling back to its most recent run, falling back
 * to the "no packets yet" empty state when it has never run at all.
 * Called directly (not debounced) from renderSelectedNode() so switching
 * devices feels instant; SSE-driven refreshes go through the debounced
 * scheduleSelectedChartRefresh() above. */
async function loadSelectedChart() {
  const wrap = document.getElementById('sel-chart-wrap');
  const container = document.getElementById('sel-chart');
  if (!wrap || !container) return;

  const node = _nodesById[_selectedNodeId];
  if (!node || node.kind !== 'device') { wrap.style.display = 'none'; return; }
  wrap.style.display = '';

  const run = node.active_run || node.last_run;
  if (!run) {
    container.innerHTML = '<p class="hint">Noch keine Pakete in diesem Run.</p>';
    return;
  }

  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/run/${run.id}/series`);
    if (_selectedNodeId !== nodeId) return; // selection changed while awaiting
    container.innerHTML = buildRunChartHtml(data);
  } catch (e) {
    if (_selectedNodeId !== nodeId) return;
    container.innerHTML = `<p class="hint">Fehler: ${esc(e.message)}</p>`;
  }
}

/** Build the inline-SVG chart + legend markup for one run's series response
 * (GET /api/run/{id}/series). Pure w.r.t. the DOM — returns an HTML string. */
function buildRunChartHtml(data) {
  const points = data.points || [];
  if (!points.length) {
    return '<p class="hint">Noch keine Pakete in diesem Run.</p>';
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
    <svg viewBox="0 0 ${W} ${H}" class="rc-svg" preserveAspectRatio="xMidYMid meet" role="img" aria-label="RSSI- und SNR-Verlauf">
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
// Übersicht — Node-Dashboard (device cards)
// ---------------------------------------------------------------------------

function renderNodeDashboard() {
  const grid = document.getElementById('node-grid');
  if (!_nodes.length) {
    grid.innerHTML = '<div class="hint" style="padding:20px 0;text-align:center">Keine Geräte gefunden.</div>';
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
    summaryEl.textContent = doneCount > 0 ? `${doneCount} fertig` : '';
  }
}

function gatewayCardHtml(n) {
  const loc = n.placement
    ? `${esc(n.placement.floor || '—')} · ${esc(n.placement.room || '—')}`
    : 'nicht platziert';
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
    : 'nicht platziert';
  const m = _devMetrics[n.eui] || {};
  const progressRun = n.active_run || n.last_run;

  const statusHtml = justDone
    ? `<span class="nc-done">fertig ✓</span>`
    : `<span class="nc-run ${running ? 'on' : ''}">${running ? '● Läuft' : 'kein Run'}</span>`;

  return `
    <div class="node-card ${running ? 'running' : ''} ${n.id === _selectedNodeId ? 'selected' : ''}" id="nc-${n.id}" onclick="selectNode(${n.id}, true)">
      <div class="nc-top">
        <span class="nc-name">${esc(n.name)}</span>
        ${statusHtml}
      </div>
      <div class="nc-loc">${loc}</div>
      ${running ? `<div class="nc-packets">${n.active_run.packets} Pakete</div>` : ''}
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
    `<img src="/api/photo/${id}" alt="Foto" loading="lazy">`
  ).join('')}</div>`;
}

/** RSSI / SNR / SF only, per the Übersicht card spec (PDR stays in the
 * "Ausgewähltes Gerät" detail panel via selMetricsHtml). */
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
// Farb-Helfer (reused across selected panel + dashboard cards)
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
// Geräte-Registrierung (ChirpStack device list, Vicki bulk)
// ---------------------------------------------------------------------------

async function registerDevice() {
  const name     = document.getElementById('dev-name').value.trim();
  const dev_eui  = document.getElementById('dev-eui').value.trim().toLowerCase();
  const app_key  = document.getElementById('dev-appkey').value.trim().toLowerCase();
  const join_eui = document.getElementById('dev-joineui').value.trim() || '0000000000000000';
  const msg      = document.getElementById('dev-msg');

  if (!name || !dev_eui || !app_key) {
    setMsg(msg, 'Name, DevEUI und AppKey sind Pflichtfelder.', 'err');
    return;
  }
  try {
    const data = await apiJSON('/api/devices', {
      method: 'POST',
      body: JSON.stringify({ name, dev_eui, app_key, join_eui }),
    });
    setMsg(msg, `Registriert: ${data.dev_eui}`);
    toast('Gerät registriert.');
    loadDevices();
  } catch (e) {
    setMsg(msg, `Fehler: ${e.message}`, 'err');
  }
}

async function loadDevices() {
  try {
    const data = await apiJSON('/api/devices');
    renderDeviceList(data.devices || []);
  } catch (e) {
    setMsg(document.getElementById('dev-msg'), `Fehler beim Laden: ${e.message}`, 'err');
  }
}

function renderDeviceList(devices) {
  _currentDevices = devices;
  const tbody = document.getElementById('dev-list-body');
  if (!devices.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:12px 0">— keine Geräte —</td></tr>';
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
    setMsg(msg, 'Keine Geräte — zuerst Geräteliste laden (Geräte-Registrierung).', 'err');
    return;
  }
  let ok = 0, fail = 0, firstErr = null;
  for (const d of _currentDevices) {
    try {
      // 0x02 SetSendPeriod, 0x05 = 5 Minuten
      // count:false — Interval-Kommando zählt nicht in DL-PDR-Nenner
      await apiJSON('/api/downlink', {
        method: 'POST',
        body: JSON.stringify({ dev_eui: d.dev_eui, f_port: 1, data_hex: '0205', count: false }),
      });
      ok++;
    } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  const txt = `Intervall eingereiht: ${ok} ok` + (fail ? `, ${fail} fehlgeschlagen: ${firstErr}` : '') + '.';
  setMsg(msg, txt, fail ? 'err' : '');
  toast(`Vicki Intervall: ${ok} eingereiht.`);
}

async function sendVickiLoopback() {
  const msg = document.getElementById('vicki-msg');
  if (!_currentDevices.length) {
    setMsg(msg, 'Keine Geräte — zuerst Geräteliste laden (Geräte-Registrierung).', 'err');
    return;
  }
  let ok = 0, fail = 0, firstErr = null;
  for (const d of _currentDevices) {
    try {
      // 0x04 = HW/SW-Version lesen (bestätigt, zählt in DL-PDR; count:true)
      await apiJSON('/api/downlink', {
        method: 'POST',
        body: JSON.stringify({ dev_eui: d.dev_eui, f_port: 1, data_hex: '04', count: true }),
      });
      ok++;
    } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  const txt = `HW/SW-Version eingereiht: ${ok} ok` + (fail ? `, ${fail} fehlgeschlagen: ${firstErr}` : '') + '.';
  setMsg(msg, txt, fail ? 'err' : '');
  toast(`Vicki HW/SW-Version: ${ok} eingereiht.`);
}

// ---------------------------------------------------------------------------
// Downlink-Loopback
// ---------------------------------------------------------------------------

async function enqueueDownlink() {
  const msg = document.getElementById('dl-msg');
  const body = {
    dev_eui:  document.getElementById('dl-eui').value.trim().toLowerCase(),
    f_port:   parseInt(document.getElementById('dl-fport').value),
    data_hex: document.getElementById('dl-data').value.trim() || '00',
  };
  if (!body.dev_eui) { setMsg(msg, 'DevEUI ist Pflicht.', 'err'); return; }
  try {
    await apiJSON('/api/downlink', { method: 'POST', body: JSON.stringify(body) });
    setMsg(msg, `Downlink eingereiht (FPort ${body.f_port}).`);
    toast('Downlink eingereiht.');
  } catch (e) {
    setMsg(msg, `Fehler: ${e.message}`, 'err');
  }
}

// ---------------------------------------------------------------------------
// Funkumgebung — always-on passive coexistence view (Trust & Sichtbarkeit).
// No start/stop: the gateway hears every LoRaWAN frame in range regardless
// of any toggle; this just visualises what CampaignState already tallies.
// ---------------------------------------------------------------------------

function updateCoexTable(event) {
  const key  = `ch${event.channel}_sf${event.sf}`;
  const prev = _coexData[key] || { frames: 0 };
  _coexData[key] = {
    channel: event.channel,
    sf:      event.sf,
    frames:  (prev.frames || 0) + 1,
    caf:     event.caf,
    tl:      event.traffic_light,
  };
  if (event.is_own === true) _coexOwn++;
  else if (event.is_own === false) _coexForeign++;
  renderCoexTable();
  renderCoexTotals();
}

function renderCoexTable() {
  const tbody = document.getElementById('coex-body');
  const rows  = Object.values(_coexData);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:10px">Keine Daten.</td></tr>';
    return;
  }
  rows.sort((a, b) => a.channel - b.channel || a.sf - b.sf);
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>CH${r.channel >= 0 ? r.channel : '?'}</td>
      <td>SF${r.sf}</td>
      <td>${r.frames}</td>
      <td>${r.caf != null ? (r.caf * 100).toFixed(3) + ' %' : '—'}</td>
      <td class="tl-${r.tl || 'measuring'}">${(r.tl || 'measuring').toUpperCase()}</td>
    </tr>
  `).join('');
}

function renderCoexTotals() {
  const ownEl = document.getElementById('coex-own-count');
  const foreignEl = document.getElementById('coex-foreign-count');
  if (ownEl) ownEl.textContent = _coexOwn;
  if (foreignEl) foreignEl.textContent = _coexForeign;
}

// ---------------------------------------------------------------------------
// Panel — Phase / SF-Wechsel
// ---------------------------------------------------------------------------

const _PHASE_LABELS = {
  sf9:  'Phase 1 · SF9',
  sf12: 'Phase 2 · SF12',
  adr:  'Normal · ADR',
};

async function setPhase(phase) {
  const msg = document.getElementById('phase-msg');
  try {
    const res = await apiFetch('/api/phase', { method: 'POST', body: JSON.stringify({ phase }) });
    if (res.ok) {
      const data = await res.json();
      setMsg(msg, `Umgeschaltet: ${(data.switched || []).length} Gerät(e).`);
      _applyPhase(phase);
      toast(`Phase: ${_PHASE_LABELS[phase] || phase}`);
    } else {
      let detail;
      try { detail = (await res.json()).detail; } catch (_) { detail = null; }
      if (detail && typeof detail === 'object' && detail.failed && detail.failed.length) {
        const first = detail.failed[0];
        setMsg(msg, `${detail.failed.length} Gerät(e) fehlgeschlagen. Erstes: ${first.dev_eui}: ${first.error}`, 'err');
      } else {
        setMsg(msg, `Fehler ${res.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`, 'err');
      }
      // _applyPhase wird NICHT aufgerufen — Anzeige bleibt bei alter Phase
    }
  } catch (e) {
    setMsg(msg, `Fehler: ${e.message}`, 'err');
  }
}

function _applyPhase(phase) {
  const label = _PHASE_LABELS[phase] || phase;
  const big   = document.getElementById('phase-big');
  const pill  = document.getElementById('pill-phase');

  big.textContent  = label;
  big.className    = phase;
  pill.textContent = label;
  pill.className   = 'pill ' + phase;

  ['sf9', 'sf12', 'adr'].forEach(p => {
    const btn = document.getElementById(`pbtn-${p}`);
    if (!btn) return;
    if (p === phase) btn.setAttribute('data-a', p);
    else             btn.removeAttribute('data-a');
  });
}

// ---------------------------------------------------------------------------
// SSE — Live-Eventstream
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
      const selNode = _nodesById[_selectedNodeId];
      if (selNode && selNode.kind === 'device' && selNode.eui === eui) {
        scheduleSelectedChartRefresh();
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
      updateCoexTable(ev);
      break;
    case 'state':
      if (ev.phase) _applyPhase(ev.phase);
      break;
    case 'nodes':
      loadNodes();
      break;
  }
}

// ---------------------------------------------------------------------------
// Run-Fortschritt-Ticker — recomputes the progress bars/labels from
// wall-clock time every ~30 s so they move smoothly between SSE 'nodes'
// events; loadNodes() (triggered by that event) snaps them back to server
// truth (segment_index/current_sf/done).
// ---------------------------------------------------------------------------

let _progressTimer = null;

function startProgressTicker() {
  if (_progressTimer) return;
  _progressTimer = setInterval(() => {
    renderNodeDashboard();
    renderSelectedNode();
    refreshDeviceStatus(); // periodic refresh — queue/last-downlink can change without an SSE 'nodes' event
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
  startProgressTicker();
  startSignalAgeTicker();
}

function applyInitialState(s) {
  _applyPhase(s.phase || 'adr');
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

  // Funkumgebung (always-on) — seed totals + per-channel/SF table from the
  // snapshot so a page refresh shows what has already accumulated, not an
  // empty view until the next live frame arrives.
  _coexOwn = s.coex_own_frames || 0;
  _coexForeign = s.coex_foreign_frames || 0;
  for (const [key, count] of Object.entries(s.coex_frames || {})) {
    const m = key.match(/^ch(-?\d+)_sf(\d+)$/);
    if (!m) continue;
    _coexData[key] = {
      channel: parseInt(m[1], 10),
      sf:      parseInt(m[2], 10),
      frames:  count,
      caf:     null,
      tl:      'measuring',
    };
  }
  renderCoexTotals();
  renderCoexTable();
}

// ---------------------------------------------------------------------------
// Hilfe-Overlay
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
