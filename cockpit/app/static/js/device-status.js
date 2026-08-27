// device-status.js — the "Device status" block in the Selected-device panel
// ("is the configuration working?", Trust & visibility) and the 1 s ticker
// that keeps its "Xs ago" text and every Overview card's meta line moving
// with no re-fetch. Unchanged behaviour from the old app.js.
//
// LoRaWAN Class A only delivers a queued downlink right after the device's
// own next uplink — a silent device means nothing has reached it yet. This
// block makes that visible: last packet age, measured vs. target send
// interval, and whether a config downlink is still queued or already sent.
import { state } from './state.js';
import { apiJSON } from './api.js';
import { toast, fmtAgo, fmtDuration, fmtInterval, ageFromUplinkAt, metaLineText } from './format.js';

/** Target interval (minutes) = the active run's interval_minutes, else the
 * 5-min default (matches the default sweep / Vicki keep-alive command). */
function targetIntervalMinutes(node) {
  const run = node && node.active_run;
  return (run && run.interval_minutes) ? run.interval_minutes : 5;
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

let _devConfigStatus = null; // { nodeId, last_uplink_at, interval_seconds, queued, last_downlink_at }

/** Re-render the block from the currently cached devMetrics/_devConfigStatus
 * — cheap, called every second by the signal-age ticker for smooth "Xs ago"
 * text, with no network call. */
export function renderDeviceStatusBlock() {
  const block = document.getElementById('dev-status-block');
  if (!block) return;
  const node = state.nodesById[state.selectedNodeId];
  if (!node || node.kind !== 'device') { block.classList.add('is-hidden'); return; }

  const m = state.devMetrics[node.eui] || {};
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
export async function refreshDeviceStatus() {
  const node = state.nodesById[state.selectedNodeId];
  if (!node || node.kind !== 'device') { renderDeviceStatusBlock(); return; }
  const nodeId = node.id;
  try {
    const data = await apiJSON(`/api/device/${nodeId}/config-status`);
    if (state.selectedNodeId !== nodeId) return; // selection changed while awaiting
    _devConfigStatus = Object.assign({ nodeId }, data);
  } catch (e) {
    if (state.selectedNodeId !== nodeId) return;
    _devConfigStatus = null;
  }
  renderDeviceStatusBlock();
}

async function setDeviceInterval5() {
  const node = state.nodesById[state.selectedNodeId];
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
  const node = state.nodesById[state.selectedNodeId];
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
// Signal-age ticker — updates every visible Overview card's "Xs ago" meta
// line and this block's age text every second, no re-render/re-fetch.
// ---------------------------------------------------------------------------

let _signalAgeTimer = null;

export function startSignalAgeTicker() {
  if (_signalAgeTimer) return;
  _signalAgeTimer = setInterval(() => {
    for (const n of state.nodes) {
      if (n.kind !== 'device') continue;
      const m = state.devMetrics[n.eui];
      const el = document.getElementById(`nc-meta-${n.id}`);
      if (el && m) el.textContent = metaLineText(m);
    }
    renderDeviceStatusBlock(); // cheap re-render of "Xs ago" text, no fetch
  }, 1000);
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initDeviceStatus() {
  document.getElementById('btn-set-interval-5').addEventListener('click', setDeviceInterval5);
  document.getElementById('btn-wake-device').addEventListener('click', wakeDeviceTest);
}
