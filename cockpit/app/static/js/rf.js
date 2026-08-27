// rf.js — RF Environment: full spectrum survey of the FOREIGN LoRaWAN
// traffic the gateway overhears. Always-on, passive: no start/stop — the
// gateway hears every frame in range regardless of any toggle. Fetches
// GET /api/rf-environment (own/foreign totals, a channel×SF heatmap,
// networks, foreign devices, vendors from joins, band busyness), throttled
// re-fetch on SSE 'coex' events (sse.js).
//
// cockpit-redesign Stage 2b (spec §19/§20.2): the vendor list was the
// worst offender found by actually operating the UI — 332 rows, 8885 px,
// no cap, no search. It now splits into a handful of meaningful KPI cards
// (joins > 1) and a collapsed long tail of single-join OUIs, reduced to
// just the OUI (the resolved "name" column for that tail is only ever
// "OUI <the same oui>" — showing it twice added nothing), mounted through
// the one shared list component (list.js) with its own search + sort and
// a capped, scrolling height. Foreign devices (53 rows) gets the same
// component for the same reason (spec §19.1 — it is exactly the list that
// "most needs these controls and has none").
import { apiJSON } from './api.js';
import { esc, fmtNum, fmtTime, ageFromUplinkAt, rssiClass } from './format.js';
import { mountList } from './list.js';

const RF_HEATMAP_CHANNELS = [0, 1, 2, 3, 4, 5, 6, 7]; // the 8 EU868 LoRa channels
// Fallback only, for the (currently unseen) case of an empty matrix — the
// real SF columns are always derived from the data (see deriveHeatmapSfs
// below). SF11 is listed here for historical reasons but never occurs in
// the field data (spec addendum 2026-08-26): a hardcoded 7..12 column list
// used to render one permanently-empty SF11 column on every real dataset.
const RF_HEATMAP_SFS_FALLBACK = [7, 8, 9, 10, 11, 12];

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

/** The matrix only ever contains keys for (channel, SF) pairs that
 * actually occurred (db.py groups the real rf_frame rows) — SF11, for
 * example, is real zero in the field data and simply has no `ch*_sf11` key
 * at all. Deriving the column set from the data, instead of a hardcoded
 * list, is what keeps a genuinely-unused SF from permanently occupying a
 * blank column (and would just as correctly pick up a new SF nobody has
 * hardcoded here yet). */
function deriveHeatmapSfs(matrix) {
  const sfs = new Set();
  for (const key of Object.keys(matrix)) {
    const m = /_sf(\d+)$/.exec(key);
    if (m) sfs.add(Number(m[1]));
  }
  return sfs.size ? [...sfs].sort((a, b) => a - b) : RF_HEATMAP_SFS_FALLBACK;
}

// Cell shading floor (product-owner decision) — the smallest non-zero
// value must still read as "a little", not vanish against the card. A
// real zero (see alphaForCount below) stays fully uncoloured, which is
// what actually distinguishes "none" from "the quietest cell we have".
const RF_HEATMAP_ALPHA_FLOOR = 0.15;

// The shading colour is one fixed cyan in BOTH themes, laid over the page
// background at varying opacity. That makes a single opacity threshold the
// wrong tool for choosing the text colour: in the light theme a faint cell
// is light, in the dark theme the same faint cell is dark. So the ink is
// derived from the actual composite instead — see heatmapInk().
const RF_HEATMAP_RGB = [34, 211, 238];

/** sRGB relative luminance (WCAG). */
function _luminance([r, g, b]) {
  const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

/** Current page background as [r,g,b] — the surface the cells composite over. */
function _pageBackground() {
  const m = getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g) || [];
  return m.length >= 3 ? m.slice(0, 3).map(Number) : [255, 255, 255];
}

/** log10 opacity scale, normalised over the OBSERVED range (smallest
 * non-zero value .. largest value) rather than a fixed decade count. The
 * real matrix spans a factor of ~730 (8..5838); on a linear scale that
 * puts everything below ~1000 at under 15% opacity, so 700, 200 and 8 are
 * indistinguishable. On log10 the same neighbours separate by 5-20
 * percentage points. A true zero returns 0 — no colour at all, which is
 * what distinguishes "none" from "the quietest cell we have". */
function alphaForCount(count, logMin, logMax, alphaMax) {
  if (count === 0) return 0;
  const floor = RF_HEATMAP_ALPHA_FLOOR;
  if (logMax === logMin) return alphaMax; // one distinct non-zero value — nothing to spread
  const frac = (Math.log10(count) - logMin) / (logMax - logMin);
  // The ceiling varies by theme, the floor does not: scaling the whole ramp
  // would drag the smallest value down with it (0.15 x 0.48 = 0.07) and undo
  // the very guarantee the floor exists for.
  return floor + (alphaMax - floor) * frac;
}

/** How far the shading may go, and which ink stays readable on it.
 *
 * Cyan over a LIGHT page never leaves the bright half, so dark ink holds
 * across the whole 0.15..1.0 ramp (worst case 10.3:1).
 *
 * Cyan over a DARK page is the awkward one: past roughly half opacity the
 * cell lands in the mid-luminance dead zone where *neither* dark nor light
 * ink reaches 4.5:1. Rather than pick a losing ink, the ramp is capped
 * before that zone — 0.48 keeps light ink at 5.3:1 throughout. The gradient
 * stays monotonic, just shallower, which is ordinary for a dark surface.
 * Both figures are computed from the real palette, not estimated. */
function heatmapShading(pageBg) {
  const darkPage = _luminance(pageBg) < 0.35;
  return { alphaMax: darkPage ? 0.48 : 1, inkClass: darkPage ? '' : ' is-strong' };
}

/** Channel × SF grid, cells shaded by foreign-frame count on a log10 scale
 * (a single accent color at varying opacity — flat, no gradient/glow),
 * see alphaForCount above for why. Full card width, stacked above the
 * timeline (product-owner decision, not side-by-side even on desktop) —
 * columns stretch to fill the available width instead of a fixed 24px, so
 * the per-cell frame count is actually legible instead of ~9px text. */
function buildRfHeatmapHtml(matrix) {
  const pageBg = _pageBackground();
  const { alphaMax, inkClass } = heatmapShading(pageBg);
  const sfs = deriveHeatmapSfs(matrix);
  const counts = RF_HEATMAP_CHANNELS.flatMap(
    ch => sfs.map(sf => matrix[`ch${ch}_sf${sf}`] || 0)
  );
  if (!counts.some(c => c > 0)) {
    return '<p class="hint">No foreign frames observed yet.</p>';
  }
  const positive = counts.filter(c => c > 0);
  const logMin = Math.log10(Math.min(...positive));
  const logMax = Math.log10(Math.max(...positive));

  let html = `<div class="rf-heat-grid" style="grid-template-columns:minmax(34px,auto) repeat(${sfs.length},minmax(0,1fr))">`;
  html += '<div class="rf-heat-hdr"></div>';
  for (const sf of sfs) html += `<div class="rf-heat-hdr">SF${sf}</div>`;
  for (const ch of RF_HEATMAP_CHANNELS) {
    html += `<div class="rf-heat-hdr rf-heat-rowhdr">CH${ch}</div>`;
    for (const sf of sfs) {
      const count = matrix[`ch${ch}_sf${sf}`] || 0;
      const alpha = alphaForCount(count, logMin, logMax, alphaMax);
      // Ink and ramp both come from heatmapShading() — the same opacity
      // reads light on one page background and dark on the other, so
      // neither can be a fixed constant.
      const strong = count > 0 ? inkClass : '';
      html += `<div class="rf-heat-cell${strong}" style="background:rgba(34,211,238,${alpha.toFixed(2)})" title="CH${ch} / SF${sf}: ${count} foreign frame${count === 1 ? '' : 's'}">${count || ''}</div>`;
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

function foreignRowHtml([devAddr, d]) {
  return `
    <div class="rf-dev-row">
      <span class="mono">${esc(devAddr)}</span>
      <span class="rf-dev-net">${esc(d.network || 'other')}</span>
      <span>${d.last_sf != null ? 'SF' + d.last_sf : '—'}</span>
      <span class="${rssiClass(d.last_rssi)}">${fmtNum(d.last_rssi)}&nbsp;dBm</span>
      <span class="hint">${ageFromUplinkAt(d.last_seen)}</span>
    </div>`;
}

const FOREIGN_FILTERS = [
  { key: 'all', test: () => true },
  { key: 'ttn', test: ([, d]) => d.network === 'The Things Network' },
  { key: 'private', test: ([, d]) => d.network === 'private/experimental' },
  { key: 'other', test: ([, d]) => !d.network || (d.network !== 'The Things Network' && d.network !== 'private/experimental') },
];
const FOREIGN_SORTS = [
  { label: 'Most recent', cmp: (a, b) => new Date(b[1].last_seen || 0) - new Date(a[1].last_seen || 0) },
  { label: 'Most frames', cmp: (a, b) => (b[1].frames || 0) - (a[1].frames || 0) },
  { label: 'Strongest signal', cmp: (a, b) => (b[1].last_rssi || -999) - (a[1].last_rssi || -999) },
];

let _foreignList = null; // mountList() handle — created once, fed via setItems() so a live
                          // refresh never wipes out the operator's in-progress search/sort.

function renderRfDevices(devices) {
  const countEl = document.getElementById('rf-device-count');
  const entries = Object.entries(devices);
  if (countEl) countEl.textContent = entries.length ? `(${entries.length})` : '';

  if (!_foreignList) {
    const root = document.getElementById('lb-foreign');
    if (!root) return;
    _foreignList = mountList({
      root,
      items: entries,
      renderRow: foreignRowHtml,
      searchFields: ([addr, d]) => `${addr} ${d.network || ''}`,
      filters: FOREIGN_FILTERS,
      sorts: FOREIGN_SORTS,
      emptyText: 'No foreign devices observed yet.',
    });
  } else {
    _foreignList.setItems(entries);
  }
}

let _vendorTailList = null; // mountList() handle — created once on first data, then fed via setItems()

const VENDOR_TAIL_SORTS = [
  { label: 'OUI A→Z', cmp: (a, b) => a.oui.localeCompare(b.oui) },
  { label: 'OUI Z→A', cmp: (a, b) => b.oui.localeCompare(a.oui) },
];

function vendorHighlightHtml([, v]) {
  return `
    <div class="vcard">
      <div class="stat-num">${v.joins.toLocaleString('en-US')}</div>
      <div class="stat-label">joins</div>
      <div class="vcard-name" title="${esc(v.name)}">${esc(v.name)}</div>
    </div>`;
}

function vendorTailRowHtml(v) {
  return `<div class="vtail-cell mono">${esc(v.oui)}</div>`;
}

/** Splits joins-from-vendors into a handful of meaningful KPI cards
 * (> 1 join) and a collapsed, searchable/sortable long tail (exactly 1
 * join each, reduced to just the OUI — spec §19.1/§20.2). */
function renderRfVendors(vendors) {
  const countEl = document.getElementById('vendor-count');
  const entries = Object.entries(vendors);
  if (countEl) countEl.textContent = entries.length ? `(${entries.length})` : '';

  const highlights = entries.filter(([, v]) => v.joins > 1).sort((a, b) => b[1].joins - a[1].joins);
  const tail = entries.filter(([, v]) => v.joins === 1).map(([oui]) => ({ oui }));

  const highlightsEl = document.getElementById('vendor-highlights');
  if (highlightsEl) {
    highlightsEl.innerHTML = highlights.length
      ? highlights.map(vendorHighlightHtml).join('')
      : '<p class="hint">No joins observed yet.</p>';
  }

  const toggle = document.getElementById('vendor-tail-toggle');
  const tailWrap = document.getElementById('vendor-tail');
  const hint = document.getElementById('vendor-tail-hint');
  if (toggle) toggle.classList.toggle('is-hidden', !tail.length);
  if (!tail.length) { if (tailWrap) tailWrap.classList.add('is-hidden'); return; }

  if (toggle && !toggle.dataset.labelled) {
    toggle.textContent = `Show ${tail.length} more · 1 join each`;
    toggle.dataset.labelled = '1';
  }
  if (hint) hint.textContent = `${tail.length} unresolved · 1 join each`;

  if (!_vendorTailList) {
    const root = document.getElementById('lb-vendor-tail');
    if (root) {
      _vendorTailList = mountList({
        root,
        items: tail,
        renderRow: vendorTailRowHtml,
        searchFields: (v) => v.oui,
        sorts: VENDOR_TAIL_SORTS,
        emptyText: 'No matching OUIs.',
      });
    }
  } else {
    _vendorTailList.setItems(tail);
  }
}

/** Vertical column chart shared by the SF and RSSI distributions —
 * cockpit-redesign Stage 2b addendum (product-owner note, 2026-08-26):
 * both are ORDERED categories, so a column shape reads as a distribution
 * at a glance instead of a stack of rows.
 *
 * The real data has a brutal range (RSSI: 48,617 vs. 2 — a 24,000:1
 * ratio). On a linear scale (kept deliberately linear — a log scale would
 * need axis labels there is no room for on a phone) the smallest non-zero
 * bucket would round to a sub-pixel height and read as "nothing", exactly
 * like the genuine zero (SF11 = 0) next to it. So:
 *   - every value > 0 gets a floor of COL_MIN_PX so "very little" stays
 *     visually distinct from "none" (never just a CSS min-height on a 0%
 *     bar — computed in JS against the same px scale as every other bar,
 *     so a 3 px floor is still 3 px next to a 96 px column, not stretched)
 *   - a genuine zero renders NO bar at all, only a baseline tick + the
 *     label "0" — it must not look like "almost zero"
 *   - the exact number sits above every column as text, not only in a
 *     title tooltip (spec §20.2 — a tooltip is not a touch answer, and
 *     the RSSI bucket of 2 is otherwise unreadable at this scale)
 * Uses <div>, not <span>, for the bar itself, with the height computed in
 * JS as an absolute px value (not a %) — the exact bug class the product
 * owner flagged from the design-variant prototypes: an inline element's
 * width/height is ignored by the box model regardless of a correct
 * `style="width:…"`, unless it is block-level. */
const COL_CHART_PLOT_PX = 84;
const COL_CHART_MIN_PX = 3;

function columnChartHtml(entries) {
  const max = Math.max(1, ...entries.map(([, c]) => c));
  return `<div class="col-chart">` + entries.map(([label, c]) => {
    const isZero = !c;
    const heightPx = isZero ? 0 : Math.max(COL_CHART_MIN_PX, Math.round((c / max) * COL_CHART_PLOT_PX));
    const bar = isZero
      ? ''
      : `<div class="col-bar-fill" style="height:${heightPx}px"></div>`;
    return `
      <div class="col-item${isZero ? ' col-zero' : ''}">
        <span class="col-value">${c.toLocaleString('en-US')}</span>
        <div class="col-bar-track">${bar}</div>
        <span class="col-label">${esc(label)}</span>
      </div>`;
  }).join('') + `</div>`;
}

function renderRfSfDistribution(sfDist) {
  const el = document.getElementById('rf-sf-dist');
  if (!el) return;
  const entries = Object.entries(sfDist).map(([sf, c]) => [`SF${sf}`, c]);
  const total = entries.reduce((a, [, c]) => a + c, 0);
  if (!total) { el.innerHTML = '<p class="hint">No data yet.</p>'; return; }
  el.innerHTML = columnChartHtml(entries);
}

/** Backend labels carry their own " dBm" suffix ("≥ -80 dBm", spec
 * db.py:1430-1433) — dropped here since the column is too narrow for it
 * and the section title already states the unit; shortened, not
 * shortened-and-vaguer (spec addendum point 5: "kürze die Beschriftung,
 * nicht die Lesbarkeit"). */
function shortRssiLabel(label) {
  return label.replace(/\s*dBm$/, '');
}

function renderRfRssiDistribution(buckets) {
  const el = document.getElementById('rf-rssi-dist');
  if (!el) return;
  const total = buckets.reduce((a, b) => a + b.count, 0);
  if (!total) { el.innerHTML = '<p class="hint">No data yet.</p>'; return; }
  el.innerHTML = columnChartHtml(buckets.map(b => [shortRssiLabel(b.label), b.count]));
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

// ---------------------------------------------------------------------------
// Wiring (called once from app.js) — the vendor long-tail disclosure
// (cockpit-redesign Stage 2b, spec §19/§20.2).
// ---------------------------------------------------------------------------

export function initRfView() {
  // The heatmap derives its text colour from the composite of each cell's
  // shading over the page background (see heatmapInk). Custom properties
  // cannot express that, so switching theme has to rebuild those cells —
  // otherwise the ink stays chosen for the previous background and half the
  // grid drops below 4.5:1 without anything looking obviously broken.
  document.addEventListener('cockpit:themechange', () => { loadRfEnvironment(); });

  const toggle = document.getElementById('vendor-tail-toggle');
  const tailWrap = document.getElementById('vendor-tail');
  if (!toggle || !tailWrap) return;
  toggle.addEventListener('click', () => {
    const willShow = tailWrap.classList.contains('is-hidden');
    tailWrap.classList.toggle('is-hidden');
    toggle.setAttribute('aria-expanded', String(willShow));
  });
}
