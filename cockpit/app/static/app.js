/* app.js — Field-Test Cockpit frontend entry point (ES module, no
   framework, no bundler — see cockpit/app/static/package.json).
   F-0006 field-measurement workflow — device-centric, no GPS.
   Visual/UX layer applies 6 psychology principles (smart defaults,
   goal-gradient, reciprocity, endowment/IKEA, loss aversion, contrast/
   anchoring) on top of the unchanged backend contracts.

   cockpit-redesign Stage 2a (spec §6/§16): this file used to BE the whole
   frontend (2815 lines, no modules, 40 inline onclick/onchange/ontoggle
   handlers). It is now the bootstrap only — every feature lives in its own
   module under js/, imported below. Kept at this path (not moved into
   js/) so /static/app.js keeps resolving exactly as before — the HTTP
   contract test at cockpit/tests/test_http.py and index.html's
   <script type="module" src="/static/app.js"> are both unaffected by the
   split underneath. */
import { state } from './js/state.js';
import { apiJSON } from './js/api.js';
import { initHeroRing, renderHero } from './js/hero.js';
import { loadNodes, initNodesView, renderNodeDashboard } from './js/nodes.js';
import { initSelectedPanel, renderSelectedNode } from './js/selected-panel.js';
import { initDeviceStatus, startSignalAgeTicker, refreshDeviceStatus } from './js/device-status.js';
import { initRunControls } from './js/run.js';
import { initSheet } from './js/sheet.js';
import { initHistoryView } from './js/history.js';
import { initMapView } from './js/map.js';
import { initEventsView } from './js/events.js';
import { loadRfEnvironment } from './js/rf.js';
import { loadDevices, initRegistration } from './js/registration.js';
import { initViewSwitch } from './js/view-switch.js';
import { initOverlays } from './js/overlays.js';
import { initSSE } from './js/sse.js';

// ---------------------------------------------------------------------------
// Run-progress ticker — recomputes the progress bars/labels from
// wall-clock time every ~30 s so they move smoothly between SSE 'nodes'
// events; loadNodes() (triggered by that event) snaps them back to server
// truth (segment_index/current_sf/done).
// ---------------------------------------------------------------------------

let _progressTimer = null;

function startProgressTicker() {
  if (_progressTimer) return;
  _progressTimer = setInterval(() => {
    renderHero(); // smooth ring/per-device movement from the live elapsed÷planned extrapolation
    renderNodeDashboard();
    renderSelectedNode();
    refreshDeviceStatus(); // periodic refresh — queue/last-downlink can change without an SSE 'nodes' event
    loadRfEnvironment(); // periodic safety-net refresh alongside the throttled SSE-driven one
  }, 30000);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

function applyInitialState(s) {
  for (const [eui, m] of Object.entries(s.devices || {})) {
    state.devMetrics[eui] = {
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

  // RF Environment (always-on) — seed the own/foreign totals instantly from
  // this lightweight snapshot; the richer survey (heatmap, networks,
  // devices, vendors) loads separately via loadRfEnvironment() in init().
  const ownEl = document.getElementById('coex-own-count');
  const foreignEl = document.getElementById('coex-foreign-count');
  if (ownEl) ownEl.textContent = s.coex_own_frames || 0;
  if (foreignEl) foreignEl.textContent = s.coex_foreign_frames || 0;
}

async function init() {
  initHeroRing();
  initOverlays();
  initViewSwitch();
  initNodesView();
  initSelectedPanel();
  initDeviceStatus();
  initRunControls();
  initSheet();
  initHistoryView();
  initMapView();
  initEventsView();
  initRegistration();

  try {
    const s = await apiJSON('/api/state');
    applyInitialState(s);
  } catch (_) {}
  await loadNodes();
  initSSE();
  loadDevices();
  loadRfEnvironment();
  startProgressTicker();
  startSignalAgeTicker();
}

init();
