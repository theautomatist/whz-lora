// view-switch.js — cockpit-redesign Stage 2b (spec §11/§20): the bottom
// tab bar (Devices · Events · Radio · Map) plus the two level-2 screens
// reached one tap deeper (device detail, from a Devices card; measurement
// history, from the "All measurement history" link) — replaces the old
// header Live | History | Map | Events switch. Still only toggles
// `.is-hidden` (via classList, not inline style), same idiom as before
// this stage.
//
// Adds `history.pushState`/`popstate` (spec §11: "the Android back button
// and iOS edge-swipe leave the app" otherwise) — a small, deliberately
// shallow addition: it remembers which screen was open, not scroll
// position or any open sheet's field values (spec §11 sizes that whole
// feature at "~20 lines"; this is that feature, not more).
import { state } from './state.js';
import { closeHistoryDetail, loadHistoryList } from './history.js';
import { loadMapView } from './map.js';
import { loadEventsLog } from './events.js';
import { loadRfEnvironment } from './rf.js';

const TOP_TABS = ['devices', 'events', 'radio', 'map'];
const VIEW_IDS = {
  devices: 'view-devices',
  events:  'view-events',
  radio:   'view-radio',
  map:     'view-map',
  detail:  'view-detail',
  history: 'view-history',
};

function showView(view, opts = {}) {
  if (!VIEW_IDS[view]) view = 'devices';
  state.currentView = view;

  for (const [key, id] of Object.entries(VIEW_IDS)) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('is-hidden', key !== view);
  }

  const activeTab = TOP_TABS.includes(view) ? view : 'devices';
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === activeTab));

  if (!opts.fromPopState) {
    try { history.pushState({ view }, '', location.pathname + location.search); } catch (_) { /* non-browser test harness */ }
  }

  onViewShown(view);
}

function onViewShown(view) {
  if (view === 'events') {
    loadEventsLog(true);
  } else if (view === 'radio') {
    loadRfEnvironment();
  } else if (view === 'map') {
    loadMapView();
  } else if (view === 'history') {
    closeHistoryDetail(); // always land on the list, never a stale detail
    loadHistoryList();
  }
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initViewSwitch() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => showView(btn.dataset.tab));
  });

  const openHistoryBtn = document.getElementById('btn-open-history');
  if (openHistoryBtn) openHistoryBtn.addEventListener('click', () => showView('history'));

  const detailBackBtn = document.getElementById('detail-back-btn');
  if (detailBackBtn) detailBackBtn.addEventListener('click', () => showView('devices'));

  const historyBackBtn = document.getElementById('history-back-btn');
  if (historyBackBtn) historyBackBtn.addEventListener('click', () => showView('devices'));

  // Dispatched by nodes.js when a Devices card is tapped — decouples the
  // navigation module from the device-list module (no import cycle).
  document.addEventListener('cockpit:open-detail', () => showView('detail'));

  window.addEventListener('popstate', (e) => {
    const view = (e.state && e.state.view) || 'devices';
    showView(view, { fromPopState: true });
  });

  try { history.replaceState({ view: 'devices' }, '', location.pathname + location.search); } catch (_) { /* non-browser test harness */ }
  showView('devices', { fromPopState: true });
}
