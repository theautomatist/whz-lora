// run-detail.js — rendering helpers for "what a run/placement looked like":
// the RSSI/SNR chart, the PDR-per-SF grid, and the location/photo block.
// Shared verbatim between the Live "Selected device / gateway" panel
// (selected-panel.js) and the top-level History detail view (history.js) —
// pulled out precisely because both call the exact same builders today.
// Pure w.r.t. the DOM except where noted; unchanged behaviour from the old
// app.js.
import { esc, fmtNum, rssiClass, snrClass, pdrClass } from './format.js';

// ---------------------------------------------------------------------------
// Location + photos
// ---------------------------------------------------------------------------

/** Location block markup — floor/room/description/note[/antenna]. */
export function placeInfoHtml(p, opts = {}) {
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

/** Larger photo thumbnails (not the small Overview-card photoStripHtml in
 * nodes.js) — "your collection" (endowment). */
export function photoThumbsHtml(photoIds) {
  if (!photoIds || !photoIds.length) return '';
  return photoIds.map(id => `<div class="pthumb view"><img src="/api/photo/${id}" alt="Photo" loading="lazy"></div>`).join('');
}

/** F-0008 — small read-only floorplan thumbnail with one marker, showing
 * where a placement stood at the time (frozen map_x/map_y + the floorplan
 * it's relative to). '' when the placement has no map position — nothing
 * to show, the caller's container just stays empty. */
export function mapThumbnailHtml(placement, isGateway) {
  if (!placement || !placement.floorplan || placement.map_x == null || placement.map_y == null) return '';
  return `
    <div class="map-thumb">
      <img src="${esc(placement.floorplan.image_url)}" alt="Floor plan" loading="lazy">
      <div class="map-marker-sm${isGateway ? ' gateway' : ''}"
           style="left:${(placement.map_x * 100).toFixed(2)}%;top:${(placement.map_y * 100).toFixed(2)}%"></div>
    </div>`;
}

// ---------------------------------------------------------------------------
// PDR per SF — HEADLINE: delivery reliability per SF is the coverage metric
// that actually matters (RSSI barely changes with SF, PDR does).
// ---------------------------------------------------------------------------

/** Renders into #pdr-sf-grid/#pdr-sf-overall/#pdr-sf-hint by default (the
 * Selected-device panel); pass *ids* ({grid,overall,hint}) to target a
 * different set of elements — the History detail view reuses this same
 * builder for its own #hist-pdr-sf-* elements. */
export function renderPdrSfBlock(data, ids = {}) {
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

// ---------------------------------------------------------------------------
// RSSI/SNR-over-time chart — hand-rolled inline SVG, no chart library/CDN.
// SF-stage colors mirror style.css's --sfN-color tokens as literal hex
// (inline SVG stroke/fill attributes don't reliably resolve CSS custom
// properties on every mobile browser).
// ---------------------------------------------------------------------------

const RUN_CHART_SF_COLORS = {
  7:  '#22d3ee', // mirrors style.css --sf7-color
  9:  '#fb923c', // mirrors style.css --sf9-color
  12: '#6366f1', // mirrors style.css --sf12-color
};
const RUN_CHART_DEFAULT_COLOR = '#8593a6'; // mirrors style.css --adr-color / --muted

/** Build the inline-SVG chart + legend markup for one run's series response
 * (GET /api/run/{id}/series). Pure w.r.t. the DOM — returns an HTML string. */
export function buildRunChartHtml(data) {
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
