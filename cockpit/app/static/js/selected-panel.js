// selected-panel.js — the "Selected device / gateway" detail card: header
// pills, the live signal hero, location/photos, the PDR-per-SF headline
// block, the RSSI/SNR chart, the sweep-progress timeline, and the
// collapsible "History" list of past runs for this device (distinct from
// the top-level History tab in history.js, which lists every run). Reads
// #dev-status-block visibility only — device-status.js owns its content.
// Unchanged behaviour from the old app.js; inline onclick/onchange/ontoggle
// replaced with addEventListener (cockpit-redesign Stage 2a, spec §6).
import { state } from './state.js';
import { apiJSON } from './api.js';
import { esc, setMsg, fmtNum, fmtTime, snrClass, rssiQualityLabel, histStatusLabel } from './format.js';
import { placeInfoHtml, photoThumbsHtml, renderPdrSfBlock, buildRunChartHtml } from './run-detail.js';
import { runProgressHtml } from './run.js';
import { renderDeviceStatusBlock } from './device-status.js';

export function renderSelectedNode() {
  const node          = state.nodesById[state.selectedNodeId];
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
    runPill.classList.add('is-hidden');
    placeInfo.innerHTML = '<div class="place-empty">First register a device in ChirpStack (below) and restart the cockpit.</div>';
    photosEl.innerHTML = '';
    metricsEl.classList.add('is-hidden');
    progressEl.classList.add('is-hidden');
    btnPlace.classList.add('is-hidden');
    runStartBlock.classList.add('is-hidden');
    btnStop.classList.add('is-hidden');
    btnGwMove.classList.add('is-hidden');
    histDetails.classList.add('is-hidden');
    if (devStatusBlock) devStatusBlock.classList.add('is-hidden');
    loadSelectedChart();
    loadSelectedPdrStats();
    return;
  }

  nameEl.textContent = node.name;
  euiEl.textContent = node.eui;

  const isDevice = node.kind === 'device';
  histDetails.classList.toggle('is-hidden', !isDevice);

  // Placement
  const p = node.placement;
  placeInfo.innerHTML = placeInfoHtml(p);

  // Photos of the current placement — "your collection" (endowment)
  photosEl.innerHTML = photoThumbsHtml(p && p.photo_ids);

  if (isDevice) {
    const run = node.active_run;
    const lastRun = node.last_run;
    const justDone = !run && lastRun && lastRun.status === 'done';

    runPill.classList.remove('is-hidden');
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

    metricsEl.classList.remove('is-hidden');
    metricsEl.innerHTML = selMetricsHtml(state.devMetrics[node.eui] || {});

    // Sweep timeline only while a run is actually active — a finished run's
    // progress is already conveyed by the "done ✓" pill above and its own
    // chart in History below, not repeated here.
    const progressHtml = run ? runProgressHtml(run, { compact: false }) : '';
    progressEl.classList.toggle('is-hidden', !progressHtml);
    progressEl.innerHTML = progressHtml;

    btnPlace.textContent = 'Place / Relocate';
    btnPlace.classList.remove('is-hidden');
    btnGwMove.classList.add('is-hidden');
    runStartBlock.classList.toggle('is-hidden', !!run);
    btnStop.classList.toggle('is-hidden', !run);

    if (devStatusBlock) devStatusBlock.classList.remove('is-hidden');
    renderDeviceStatusBlock();
  } else {
    runPill.classList.add('is-hidden');
    metricsEl.classList.add('is-hidden');
    progressEl.classList.add('is-hidden');
    btnPlace.classList.add('is-hidden');
    runStartBlock.classList.add('is-hidden');
    btnStop.classList.add('is-hidden');
    btnGwMove.classList.remove('is-hidden');
    if (devStatusBlock) devStatusBlock.classList.add('is-hidden');
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
    runPill.classList.add('is-hidden');
    return;
  }
  nodePill.textContent = node.name;
  if (node.kind === 'device') {
    const running = !!(node.active_run && node.active_run.status === 'running');
    runPill.classList.remove('is-hidden');
    runPill.textContent = running ? '● Running' : 'No run';
    runPill.className = 'pill' + (running ? ' on' : '');
  } else {
    runPill.classList.add('is-hidden');
  }
}

/** Big RSSI number + quality label only — "Last packet"/"Send interval"
 * live exclusively in the Device status block (device-status.js, no
 * duplication). */
function renderSignalHero(node) {
  const wrap = document.getElementById('signal-hero');
  if (!wrap) return;
  if (!node || node.kind !== 'device') { wrap.classList.add('is-hidden'); return; }

  const m = state.devMetrics[node.eui];
  if (!m || m.rssi == null) { wrap.classList.add('is-hidden'); return; }

  wrap.classList.remove('is-hidden');
  const numEl = document.getElementById('signal-hero-rssi');
  const qEl   = document.getElementById('signal-hero-quality');

  numEl.textContent = fmtNum(m.rssi);
  const q = rssiQualityLabel(m.rssi);
  qEl.textContent = q.label;
  qEl.className = 'signal-hero-quality ' + q.cls;
}

/** Compact, muted single line under the signal hero — SNR/SF only; the big
 * number in #signal-hero is the one and only place RSSI is shown, and PDR
 * lives in the "PDR per SF" headline block (per-SF, not this single
 * always-empty legacy figure — see run-detail.js's renderPdrSfBlock). */
function selMetricsHtml(m) {
  return `
    <span class="${snrClass(m.snr)}">SNR&nbsp;${fmtNum(m.snr)}&nbsp;dB</span>
    <span>${m.sf != null ? 'SF' + m.sf : '—'}</span>
  `;
}

export function updateSelectedMetrics(eui) {
  const node = state.nodesById[state.selectedNodeId];
  if (!node || node.kind !== 'device' || node.eui !== eui) return;
  const metricsEl = document.getElementById('sel-metrics');
  if (metricsEl) metricsEl.innerHTML = selMetricsHtml(state.devMetrics[eui] || {});
  renderSignalHero(node);
  const numEl = document.getElementById('signal-hero-rssi');
  if (numEl) {
    numEl.classList.remove('roll');
    void numEl.offsetWidth; // reflow to restart the animation
    numEl.classList.add('roll');
  }
}

// ---------------------------------------------------------------------------
// Always-visible RSSI/SNR chart + PDR-per-SF headline block for the
// selected device's active (or most recent) run.
// ---------------------------------------------------------------------------

let _selChartDebounce = null;

/** Debounced re-fetch of the selected-device chart AND PDR-per-SF block —
 * called on every SSE 'uplink' event for that device (sse.js), so a burst
 * of near-simultaneous events collapses into a single pair of requests
 * instead of one per event. */
export function scheduleSelectedRunRefresh() {
  if (_selChartDebounce) clearTimeout(_selChartDebounce);
  _selChartDebounce = setTimeout(() => {
    _selChartDebounce = null;
    loadSelectedChart();
    loadSelectedPdrStats();
  }, 1500);
}

/** Called directly (not debounced) from renderSelectedNode() so switching
 * devices feels instant; SSE-driven refreshes go through the debounced
 * scheduleSelectedRunRefresh() above. */
async function loadSelectedChart() {
  const wrap = document.getElementById('sel-chart-wrap');
  const container = document.getElementById('sel-chart');
  if (!wrap || !container) return;

  const node = state.nodesById[state.selectedNodeId];
  if (!node || node.kind !== 'device') { wrap.classList.add('is-hidden'); return; }
  wrap.classList.remove('is-hidden');

  const run = node.active_run || node.last_run;
  if (!run) {
    container.innerHTML = '<p class="hint">No packets in this run yet.</p>';
    return;
  }

  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/run/${run.id}/series`);
    if (state.selectedNodeId !== nodeId) return; // selection changed while awaiting
    container.innerHTML = buildRunChartHtml(data);
  } catch (e) {
    if (state.selectedNodeId !== nodeId) return;
    container.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

/** Same active/last-run resolution and staleness guard as loadSelectedChart
 * above. */
async function loadSelectedPdrStats() {
  const block = document.getElementById('pdr-sf-block');
  if (!block) return;

  const node = state.nodesById[state.selectedNodeId];
  if (!node || node.kind !== 'device') { block.classList.add('is-hidden'); return; }

  const run = node.active_run || node.last_run;
  if (!run) { block.classList.add('is-hidden'); return; }
  block.classList.remove('is-hidden');

  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/run/${run.id}/stats`);
    if (state.selectedNodeId !== nodeId) return; // selection changed while awaiting
    renderPdrSfBlock(data);
  } catch (e) {
    if (state.selectedNodeId !== nodeId) return;
    const grid = document.getElementById('pdr-sf-grid');
    if (grid) grid.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

// ---------------------------------------------------------------------------
// "History" (collapsible, within THIS card) — a device's own past runs.
// Distinct from the top-level History tab (history.js), which lists every
// device's runs.
// ---------------------------------------------------------------------------

function onHistoryToggle(details) {
  if (details.open) loadHistory();
}

async function loadHistory() {
  const body = document.getElementById('history-body');
  if (!body || state.selectedNodeId == null) return;
  body.innerHTML = '<p class="hint">Loading…</p>';
  try {
    const data = await apiJSON(`/api/runs?node_id=${state.selectedNodeId}`);
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

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initSelectedPanel() {
  const historyDetails = document.getElementById('history-details');
  historyDetails.addEventListener('toggle', () => onHistoryToggle(historyDetails));
}
