// nodes.js — the Overview (device/gateway cards) and node selection:
// GET /api/nodes, the node picker in the "Selected device / gateway" card
// title, and the dashboard cards themselves. Unchanged behaviour from the
// old app.js; the cards' onclick="selectNode(...)" is now event delegation
// on the stable #node-grid container (cockpit-redesign Stage 2a, spec §6).
import { state } from './state.js';
import { apiJSON } from './api.js';
import { esc, toast, metaLineText, fmtNum, rssiClass, snrClass } from './format.js';
import { runProgressHtml, checkCelebration } from './run.js';
import { renderHero } from './hero.js';
import { renderSelectedNode } from './selected-panel.js';
import { refreshDeviceStatus } from './device-status.js';
import { populateEventDeviceChips } from './events.js';

export async function loadNodes() {
  try {
    const data = await apiJSON('/api/nodes');
    state.nodes = data.nodes || [];
    state.nodesById = {};
    for (const n of state.nodes) state.nodesById[n.id] = n;

    if (state.selectedNodeId == null || !state.nodesById[state.selectedNodeId]) {
      const firstDevice = state.nodes.find(n => n.kind === 'device');
      const fallback = firstDevice || state.nodes[0];
      state.selectedNodeId = fallback ? fallback.id : null;
    }

    renderHero();
    renderNodeSelect();
    renderSelectedNode();
    renderNodeDashboard();
    populateEventDeviceChips(); // Stage 1 event log — device filter chips
    refreshDeviceStatus(); // fire-and-forget — Device status (Trust & visibility)
  } catch (e) {
    toast(`Error loading devices: ${e.message}`);
  }
}

function renderNodeSelect() {
  const sel = document.getElementById('node-select');
  if (!state.nodes.length) {
    sel.innerHTML = '<option value="">— no devices —</option>';
    return;
  }
  sel.innerHTML = state.nodes.map(n =>
    `<option value="${n.id}">${n.kind === 'gateway' ? 'Gateway: ' : ''}${esc(n.name)}</option>`
  ).join('');
  if (state.selectedNodeId != null) sel.value = String(state.selectedNodeId);
}

function onNodeSelect() {
  const sel = document.getElementById('node-select');
  const id = parseInt(sel.value, 10);
  if (!isNaN(id)) selectNode(id);
}

/** Select a node. When *scroll* is true (card tap in the Overview), the
 * "Selected device / gateway" detail panel is scrolled into view. */
export function selectNode(id, scroll = false) {
  state.selectedNodeId = id;
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
// Overview — Node dashboard (device cards)
// ---------------------------------------------------------------------------

export function renderNodeDashboard() {
  const grid = document.getElementById('node-grid');
  if (!state.nodes.length) {
    grid.innerHTML = '<div class="hint" style="padding:20px 0;text-align:center">No devices found.</div>';
    return;
  }
  const gateways = state.nodes.filter(n => n.kind === 'gateway');
  const devices  = state.nodes.filter(n => n.kind === 'device');
  grid.innerHTML = gateways.map(gatewayCardHtml).join('') + devices.map(deviceCardHtml).join('');

  for (const n of devices) checkCelebration(n);

  const doneCount = devices.filter(n => n.last_run && n.last_run.status === 'done').length;
  const summaryEl = document.getElementById('overview-summary');
  if (summaryEl) {
    summaryEl.classList.toggle('is-hidden', doneCount === 0);
    summaryEl.textContent = doneCount > 0 ? `${doneCount} done` : '';
  }
}

function gatewayCardHtml(n) {
  const loc = n.placement
    ? `${esc(n.placement.floor || '—')} · ${esc(n.placement.room || '—')}`
    : 'not placed';
  return `
    <div class="node-card gw-card ${n.id === state.selectedNodeId ? 'selected' : ''}" id="nc-${n.id}" data-node-id="${n.id}">
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
  const m = state.devMetrics[n.eui] || {};
  const progressRun = n.active_run || n.last_run;

  const statusHtml = justDone
    ? `<span class="nc-done">done ✓</span>`
    : `<span class="nc-run ${running ? 'on' : ''}">${running ? '● Running' : 'no run'}</span>`;

  return `
    <div class="node-card ${running ? 'running' : ''} ${n.id === state.selectedNodeId ? 'selected' : ''}" id="nc-${n.id}" data-node-id="${n.id}">
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

export function updateNodeCardMetrics(eui) {
  const node = state.nodes.find(n => n.eui === eui);
  if (!node) return;
  const card = document.getElementById(`nc-${node.id}`);
  if (!card) return;
  const m = state.devMetrics[eui] || {};
  const metricsEl = card.querySelector('.nc-metrics');
  if (metricsEl) metricsEl.innerHTML = nodeCardMetricsHtml(m);
  card.classList.remove('flash');
  void card.offsetWidth; // reflow
  card.classList.add('flash');
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initNodesView() {
  document.getElementById('node-select').addEventListener('change', onNodeSelect);

  // Event delegation on the stable container — cards are replaced wholesale
  // on every renderNodeDashboard() call (cockpit-redesign Stage 2a, spec §6).
  document.getElementById('node-grid').addEventListener('click', (e) => {
    const card = e.target.closest('.node-card');
    if (!card) return;
    const id = parseInt(card.dataset.nodeId, 10);
    if (!isNaN(id)) selectNode(id, true);
  });
}
