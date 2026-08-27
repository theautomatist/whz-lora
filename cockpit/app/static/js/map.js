// map.js — F-0008 Map / Placement Editor: drag node markers onto an
// uploaded map image. Explicitly a placeholder: the first map is an
// isometric building view whose perspective distorts real coordinates, so
// x/y are fractions (0..1) of the image, not real-world positions — this is
// about the editor UX + persistence, not accurate positioning yet.
//
// The map position is a PLACEMENT attribute (frozen per measurement, same
// idea as floor/room/photos — see sheet.js's own "Position on floor plan"
// control). Dragging a marker here edits the node's CURRENT ACTIVE
// placement in place (PUT /api/marker) — it never creates one, so the
// palette below only ever offers already-placed nodes. Unchanged behaviour
// from the old app.js; inline onclick/onchange replaced with
// addEventListener and event delegation (cockpit-redesign Stage 2a, spec §6).
import { state } from './state.js';
import { apiJSON, extractDetail } from './api.js';
import { esc, toast, setMsg } from './format.js';

let _mapFloorplan = null; // {id, name, image_url} | null
let _mapMarkers = [];     // [{node_id, name, kind, x, y}]

export async function loadMapView() {
  try {
    const data = await apiJSON('/api/floorplan');
    _mapFloorplan = data.floorplan;
    _mapMarkers = data.markers || [];
    renderMapView();
  } catch (e) {
    toast(`Error loading map: ${e.message}`);
  }
}

function renderMapView() {
  const emptyEl = document.getElementById('map-empty');
  const withEl = document.getElementById('map-with-image');
  if (!emptyEl || !withEl) return;

  if (!_mapFloorplan) {
    emptyEl.classList.remove('is-hidden');
    withEl.classList.add('is-hidden');
    return;
  }
  emptyEl.classList.add('is-hidden');
  withEl.classList.remove('is-hidden');

  const img = document.getElementById('map-image');
  if (img) img.src = _mapFloorplan.image_url;
  const nameEl = document.getElementById('map-name');
  if (nameEl) nameEl.textContent = _mapFloorplan.name;

  renderMapMarkers();
  renderMapUnplacedList();
  initMapDrag();
}

/** Upload (empty state) or replace (with a map already) — same handler,
 * both file inputs feed it. */
async function onMapImageSelected(e) {
  const file = e.target.files && e.target.files[0];
  e.target.value = ''; // allow re-selecting the same file again
  if (!file) return;

  const msg = document.getElementById('map-upload-msg');
  if (msg) setMsg(msg, 'Uploading…');
  try {
    const fd = new FormData();
    fd.append('file', file, file.name || 'map.jpg');
    const res = await fetch('/api/floorplan', { method: 'POST', body: fd });
    if (res.status === 401) { toast('Not authenticated.'); return; }
    if (!res.ok) throw new Error(await extractDetail(res));
    if (msg) setMsg(msg, '');
    toast('Map uploaded.');
    await loadMapView();
  } catch (err) {
    toast(`Upload failed: ${err.message}`);
    if (msg) setMsg(msg, `Error: ${err.message}`, 'err');
  }
}

/** Gateway vs. device markers are visually distinct (dot color + icon);
 * both carry the node name label and a small remove ("x") action. Absolute
 * positions (left/top %) come straight from x/y (fractions of the image). */
function renderMapMarkers() {
  const el = document.getElementById('map-markers');
  if (!el) return;
  el.innerHTML = _mapMarkers.map(m => `
    <div class="map-marker map-marker-${esc(m.kind)}" data-node-id="${m.node_id}"
         style="left:${(m.x * 100).toFixed(2)}%;top:${(m.y * 100).toFixed(2)}%">
      <button type="button" class="map-marker-remove" title="Remove from map">×</button>
      <div class="map-marker-dot">${m.kind === 'gateway' ? '⌂' : '●'}</div>
      <div class="map-marker-label">${esc(m.name)}</div>
    </div>`).join('');
}

/** Nodes with an active placement but no map position yet — tap one to
 * place it at the map's center (a drag then fine-tunes the position). A
 * node with no active placement at all never appears here — placing it
 * (Place / Relocate) is a separate step, since dragging a marker only ever
 * edits an EXISTING placement, never creates one. */
function renderMapUnplacedList() {
  const el = document.getElementById('map-unplaced-list');
  if (!el) return;
  const placedIds = new Set(_mapMarkers.map(m => m.node_id));
  const unplaced = state.nodes.filter(n => n.placement && !placedIds.has(n.id));
  if (!unplaced.length) {
    el.innerHTML = '<p class="hint">All placed nodes are already on the map.</p>';
    return;
  }
  el.innerHTML = unplaced.map(n => `
    <button type="button" class="map-unplaced-chip" data-node-id="${n.id}">
      <span class="map-unplaced-dot ${n.kind === 'gateway' ? 'gw' : ''}"></span>${esc(n.name)}
    </button>`).join('');
}

async function addNodeToMap(nodeId) {
  const ok = await saveMarkerPosition(nodeId, 0.5, 0.5); // "place at center"
  if (ok) {
    renderMapMarkers();
    renderMapUnplacedList();
  }
}

async function removeMapMarker(nodeId) {
  try {
    await apiJSON(`/api/marker/${nodeId}`, { method: 'DELETE' });
    _mapMarkers = _mapMarkers.filter(m => m.node_id !== nodeId);
    renderMapMarkers();
    renderMapUnplacedList();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

/** PUT /api/marker (sets the node's CURRENT ACTIVE placement's map
 * position — never creates a placement) + keep the in-memory _mapMarkers
 * cache in sync (adding an entry the first time a node is positioned).
 * Returns true on success so callers can decide whether to re-render or
 * snap back. */
async function saveMarkerPosition(nodeId, x, y) {
  try {
    await apiJSON('/api/marker', {
      method: 'PUT',
      body: JSON.stringify({ node_id: nodeId, x, y }),
    });
    const existing = _mapMarkers.find(m => m.node_id === nodeId);
    if (existing) {
      existing.x = x;
      existing.y = y;
    } else {
      const node = state.nodesById[nodeId];
      _mapMarkers.push({ node_id: nodeId, name: node ? node.name : '', kind: node ? node.kind : 'device', x, y });
    }
    return true;
  } catch (e) {
    toast(`Could not save position: ${e.message}`);
    return false;
  }
}

/** Mouse + touch drag via the unified Pointer Events API, delegated on the
 * stable #map-markers container (so it keeps working across re-renders —
 * markers are replaced wholesale on every renderMapMarkers() call). Only
 * ever wired once (subsequent loadMapView() calls reuse it). touch-action:
 * none (CSS) on the stage/markers keeps a drag from also scrolling the
 * page on a phone. Remove-button and unplaced-chip clicks are delegated
 * here too (cockpit-redesign Stage 2a, spec §6). */
let _mapDragInitialized = false;

function initMapDrag() {
  if (_mapDragInitialized) return;
  const markersEl = document.getElementById('map-markers');
  const stageEl = document.getElementById('map-stage');
  const unplacedEl = document.getElementById('map-unplaced-list');
  if (!markersEl || !stageEl) return;
  _mapDragInitialized = true;

  let dragEl = null;
  let dragNodeId = null;
  let pendingXY = null;

  markersEl.addEventListener('click', (e) => {
    const removeBtn = e.target.closest('.map-marker-remove');
    if (!removeBtn) return;
    const marker = removeBtn.closest('.map-marker');
    const nodeId = marker ? parseInt(marker.dataset.nodeId, 10) : NaN;
    if (!isNaN(nodeId)) removeMapMarker(nodeId);
  });

  if (unplacedEl) {
    unplacedEl.addEventListener('click', (e) => {
      const chip = e.target.closest('.map-unplaced-chip');
      if (!chip) return;
      const nodeId = parseInt(chip.dataset.nodeId, 10);
      if (!isNaN(nodeId)) addNodeToMap(nodeId);
    });
  }

  markersEl.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.map-marker-remove')) return; // let its own click fire, don't drag
    const marker = e.target.closest('.map-marker');
    if (!marker) return;
    dragEl = marker;
    dragNodeId = parseInt(marker.dataset.nodeId, 10);
    pendingXY = null;
    marker.classList.add('dragging');
    marker.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  markersEl.addEventListener('pointermove', (e) => {
    if (!dragEl) return;
    const rect = stageEl.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    dragEl.style.left = `${(x * 100).toFixed(2)}%`;
    dragEl.style.top = `${(y * 100).toFixed(2)}%`;
    pendingXY = { x, y };
  });

  function endDrag() {
    if (!dragEl) return;
    dragEl.classList.remove('dragging');
    const nodeId = dragNodeId;
    const xy = pendingXY;
    dragEl = null;
    dragNodeId = null;
    pendingXY = null;
    if (xy) {
      saveMarkerPosition(nodeId, xy.x, xy.y).then(ok => {
        if (!ok) renderMapMarkers(); // snap back to the last known-good position
      });
    }
  }

  markersEl.addEventListener('pointerup', endDrag);
  markersEl.addEventListener('pointercancel', endDrag);
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initMapView() {
  document.getElementById('map-upload-input').addEventListener('change', onMapImageSelected);
  document.getElementById('map-replace-input').addEventListener('change', onMapImageSelected);
  document.getElementById('btn-map-upload').addEventListener('click', () =>
    document.getElementById('map-upload-input').click());
  document.getElementById('btn-map-replace').addEventListener('click', () =>
    document.getElementById('map-replace-input').click());
}
