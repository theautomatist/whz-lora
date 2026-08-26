// events.js — cockpit-redesign Stage 1 Event Log (spec §4/§12/§14/§16),
// extended in Stage 2b (spec §12/§20.2) with a plain-text search over the
// currently loaded rows and a two-line row layout. Keyset "Load more"
// pagination against GET /api/events/log, a permanently visible type +
// device chip row, and two distinct empty states (genuinely empty vs.
// filtered empty — spec §12). New events arrive via the existing SSE
// full-refresh convention (§12) — no lean per-event markers.
//
// Search is client-side over whatever page(s) have been loaded so far —
// documented simplification (KISS), same reasoning as list.js: a
// cross-page server search endpoint does not exist and this stage does not
// add one.
import { state } from './state.js';
import { apiJSON } from './api.js';
import { esc, fmtDateTime } from './format.js';

const EVENT_TYPE_LABELS = {
  join:              'Join',
  run_started:       'Run started',
  run_stopped:       'Run stopped',
  relocated:         'Relocated',
  gateway_moved:     'Gateway moved',
  downlink_acked:    'Downlink ACK',
  downlink_nacked:   'Downlink NACK',
  segment_changed:   'Segment changed',
  first_uplink:      'First uplink',
};

let _eventsRows = [];
let _eventsCursor = null;
let _eventsHasMore = false;
let _eventsTypeFilter = '';
let _eventsNodeFilter = '';
let _eventsSearch = '';

/** Rebuilds the device chip row from the already-loaded node list (no
 * extra request) — called from nodes.js's loadNodes() so a newly
 * registered device shows up as a filter option. The active selection
 * survives a rebuild. */
export function populateEventDeviceChips() {
  const row = document.getElementById('evt-device-chips');
  if (!row || !state.nodes) return;
  const current = _eventsNodeFilter;
  const allChip = `<button type="button" class="chip${current === '' ? ' active' : ''}" data-evt-node-id="">All devices</button>`;
  const deviceChips = state.nodes.map(n => {
    const active = String(n.id) === current ? ' active' : '';
    const label = (n.kind === 'gateway' ? 'Gateway: ' : '') + esc(n.name);
    return `<button type="button" class="chip${active}" data-evt-node-id="${n.id}">${label}</button>`;
  });
  row.innerHTML = [allChip, ...deviceChips].join('');
}

/** *reset*=true starts over from page 1 (a fresh filter, or the SSE
 * full-refresh trigger); *reset*=false appends the next "Load more" page
 * via the current keyset cursor. */
export async function loadEventsLog(reset) {
  const body = document.getElementById('events-log-body');
  if (!body) return;
  if (reset) {
    _eventsRows = [];
    _eventsCursor = null;
    body.innerHTML = '<p class="hint">Loading…</p>';
  }
  const params = new URLSearchParams();
  if (_eventsCursor != null) params.set('cursor', _eventsCursor);
  if (_eventsTypeFilter) params.set('type', _eventsTypeFilter);
  if (_eventsNodeFilter) params.set('node_id', _eventsNodeFilter);
  try {
    const data = await apiJSON('/api/events/log?' + params.toString());
    _eventsRows = _eventsRows.concat(data.events || []);
    _eventsCursor = data.next_cursor;
    _eventsHasMore = !!data.has_more;
    renderEventsLog();
  } catch (e) {
    body.innerHTML = `<p class="hint">Error: ${esc(e.message)}</p>`;
  }
}

/** If the Events tab is the one currently on screen, pull a fresh first
 * page — the existing SSE channel is a full-refresh trigger (spec §12),
 * not a source of lean per-event markers. A no-op while another tab is
 * showing; switching to Events always loads fresh anyway (nav.js). */
export function refreshEventsLogIfActive() {
  if (state.currentView === 'events') loadEventsLog(true);
}

/** Rows actually on screen after the client-side search on top of the
 * server-filtered/paginated _eventsRows. */
function visibleRows() {
  if (!_eventsSearch) return _eventsRows;
  const q = _eventsSearch.toLowerCase();
  return _eventsRows.filter(ev => {
    const label = EVENT_TYPE_LABELS[ev.type] || ev.type;
    const hay = `${ev.node_name || ''} ${label} ${eventReasonText(ev)}`.toLowerCase();
    return hay.includes(q);
  });
}

function renderEventsLog() {
  const body = document.getElementById('events-log-body');
  if (!body) return;
  const rows = visibleRows();
  const filtered = Boolean(_eventsTypeFilter || _eventsNodeFilter || _eventsSearch);

  if (!rows.length) {
    // Two distinct empty states (spec §12) — a filter must never look like
    // a bug ("is the log broken?") or vice versa.
    body.innerHTML = filtered
      ? '<p class="hint">No events match this filter. <button type="button" class="btn-g" id="evt-reset-filters">Reset</button></p>'
      : '<p class="hint">No events recorded yet.</p>';
    const resetBtn = document.getElementById('evt-reset-filters');
    if (resetBtn) resetBtn.addEventListener('click', resetEventFilters);
  } else {
    // "BACKFILL on every row" defect (spec §20.2) — when the visible page
    // is entirely reconstructed, one notice above the list is more honest
    // than repeating the badge on every single row; mark the exception
    // instead of the rule.
    const allBackfill = rows.every(r => r.source === 'backfill');
    const banner = allBackfill
      ? '<p class="hint evt-backfill-banner">All events below were reconstructed from run history at migration time, not recorded live.</p>'
      : '';
    body.innerHTML = banner + rows.map(ev => eventRowHtml(ev, !allBackfill)).join('');
  }
  const loadMoreRow = document.getElementById('evt-load-more-row');
  if (loadMoreRow) loadMoreRow.classList.toggle('is-hidden', !_eventsHasMore);
}

function resetEventFilters() {
  _eventsTypeFilter = '';
  _eventsNodeFilter = '';
  _eventsSearch = '';
  const searchInput = document.getElementById('evt-search');
  if (searchInput) searchInput.value = '';
  const typeRow = document.getElementById('evt-type-chips');
  const deviceRow = document.getElementById('evt-device-chips');
  if (typeRow) {
    for (const c of typeRow.querySelectorAll('.chip')) c.classList.toggle('active', !c.dataset.evtType);
  }
  if (deviceRow) {
    for (const c of deviceRow.querySelectorAll('.chip')) c.classList.toggle('active', !c.dataset.evtNodeId);
  }
  loadEventsLog(true);
}

/** Plain-language "reason" text per event type, built from its small
 * payload (never a second request). */
function eventReasonText(ev) {
  const p = ev.payload || {};
  switch (ev.type) {
    case 'join':
      return p.dev_addr ? `DevAddr ${p.dev_addr}` : 'joined the network';
    case 'run_started':
      return p.sweep ? 'sweep started' : 'run started';
    case 'run_stopped': {
      const where = p.reason ? p.reason : (p.status || 'stopped');
      return where;
    }
    case 'relocated':
    case 'gateway_moved': {
      const place = [p.floor, p.room].filter(Boolean).join(' / ');
      return place ? `moved to ${place}` : 'moved';
    }
    case 'downlink_acked':
      return 'acknowledged';
    case 'downlink_nacked':
      return 'not acknowledged';
    case 'segment_changed':
      return p.sf != null ? `now SF${p.sf}` : `segment ${p.segment_index}`;
    case 'first_uplink':
      return 'first packet received';
    default:
      return '';
  }
}

/** Two fixed-height lines instead of four squeezed columns (spec §20.2):
 * device + time on line 1, type + reason on line 2. `nowrap` + a CSS grid
 * with fixed track sizes make the height structural, not incidental (spec
 * §20 — "a badge cannot make one row taller than the next"); a truncated
 * value is reachable by tapping (spec §20.2 — a tooltip alone is a
 * desktop-only answer) via the built-in `title` attribute AND a tap-to-
 * expand toggle, since `title` never fires on touch. */
function eventRowHtml(ev, showBackfillTag) {
  const label = EVENT_TYPE_LABELS[ev.type] || ev.type;
  const device = ev.node_name ? esc(ev.node_name) : '—';
  const reasonText = eventReasonText(ev);
  const line2 = reasonText ? `${label} · ${reasonText}` : label;
  const full = `${ev.node_name || '—'} — ${line2}`;
  const backfillBadge = (showBackfillTag && ev.source === 'backfill')
    ? '<span class="evt-badge-backfill" title="Reconstructed from run history — not live measurement evidence">reconstructed</span>'
    : '';
  return `
    <button type="button" class="evt-row" data-full="${esc(full)}" title="${esc(full)}">
      <span class="evt-row-l1">
        <span class="evt-device">${device}</span>
        <span class="evt-time">${fmtDateTime(ev.ts)}</span>
      </span>
      <span class="evt-row-l2">
        <span class="evt-type-reason"><span class="evt-type">${esc(label)}</span> <span class="evt-reason">${reasonText ? '· ' + esc(reasonText) : ''}</span></span>
        ${backfillBadge}
      </span>
    </button>`;
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js) — the "Events" tab button itself is
// wired in nav.js alongside its sibling tabs.
// ---------------------------------------------------------------------------

export function initEventsView() {
  const typeRow = document.getElementById('evt-type-chips');
  if (typeRow) {
    typeRow.addEventListener('click', (e) => {
      const btn = e.target.closest('.chip');
      if (!btn) return;
      _eventsTypeFilter = btn.dataset.evtType || '';
      for (const c of typeRow.querySelectorAll('.chip')) c.classList.toggle('active', c === btn);
      loadEventsLog(true);
    });
  }

  const deviceRow = document.getElementById('evt-device-chips');
  if (deviceRow) {
    deviceRow.addEventListener('click', (e) => {
      const btn = e.target.closest('.chip');
      if (!btn) return;
      _eventsNodeFilter = btn.dataset.evtNodeId || '';
      for (const c of deviceRow.querySelectorAll('.chip')) c.classList.toggle('active', c === btn);
      loadEventsLog(true);
    });
  }

  const searchInput = document.getElementById('evt-search');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      _eventsSearch = e.target.value;
      renderEventsLog();
    });
  }

  // Tap-to-reveal for a truncated device/reason on a row — `title` never
  // fires on touch (spec §20.2), so a tap toggles an expanded class that
  // CSS turns into `white-space: normal` for that one row.
  const body = document.getElementById('events-log-body');
  if (body) {
    body.addEventListener('click', (e) => {
      const row = e.target.closest('.evt-row');
      if (row) row.classList.toggle('evt-row-expanded');
    });
  }

  const loadMoreBtn = document.getElementById('evt-load-more');
  if (loadMoreBtn) loadMoreBtn.addEventListener('click', () => loadEventsLog(false));
}
