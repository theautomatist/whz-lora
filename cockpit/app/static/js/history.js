// history.js — F-0007 top-level History tab: a browsable/filterable-by-
// device list of every run (GET /api/runs, no node_id), and a
// left(device)/right(gateway) run detail. A read/browse view — reuses
// run-detail.js's builders unchanged. Unchanged behaviour from the old
// app.js; inline onclick/onchange replaced with addEventListener and event
// delegation (cockpit-redesign Stage 2a, spec §6).
import { apiJSON } from './api.js';
import { esc, fmtDateTime, histStatusLabel, pdrClass } from './format.js';
import { placeInfoHtml, photoThumbsHtml, mapThumbnailHtml, renderPdrSfBlock, buildRunChartHtml } from './run-detail.js';

let _historyRuns = [];

export async function loadHistoryList() {
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
  const sortSel = document.getElementById('hist-sort');
  const sorted = sortHistoryRuns(runs, sortSel ? sortSel.value : 'start_desc');
  body.innerHTML = sorted.map(historyRowHtml).join('');
}

/** field: 'start'|'end' from a "<field>_<dir>" sort key; dir: 'desc'
 * (newest first, the default) or 'asc' (oldest first). A still-running
 * run (no ended_at) sorts as "now" when sorting by End — a single,
 * consistent rule that puts it first newest-first, last oldest-first,
 * without a special case. Array.prototype.sort is stable (ES2019), so
 * equal timestamps keep their existing relative order. */
function sortHistoryRuns(runs, sortKey) {
  const [field, dir] = sortKey.split('_');
  const timeOf = r => {
    if (field === 'end') return r.ended_at ? new Date(r.ended_at).getTime() : Date.now();
    return new Date(r.started_at).getTime();
  };
  const sorted = runs.slice();
  sorted.sort((a, b) => (dir === 'asc' ? timeOf(a) - timeOf(b) : timeOf(b) - timeOf(a)));
  return sorted;
}

/** One row: device · location · Started/Ended (or a "Running" badge in
 * place of the end time) · status · packets · PDR summary. Tap ->
 * openHistoryDetail() (event delegation, see initHistoryView below). */
function historyRowHtml(r) {
  const o = r.overall || {};
  const pdrKnown = o.expected != null && o.expected > 0;
  const pdrText = pdrKnown ? `${Math.round(o.pdr * 100)}% PDR` : '—';
  const pdrCls = pdrKnown ? pdrClass(o.pdr) : '';
  const deviceName = r.device ? r.device.name : '—';
  const endedHtml = r.ended_at
    ? `<span class="hist-row-time-lbl">Ended</span>${fmtDateTime(r.ended_at)}`
    : `<span class="hist-badge hist-running">Running</span>`;
  return `
    <div class="hist-row" data-run-id="${r.run_id}">
      <div class="hist-row-main">
        <span class="hist-row-device">${esc(deviceName)}</span>
        <span class="hist-row-loc">${esc(r.floor || '—')} · ${esc(r.room || '—')}</span>
      </div>
      <div class="hist-row-times">
        <span class="hist-row-time"><span class="hist-row-time-lbl">Started</span>${fmtDateTime(r.started_at)}</span>
        <span class="hist-row-time">${endedHtml}</span>
      </div>
      <div class="hist-row-meta">
        <span class="hist-badge hist-${esc(r.status)}">${histStatusLabel(r.status)}</span>
        <span>${r.packets} pkts</span>
        <span class="hist-row-pdr ${pdrCls}">${pdrText}</span>
      </div>
    </div>`;
}

function openHistoryDetail(runId) {
  const listView = document.getElementById('history-list-view');
  const detailView = document.getElementById('history-detail-view');
  if (listView) listView.classList.add('is-hidden');
  if (detailView) detailView.classList.remove('is-hidden');
  loadHistoryDetail(runId);
}

export function closeHistoryDetail() {
  const listView = document.getElementById('history-list-view');
  const detailView = document.getElementById('history-detail-view');
  if (detailView) detailView.classList.add('is-hidden');
  if (listView) listView.classList.remove('is-hidden');
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

function renderHistoryDetail(detail, stats, series) {
  const run = detail.run;
  const device = detail.device;
  const devicePlacement = detail.device_placement;
  const gatewayPlacement = detail.gateway_placement;

  document.getElementById('hist-detail-title').textContent =
    device ? `${device.name} — ${fmtDateTime(run.started_at)}` : `Run #${run.id}`;

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
    <div><strong>Started:</strong> ${fmtDateTime(run.started_at)}</div>
    <div><strong>Ended:</strong> ${run.ended_at ? fmtDateTime(run.ended_at) : '—'}</div>
    <div><strong>Packets:</strong> ${run.packets}</div>`;
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initHistoryView() {
  document.getElementById('hist-device-filter').addEventListener('change', renderHistoryList);
  document.getElementById('hist-sort').addEventListener('change', renderHistoryList);
  document.getElementById('hist-detail-back-btn').addEventListener('click', closeHistoryDetail);

  // Dynamically rendered rows (historyRowHtml) — event delegation on the
  // stable container instead of a handler per row (cockpit-redesign
  // Stage 2a, spec §6).
  document.getElementById('history-list-body').addEventListener('click', (e) => {
    const row = e.target.closest('.hist-row');
    if (!row) return;
    const runId = parseInt(row.dataset.runId, 10);
    if (!isNaN(runId)) openHistoryDetail(runId);
  });
}
