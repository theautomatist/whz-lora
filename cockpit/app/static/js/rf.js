// rf.js — RF Environment: full spectrum survey of the FOREIGN LoRaWAN
// traffic the gateway overhears. Always-on, passive: no start/stop — the
// gateway hears every frame in range regardless of any toggle. Fetches
// GET /api/rf-environment (own/foreign totals, a channel×SF heatmap,
// networks, foreign devices, vendors from joins, band busyness), throttled
// re-fetch on SSE 'coex' events (sse.js). Unchanged behaviour from the old
// app.js — this panel has no inline handlers to remove, only rendering.
import { apiJSON } from './api.js';
import { esc, fmtNum, fmtTime, ageFromUplinkAt, rssiClass } from './format.js';

const RF_HEATMAP_CHANNELS = [0, 1, 2, 3, 4, 5, 6, 7]; // the 8 EU868 LoRa channels
const RF_HEATMAP_SFS = [7, 8, 9, 10, 11, 12];

let _rfEnvLoading = false;
let _rfEnvPending = false;

/** Fetch + render the full survey. Coalesces overlapping calls (a pending
 * fetch already in flight just gets one more run queued after it, not a
 * pile of parallel requests). */
export async function loadRfEnvironment() {
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
export function scheduleRfEnvironmentRefresh() {
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

/** "HH:MM:SS" from a stored ts, using the same raw-substring approach as
 * fmtTime — no local-timezone conversion anywhere else in this app. */
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
