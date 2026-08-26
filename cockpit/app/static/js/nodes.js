// nodes.js — GET /api/nodes, the node picker inside the device-detail
// topbar, and — cockpit-redesign Stage 2b (spec §7/§20) — the Devices
// landing list: one card per device/gateway, sorted by computed
// need-for-action rather than alphabetically or by raw run state. The
// cards' click is event delegation on the stable #device-list container
// (cockpit-redesign Stage 2a, spec §6).
import { state } from './state.js';
import { apiJSON } from './api.js';
import { esc, toast } from './format.js';
import { checkCelebration } from './run.js';
import { computeSeverity, sortByNeed } from './severity.js';
import { renderHero } from './hero.js';
import { renderSelectedNode } from './selected-panel.js';
import { refreshDeviceStatus } from './device-status.js';
import { populateEventDeviceChips } from './events.js';

export async function loadNodes() {
  try {
    const [nodesData, runsData] = await Promise.all([
      apiJSON('/api/nodes'),
      apiJSON('/api/runs').catch(() => ({ runs: [] })), // best-effort — a stale severity read beats a broken Devices tab
    ]);
    state.nodes = nodesData.nodes || [];
    state.nodesById = {};
    for (const n of state.nodes) state.nodesById[n.id] = n;

    state.runsByEui = {};
    for (const r of runsData.runs || []) {
      if (!r.device || !r.device.eui) continue;
      (state.runsByEui[r.device.eui] = state.runsByEui[r.device.eui] || []).push(r);
    }

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
  if (!sel) return;
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

/** Select a node and show its detail screen (cockpit-redesign Stage 2b —
 * the device detail is now a level-2 screen, opened from a Devices card or
 * the in-detail picker; see nav.js's openDeviceDetail()). */
export function selectNode(id) {
  state.selectedNodeId = id;
  const sel = document.getElementById('node-select');
  if (sel) sel.value = String(id);
  renderSelectedNode();
  refreshDeviceStatus(); // fire-and-forget — Device status (Trust & visibility)
}

// ---------------------------------------------------------------------------
// Devices landing list — cockpit-redesign Stage 2b (spec §7/§9/§20)
// ---------------------------------------------------------------------------

export function renderNodeDashboard() {
  const list = document.getElementById('device-list');
  if (!list) return;
  if (!state.nodes.length) {
    list.innerHTML = '<div class="hint" style="padding:20px 0;text-align:center">No devices found.</div>';
    return;
  }

  const entries = state.nodes.map(n => Object.assign({ node: n }, computeSeverity(n, state.runsByEui)));
  const sorted = sortByNeed(entries);

  list.innerHTML = sorted.map(dcardHtml).join('');

  for (const n of state.nodes) checkCelebration(n);

  const badge = document.getElementById('tab-devices-badge');
  if (badge) {
    const attn = entries.filter(e => e.severity === 'red' || e.severity === 'amber').length;
    badge.classList.toggle('is-hidden', attn === 0);
    badge.textContent = attn > 0 ? String(attn) : '';
  }
}

function criticalFlagText(node, reason) {
  if (reason.includes('never measured')) return 'Never measured — go here first';
  if (reason.includes('0 packets')) return 'Zero packets — check the device now';
  return 'Needs attention now';
}

function dcardHtml(entry) {
  const { node: n, severity, reason, meta } = entry;
  const kindLabel = n.kind === 'gateway' ? 'Gateway' : 'Device';

  if (severity === 'red') {
    return `
      <button class="dcard dcard-critical" id="nc-${n.id}" data-node-id="${n.id}">
        <div class="dcard-crit-row1">
          <span class="dcard-crit-icon" aria-hidden="true">!</span>
          <span class="dcard-name">${esc(n.name)}</span>
          <span class="dcard-chevron" aria-hidden="true">&rsaquo;</span>
        </div>
        <p class="dcard-crit-reason">${esc(reason)}</p>
        ${meta ? `<div class="dcard-meta">${esc(meta)}</div>` : ''}
        <span class="dcard-crit-flag">${esc(criticalFlagText(n, reason))}</span>
      </button>`;
  }

  return `
    <button class="dcard sev-${severity}" id="nc-${n.id}" data-node-id="${n.id}">
      <div class="dcard-head">
        <span class="dcard-name">${esc(n.name)}</span>
        <span class="dcard-kind">${kindLabel}</span>
      </div>
      <p class="dcard-statement">${esc(reason)}</p>
      <div class="dcard-meta">${esc(meta)}</div>
      <span class="dcard-chevron" aria-hidden="true">&rsaquo;</span>
    </button>`;
}

// updateNodeCardMetrics() was Stage-2a's live RSSI/SNR/SF refresh on the
// Overview card — cockpit-redesign Stage 2b (spec §10) removes that triple
// from the device card (PDR-per-SF in the detail screen is the metric that
// actually matters). sse.js's 'uplink' handler still calls this on every
// packet; kept as a harmless no-op (no '.nc-metrics' element exists on the
// new cards) rather than touching sse.js for a call site that already
// degrades safely.
export function updateNodeCardMetrics(eui) {
  const node = state.nodes.find(n => n.eui === eui);
  if (!node) return;
  const card = document.getElementById(`nc-${node.id}`);
  if (!card) return;
  const metricsEl = card.querySelector('.nc-metrics');
  if (!metricsEl) return;
  card.classList.remove('flash');
  void card.offsetWidth; // reflow
  card.classList.add('flash');
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initNodesView() {
  const sel = document.getElementById('node-select');
  if (sel) sel.addEventListener('change', onNodeSelect);

  // Event delegation on the stable container — cards are replaced wholesale
  // on every renderNodeDashboard() call (cockpit-redesign Stage 2a, spec §6).
  document.getElementById('device-list').addEventListener('click', (e) => {
    const card = e.target.closest('.dcard');
    if (!card) return;
    const id = parseInt(card.dataset.nodeId, 10);
    if (!isNaN(id)) {
      selectNode(id);
      document.dispatchEvent(new CustomEvent('cockpit:open-detail', { detail: { nodeId: id } }));
    }
  });
}
