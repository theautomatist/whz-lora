// view-switch.js — the top-level Live | History | Map | Events tab switch
// (header). Unchanged behaviour from the old app.js — switchView() only
// toggles `display` (via .is-hidden now, not inline style); no
// pushState/hash/sessionStorage, same as before this stage (that is
// cockpit-redesign Stage 4, spec §11, out of scope here). Inline onclick
// replaced with addEventListener (Stage 2a, spec §6).
import { state } from './state.js';
import { closeHistoryDetail, loadHistoryList } from './history.js';
import { loadMapView } from './map.js';
import { loadEventsLog } from './events.js';

function switchView(view) {
  if (view === state.currentView) return;
  state.currentView = view;
  const liveBtn = document.getElementById('vsw-live');
  const histBtn = document.getElementById('vsw-history');
  const mapBtn = document.getElementById('vsw-map');
  const eventsBtn = document.getElementById('vsw-events');
  if (liveBtn) liveBtn.classList.toggle('active', view === 'live');
  if (histBtn) histBtn.classList.toggle('active', view === 'history');
  if (mapBtn) mapBtn.classList.toggle('active', view === 'map');
  if (eventsBtn) eventsBtn.classList.toggle('active', view === 'events');
  const mainEl = document.getElementById('main');
  const histEl = document.getElementById('history-view');
  const mapEl = document.getElementById('map-view');
  const eventsEl = document.getElementById('events-view');
  if (mainEl) mainEl.classList.toggle('is-hidden', view !== 'live');
  if (histEl) histEl.classList.toggle('is-hidden', view !== 'history');
  if (mapEl) mapEl.classList.toggle('is-hidden', view !== 'map');
  if (eventsEl) eventsEl.classList.toggle('is-hidden', view !== 'events');
  if (view === 'history') {
    closeHistoryDetail(); // always land on the list, never a stale detail
    loadHistoryList();
  } else if (view === 'map') {
    loadMapView();
  } else if (view === 'events') {
    loadEventsLog(true);
  }
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initViewSwitch() {
  document.getElementById('vsw-live').addEventListener('click', () => switchView('live'));
  document.getElementById('vsw-history').addEventListener('click', () => switchView('history'));
  document.getElementById('vsw-map').addEventListener('click', () => switchView('map'));
  document.getElementById('vsw-events').addEventListener('click', () => switchView('events'));
}
