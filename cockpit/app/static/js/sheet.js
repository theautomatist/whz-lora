// sheet.js — the Place / Relocate / Move-gateway bottom sheet: smart
// defaults (principle 1) + outcome-stating submit labels (principle 4), the
// optional F-0008 "Position on floor plan" control, and the loss-framed
// gateway-move pre-flight confirm. Unchanged behaviour from the old app.js;
// inline onclick/onchange replaced with addEventListener (cockpit-redesign
// Stage 2a, spec §6).
import { state } from './state.js';
import { apiFetch, apiJSON, extractDetail, uploadPhoto } from './api.js';
import { esc, setMsg, toast, fmtTime } from './format.js';
import { confirmModal } from './overlays.js';
import { sweepStatusText } from './run.js';
import { loadNodes } from './nodes.js';

let _sheetMode    = null; // 'device' | 'gateway'
let _sheetAntenna = '3dbi';
let _sheetPhotos  = [];   // File[] queued for upload after the placement is created
let _gatewayForce = false; // set by onMoveGatewayClick() before opening the gateway
                            // sheet — true when the pre-flight conflict check already
                            // got the operator's "end the running measurements" OK, so
                            // submitSheet() must call /api/gateway/move/force, not the
                            // plain /api/gateway/move. Reset on sheet open (device mode)
                            // and close.
// F-0008 Map / Placement Editor — the sheet's optional "Position on floor
// plan" control. _sheetFloorplan is the current floorplan (or null — hides
// the control), fetched fresh on every sheet open; _sheetMapPosition is
// the pending {x,y} tap (or null — no position), submitted as map_x/map_y
// alongside floor/room/photos.
let _sheetFloorplan   = null;
let _sheetMapPosition = null;

// ---------------------------------------------------------------------------
// Loss aversion — status list rows shared by the gateway-move pre-flight
// confirm modal and the in-sheet fallback conflict box.
// ---------------------------------------------------------------------------

function _lossRowHtml(name, detail) {
  return `
    <div class="loss-row">
      <div class="loss-name">${esc(name)}</div>
      <div class="loss-detail">${esc(detail)}</div>
    </div>`;
}

function _gatewayLossTitle(count) {
  return count === 1 ? '1 running measurement will be lost' : `${count} running measurements will be lost`;
}

// ---------------------------------------------------------------------------
// Open — "Place / Relocate" / "Move gateway" buttons
// ---------------------------------------------------------------------------

/** "Place / Relocate" button — the confirm gate sits BEFORE the data-entry
 * sheet: a running measurement is a real loss if relocated, so confirm
 * first; a never-run/no-run device has nothing to lose, so it's just a
 * placement — open the sheet directly. */
async function onPlaceOrRelocateClick() {
  const node = state.nodesById[state.selectedNodeId];
  if (!node) return;
  const run = node.active_run;

  if (run && run.status === 'running') {
    const ok = await confirmModal({
      icon: '⚠️',
      title: 'Stop the running measurement?',
      message: `<p>${esc(sweepStatusText(run))}</p><p>Relocating will stop it and start a new protocol.</p>`,
      okLabel: 'Stop & relocate',
      cancelLabel: 'Cancel',
    });
    if (!ok) return;
  }
  openPlaceSheet('device');
}

/** "Move gateway" button — same confirm-before-sheet ordering as
 * onPlaceOrRelocateClick above: check for running measurements FIRST (from
 * the already-loaded state.nodes, no extra API call) and confirm the loss
 * before the data-entry sheet even opens, rather than opening the sheet and
 * only discovering the 409 conflict on submit. _gatewayForce then tells
 * submitSheet() which endpoint to call. */
async function onMoveGatewayClick() {
  const runningDevices = state.nodes.filter(
    n => n.kind === 'device' && n.active_run && n.active_run.status === 'running'
  );

  if (runningDevices.length) {
    const listHtml = runningDevices.map(n => _lossRowHtml(n.name, sweepStatusText(n.active_run))).join('');
    const ok = await confirmModal({
      icon: '⚠️',
      title: _gatewayLossTitle(runningDevices.length),
      message: '',
      listHtml,
      okLabel: 'Move anyway — end measurements',
      cancelLabel: 'Cancel',
    });
    if (!ok) return;
    _gatewayForce = true;
  } else {
    _gatewayForce = false;
  }
  openPlaceSheet('gateway');
}

function openPlaceSheet(mode) {
  const node = state.nodesById[state.selectedNodeId];
  if (!node) return;

  _sheetMode = mode;
  _sheetPhotos = [];
  renderSheetPhotoThumbs();
  // _gatewayForce is set by onMoveGatewayClick() right before opening the
  // gateway sheet — nothing to do with the device path, reset it there so
  // it can never leak a stale 'true' into an unrelated device placement.
  if (mode !== 'gateway') _gatewayForce = false;

  // F-0008 — hide the map-position control until loadSheetMapPosition()
  // (async) resolves, so a re-open never briefly shows the previous node's
  // state; it also decides whether to show the control at all (hidden with
  // no current floorplan).
  _sheetMapPosition = null;
  const mapFieldEl = document.getElementById('sheet-map-field');
  if (mapFieldEl) mapFieldEl.classList.add('is-hidden');
  loadSheetMapPosition();

  document.getElementById('sheet-conflict').classList.add('is-hidden');
  document.getElementById('sheet-form').classList.remove('is-hidden');
  setMsg(document.getElementById('sheet-msg'), '');

  const p = node.placement;
  let floor = p ? (p.floor || '') : '';
  let room  = p ? (p.room || '') : '';
  // Smart default: a never-placed device has no placement to pre-fill from
  // (placements are never deleted, only superseded — so node.placement is
  // only null the very first time) — fall back to the gateway's floor.
  if (!floor && !room && mode === 'device') {
    const gw = state.nodes.find(n => n.kind === 'gateway');
    if (gw && gw.placement) floor = gw.placement.floor || '';
  }
  document.getElementById('sheet-floor').value = floor;
  document.getElementById('sheet-room').value  = room;
  document.getElementById('sheet-desc').value  = p ? (p.description || '') : '';
  document.getElementById('sheet-note').value  = p ? (p.note || '') : '';

  const hasRun = !!(node.active_run && node.active_run.status === 'running');
  const submitBtn = document.getElementById('sheet-submit-btn');
  if (mode === 'gateway') {
    document.getElementById('sheet-title').textContent = 'Move gateway';
    submitBtn.textContent = 'Save location';
  } else if (hasRun) {
    document.getElementById('sheet-title').textContent = 'Relocate device';
    submitBtn.textContent = 'Relocate — close current protocol';
  } else {
    document.getElementById('sheet-title').textContent = 'Place device';
    submitBtn.textContent = 'Place & start measurement';
  }
  // Antenna is a per-device attribute (the gateway has none); photos apply
  // to both — a site photo of the gateway's mounting spot is just as
  // useful as one of a device's.
  document.getElementById('sheet-antenna-field').classList.toggle('is-hidden', mode === 'gateway');
  document.getElementById('sheet-photo-field').classList.remove('is-hidden');

  // Smart default: last-used antenna (from the current placement), else 3 dBi.
  _sheetAntenna = (p && p.antenna) || '3dbi';
  applySheetAntennaUI();

  openSheetOverlay();
}

function selectSheetAntenna(type) {
  _sheetAntenna = type;
  applySheetAntennaUI();
}

function applySheetAntennaUI() {
  document.getElementById('sheet-ant-3dbi').classList.toggle('active', _sheetAntenna === '3dbi');
  document.getElementById('sheet-ant-12dbi').classList.toggle('active', _sheetAntenna === '12dbi');
}

function openSheetOverlay() {
  document.getElementById('place-ov').classList.add('open');
  document.body.classList.add('scroll-locked');
}

function closeSheet() {
  document.getElementById('place-ov').classList.remove('open');
  document.body.classList.remove('scroll-locked');
  _gatewayForce = false;
  _sheetMapPosition = null;
}

function _closeSheetBackdrop(e) {
  if (e.target === document.getElementById('place-ov')) closeSheet();
}

// --- Photo capture (up to 3) — two entry points feed the same queue:
// "Upload photo" (plain file/gallery picker, multi-select) and
// "Take Picture" (capture="environment" opens the live camera on a phone,
// one shot per tap). ---

function onSheetPhotoSelected(e) {
  const files = Array.from(e.target.files || []);
  e.target.value = ''; // allow re-selecting the same file again
  for (const file of files) {
    if (_sheetPhotos.length >= 3) break;
    _sheetPhotos.push(file);
  }
  renderSheetPhotoThumbs();
}

function removeSheetPhoto(idx) {
  _sheetPhotos.splice(idx, 1);
  renderSheetPhotoThumbs();
}

function renderSheetPhotoThumbs() {
  const wrap = document.getElementById('sheet-photo-thumbs');
  wrap.innerHTML = _sheetPhotos.map((f, i) => `
    <div class="pthumb">
      <img src="${URL.createObjectURL(f)}" alt="Photo ${i + 1}">
      <button type="button" class="pthumb-x" data-idx="${i}">×</button>
    </div>
  `).join('');
  const atCap = _sheetPhotos.length >= 3;
  const btnRow = document.getElementById('sheet-photo-btn-row');
  if (btnRow) btnRow.classList.toggle('is-hidden', atCap);
  const capHint = document.getElementById('sheet-photo-cap-hint');
  if (capHint) capHint.classList.toggle('is-hidden', !atCap);
}

// --- Position on floor plan (F-0008) — optional, alongside photos. A
// compact embedded floorplan preview; tap it to drop/move this node's
// marker (touch and mouse both fire a regular 'click'). Submitted as
// map_x/map_y with the placement/relocate/gateway-move call in
// submitSheet() — captured WITH the placement, not a live marker. ---

/** Fetch the current floorplan and decide whether to show the control at
 * all; when shown, pre-fill from the node's previous placement position —
 * but only if that position was captured against this SAME floorplan
 * image (an older position from a since-replaced map would be
 * meaningless overlaid on the new one). */
async function loadSheetMapPosition() {
  const fieldEl = document.getElementById('sheet-map-field');
  if (!fieldEl) return;
  try {
    const data = await apiJSON('/api/floorplan');
    _sheetFloorplan = data.floorplan;
  } catch (e) {
    _sheetFloorplan = null;
  }

  if (!_sheetFloorplan) {
    fieldEl.classList.add('is-hidden');
    return;
  }
  fieldEl.classList.remove('is-hidden');

  const node = state.nodesById[state.selectedNodeId];
  const p = node ? node.placement : null;
  _sheetMapPosition = (p && p.map_x != null && p.map_y != null && p.floorplan_id === _sheetFloorplan.id)
    ? { x: p.map_x, y: p.map_y }
    : null;
  renderSheetMap();
}

function renderSheetMap() {
  const img = document.getElementById('sheet-map-image');
  if (img && _sheetFloorplan) img.src = _sheetFloorplan.image_url;

  const markerEl = document.getElementById('sheet-map-marker');
  if (!markerEl) return;
  markerEl.classList.toggle('gateway', _sheetMode === 'gateway');
  if (_sheetMapPosition) {
    markerEl.classList.remove('is-hidden');
    markerEl.style.left = `${(_sheetMapPosition.x * 100).toFixed(2)}%`;
    markerEl.style.top = `${(_sheetMapPosition.y * 100).toFixed(2)}%`;
  } else {
    markerEl.classList.add('is-hidden');
  }
}

function onSheetMapTap(e) {
  const stage = document.getElementById('sheet-map-stage');
  if (!stage) return;
  const rect = stage.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const x = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
  _sheetMapPosition = { x, y };
  renderSheetMap();
}

function clearSheetMapPosition() {
  _sheetMapPosition = null;
  renderSheetMap();
}

// --- Submit ---

async function submitSheet() {
  const msg = document.getElementById('sheet-msg');
  const floor       = document.getElementById('sheet-floor').value.trim();
  const room        = document.getElementById('sheet-room').value.trim();
  const description = document.getElementById('sheet-desc').value.trim();
  const note        = document.getElementById('sheet-note').value.trim();
  // F-0008 — optional map position, merged into whichever request body
  // below; {} (no keys added) when the control is hidden/untouched.
  const mapPos = _sheetMapPosition ? { map_x: _sheetMapPosition.x, map_y: _sheetMapPosition.y } : {};

  const btn = document.getElementById('sheet-submit-btn');
  btn.disabled = true;
  setMsg(msg, 'Saving…');

  try {
    if (_sheetMode === 'gateway') {
      // onMoveGatewayClick() already ran the loss-framed confirm and set
      // _gatewayForce before this sheet even opened — call the matching
      // endpoint directly instead of trying the plain move first.
      const endpoint = _gatewayForce ? '/api/gateway/move/force' : '/api/gateway/move';
      const res = await apiFetch(endpoint, {
        method: 'POST',
        body: JSON.stringify(Object.assign({ floor, room, description, note }, mapPos)),
      });
      if (res.ok) {
        const result = await res.json();
        for (const file of _sheetPhotos) {
          try {
            await uploadPhoto(result.placement_id, file);
          } catch (e) {
            toast(`Photo upload failed: ${e.message}`);
          }
        }
        toast(_gatewayForce ? 'All runs acknowledged, gateway moved.' : 'Gateway moved.');
        closeSheet();
        await loadNodes();
      } else if (res.status === 409 && !_gatewayForce) {
        // Defensive fallback: a run started between the pre-flight check
        // and this submit — fall back to the existing in-sheet conflict
        // handling (forceGatewayMove() re-POSTs with /force on confirm).
        const body = await res.json();
        const openRuns = (body.detail && body.detail.open_runs) || [];
        showGatewayConflict(openRuns);
      } else {
        setMsg(msg, `Error: ${await extractDetail(res)}`, 'err');
      }
    } else {
      const node = state.nodesById[state.selectedNodeId];
      if (!node) { setMsg(msg, 'No device selected.', 'err'); return; }

      const hasRun = !!node.active_run;
      let placementId;
      if (hasRun) {
        const result = await apiJSON('/api/relocate', {
          method: 'POST',
          body: JSON.stringify(Object.assign(
            { device_node_id: node.id, floor, room, description, note, antenna: _sheetAntenna },
            mapPos,
          )),
        });
        placementId = result.placement_id;
      } else {
        const result = await apiJSON('/api/placement', {
          method: 'POST',
          body: JSON.stringify(Object.assign(
            { node_id: node.id, floor, room, description, note, antenna: _sheetAntenna },
            mapPos,
          )),
        });
        placementId = result.placement_id;
      }

      for (const file of _sheetPhotos) {
        try {
          await uploadPhoto(placementId, file);
        } catch (e) {
          toast(`Photo upload failed: ${e.message}`);
        }
      }

      if (hasRun) {
        // /api/relocate already closed the old run and opened a new one.
        toast('Relocated — new protocol started.');
      } else {
        // The sheet button promises "… & start measurement" — actually start it,
        // so the operator never needs a second tap.
        const total = 24 * 3600, per = Math.floor(total / 3);
        try {
          await apiJSON('/api/run/start', {
            method: 'POST',
            body: JSON.stringify({
              device_node_id: node.id,
              duration_seconds: total,
              sf_schedule: [
                { sf: 7, seconds: per },
                { sf: 9, seconds: per },
                { sf: 12, seconds: total - 2 * per },
              ],
              interval_minutes: 5,
            }),
          });
          toast('Placed — measurement started (24 h sweep).');
        } catch (e) {
          // Most likely: gateway not placed yet (run/start → 409).
          toast('Placed, but measurement NOT started — place the gateway first.');
        }
      }
      closeSheet();
      await loadNodes();
    }
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
  }
}

/** Loss aversion — defensive-fallback path only: a plain /api/gateway/move
 * still 409ed (a run started between the pre-flight check in
 * onMoveGatewayClick and this submit), so fall back to the same in-sheet
 * conflict box as before, using the 409 body's open_runs (device-level
 * detail comes from the last loadNodes() cache, same as onMoveGatewayClick;
 * the 409 body itself doesn't carry sweep detail). */
function showGatewayConflict(openRuns) {
  document.getElementById('sheet-form').classList.add('is-hidden');
  const box = document.getElementById('sheet-conflict');
  box.classList.remove('is-hidden');

  document.getElementById('sheet-conflict-title').textContent = _gatewayLossTitle(openRuns.length);

  const list = document.getElementById('sheet-conflict-list');
  list.innerHTML = openRuns.length
    ? openRuns.map(r => {
        const liveRun = (state.nodesById[r.device_node_id] && state.nodesById[r.device_node_id].active_run) || null;
        const detail = liveRun ? sweepStatusText(liveRun) : `${r.packets} packets · since ${fmtTime(r.started_at)}`;
        return _lossRowHtml(r.name, detail);
      }).join('')
    : '<div class="hint">No details available.</div>';
}

async function forceGatewayMove() {
  const floor       = document.getElementById('sheet-floor').value.trim();
  const room        = document.getElementById('sheet-room').value.trim();
  const description = document.getElementById('sheet-desc').value.trim();
  const note        = document.getElementById('sheet-note').value.trim();
  try {
    const result = await apiJSON('/api/gateway/move/force', {
      method: 'POST',
      body: JSON.stringify({ floor, room, description, note }),
    });
    for (const file of _sheetPhotos) {
      try {
        await uploadPhoto(result.placement_id, file);
      } catch (e) {
        toast(`Photo upload failed: ${e.message}`);
      }
    }
    toast('All runs acknowledged, gateway moved.');
    closeSheet();
    await loadNodes();
  } catch (e) {
    toast(`Error: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initSheet() {
  document.getElementById('btn-place').addEventListener('click', onPlaceOrRelocateClick);
  document.getElementById('btn-gw-move').addEventListener('click', onMoveGatewayClick);

  document.getElementById('place-ov').addEventListener('click', _closeSheetBackdrop);
  document.getElementById('sheet-close-btn').addEventListener('click', closeSheet);
  document.getElementById('sheet-submit-btn').addEventListener('click', submitSheet);

  document.getElementById('sheet-ant-3dbi').addEventListener('click', () => selectSheetAntenna('3dbi'));
  document.getElementById('sheet-ant-12dbi').addEventListener('click', () => selectSheetAntenna('12dbi'));

  document.getElementById('sheet-photo-upload-input').addEventListener('change', onSheetPhotoSelected);
  document.getElementById('sheet-photo-camera-input').addEventListener('change', onSheetPhotoSelected);
  document.getElementById('sheet-photo-upload-btn').addEventListener('click', () =>
    document.getElementById('sheet-photo-upload-input').click());
  document.getElementById('sheet-photo-camera-btn').addEventListener('click', () =>
    document.getElementById('sheet-photo-camera-input').click());
  // Dynamically rendered "×" buttons (renderSheetPhotoThumbs) — event
  // delegation on the stable container instead of a handler per thumbnail
  // (cockpit-redesign Stage 2a, spec §6).
  document.getElementById('sheet-photo-thumbs').addEventListener('click', (e) => {
    const btn = e.target.closest('.pthumb-x');
    if (!btn) return;
    const idx = parseInt(btn.dataset.idx, 10);
    if (!isNaN(idx)) removeSheetPhoto(idx);
  });

  document.getElementById('sheet-map-stage').addEventListener('click', onSheetMapTap);
  document.getElementById('sheet-map-clear-btn').addEventListener('click', clearSheetMapPosition);

  document.getElementById('sheet-conflict-cancel-btn').addEventListener('click', closeSheet);
  document.getElementById('sheet-conflict-force-btn').addEventListener('click', forceGatewayMove);
}
