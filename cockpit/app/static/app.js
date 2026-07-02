/* app.js — Feldtest-Cockpit frontend (vanilla JS, no framework) */
'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const _devMetrics = {};   // { dev_eui: { rssi, snr, sf, f_cnt, pos_received, pdr, acked, downlinks_sent, dl_pdr } }
const _coexData   = {};   // { "ch<n>_sf<n>": { channel, sf, frames, caf, tl } }
let _sseConnected = false;

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

function toast(msg, ms = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), ms);
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiFetch(path, opts = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const res = await fetch(path, Object.assign(defaults, opts));
  if (res.status === 401) { toast('Not authenticated — enter credentials in browser dialog.'); throw new Error('401'); }
  return res;
}

async function apiJSON(path, opts = {}) {
  const res = await apiFetch(path, opts);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Panel 1 — Devices
// ---------------------------------------------------------------------------

async function registerDevice() {
  const name    = document.getElementById('dev-name').value.trim();
  const dev_eui = document.getElementById('dev-eui').value.trim().toLowerCase();
  const app_key = document.getElementById('dev-appkey').value.trim().toLowerCase();
  const join_eui = document.getElementById('dev-joineui').value.trim() || '0000000000000000';
  const msg = document.getElementById('dev-msg');

  if (!name || !dev_eui || !app_key) { msg.textContent = 'Name, DevEUI and AppKey are required.'; return; }

  try {
    const data = await apiJSON('/api/devices', {
      method: 'POST',
      body: JSON.stringify({ name, dev_eui, app_key, join_eui }),
    });
    msg.textContent = `Registered: ${data.dev_eui}`;
    msg.className = 'msg';
    toast('Device registered.');
    loadDevices();
  } catch (e) {
    msg.textContent = `Error: ${e.message}`;
    msg.className = 'msg error';
  }
}

async function loadDevices() {
  try {
    const data = await apiJSON('/api/devices');
    renderDeviceList(data.devices || []);
  } catch (e) {
    document.getElementById('dev-msg').textContent = `Error loading devices: ${e.message}`;
  }
}

function renderDeviceList(devices) {
  const tbody = document.getElementById('dev-list-body');
  if (!devices.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted)">No devices.</td></tr>';
    return;
  }
  tbody.innerHTML = devices.map(d => `
    <tr>
      <td><code>${d.dev_eui}</code></td>
      <td>${esc(d.name)}</td>
      <td>${esc(d.device_profile_name || '')}</td>
      <td>${d.last_seen_at ? d.last_seen_at.replace('T',' ').substring(0,19) : '—'}</td>
    </tr>
  `).join('');
}

// ---------------------------------------------------------------------------
// Panel 2 — Measurement point + CSV
// ---------------------------------------------------------------------------

async function setPoint() {
  const msg = document.getElementById('pt-msg');
  const body = {
    pos_id:     document.getElementById('pt-posid').value.trim(),
    floor:      document.getElementById('pt-floor').value.trim(),
    room:       document.getElementById('pt-room').value.trim(),
    point_type: document.getElementById('pt-type').value,
    path:       document.getElementById('pt-path').value.trim(),
    los:        document.getElementById('pt-los').value,
    mounting:   document.getElementById('pt-mounting').value.trim(),
    expected_n: parseInt(document.getElementById('pt-n').value) || null,
  };
  if (!body.pos_id) { msg.textContent = 'Pos-ID is required.'; return; }
  try {
    await apiJSON('/api/point', { method: 'POST', body: JSON.stringify(body) });
    document.getElementById('cur-point').textContent = `Point: ${body.pos_id}`;
    document.getElementById('badge-point').textContent = `Point: ${body.pos_id}`;
    msg.textContent = `Point set: ${body.pos_id}`;
    msg.className = 'msg';
    toast(`Measurement point: ${body.pos_id}`);
  } catch (e) {
    msg.textContent = `Error: ${e.message}`;
    msg.className = 'msg error';
  }
}

async function startRecording() {
  try {
    const data = await apiJSON('/api/recording', { method: 'POST', body: JSON.stringify({ on: true }) });
    document.getElementById('rec-msg').textContent = `Recording: ${data.csv_path || ''}`;
    document.getElementById('btn-rec-start').disabled = true;
    document.getElementById('btn-rec-stop').disabled  = false;
    document.getElementById('badge-rec').textContent  = '● Recording';
    document.getElementById('badge-rec').className    = 'badge recording';
    toast('Recording started.');
  } catch (e) {
    document.getElementById('rec-msg').textContent = `Error: ${e.message}`;
  }
}

async function stopRecording() {
  try {
    const data = await apiJSON('/api/recording', { method: 'POST', body: JSON.stringify({ on: false }) });
    document.getElementById('rec-msg').textContent = `Saved: ${data.csv_path || '—'}`;
    document.getElementById('btn-rec-start').disabled = false;
    document.getElementById('btn-rec-stop').disabled  = true;
    document.getElementById('badge-rec').textContent  = '■ Stopped';
    document.getElementById('badge-rec').className    = 'badge stopped';
    toast('Recording stopped.');
  } catch (e) {
    document.getElementById('rec-msg').textContent = `Error: ${e.message}`;
  }
}

// ---------------------------------------------------------------------------
// Panel 3 — Live dashboard (updated via SSE)
// ---------------------------------------------------------------------------

function renderLiveTable() {
  const tbody = document.getElementById('live-body');
  const rows  = Object.entries(_devMetrics);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="10" style="color:var(--muted)">Waiting for uplinks…</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(([eui, m]) => `
    <tr id="row-${eui}">
      <td><code>${eui}</code></td>
      <td>${fmtNum(m.rssi)}</td>
      <td>${fmtNum(m.snr)}</td>
      <td>${m.sf != null ? 'SF' + m.sf : '—'}</td>
      <td>${m.f_cnt != null ? m.f_cnt : '—'}</td>
      <td>${m.pos_received != null ? m.pos_received : '—'}</td>
      <td>${m.pdr != null ? (m.pdr * 100).toFixed(1) + ' %' : '—'}</td>
      <td>${m.downlinks_sent != null ? m.downlinks_sent : '—'}</td>
      <td>${m.acked != null ? m.acked : '—'}</td>
      <td>${m.dl_pdr != null ? (m.dl_pdr * 100).toFixed(1) + ' %' : '—'}</td>
    </tr>
  `).join('');
}

function flashRow(eui) {
  const row = document.getElementById(`row-${eui}`);
  if (!row) return;
  row.classList.remove('highlight');
  void row.offsetWidth; // reflow
  row.classList.add('highlight');
}

// ---------------------------------------------------------------------------
// Panel 4 — Downlink
// ---------------------------------------------------------------------------

async function enqueueDownlink() {
  const msg = document.getElementById('dl-msg');
  const body = {
    dev_eui:  document.getElementById('dl-eui').value.trim().toLowerCase(),
    f_port:   parseInt(document.getElementById('dl-fport').value),
    data_hex: document.getElementById('dl-data').value.trim() || '00',
  };
  if (!body.dev_eui) { msg.textContent = 'DevEUI required.'; return; }
  try {
    await apiJSON('/api/downlink', { method: 'POST', body: JSON.stringify(body) });
    msg.textContent = `Enqueued confirmed DL on fport ${body.f_port}.`;
    msg.className = 'msg';
    toast('Downlink enqueued.');
  } catch (e) {
    msg.textContent = `Error: ${e.message}`;
    msg.className = 'msg error';
  }
}

// ---------------------------------------------------------------------------
// Panel 5 — Coexistence scan
// ---------------------------------------------------------------------------

async function toggleCoex(on) {
  try {
    await apiJSON('/api/coex', { method: 'POST', body: JSON.stringify({ on }) });
    document.getElementById('btn-coex-start').disabled = on;
    document.getElementById('btn-coex-stop').disabled  = !on;
    document.getElementById('coex-status').textContent = on ? 'Scan active…' : 'Scan stopped.';
    if (!on) toast('Coex scan stopped.');
    else      toast('Coex scan started.');
  } catch (e) {
    document.getElementById('coex-status').textContent = `Error: ${e.message}`;
  }
}

function updateCoexTable(event) {
  // key: "ch<channel>_sf<sf>" to deduplicate
  const key = `ch${event.channel}_sf${event.sf}`;
  const prev = _coexData[key] || { frames: 0 };
  _coexData[key] = {
    channel: event.channel,
    sf:      event.sf,
    frames:  (prev.frames || 0) + 1,
    caf:     event.caf,
    tl:      event.traffic_light,
  };
  renderCoexTable();
}

function renderCoexTable() {
  const tbody = document.getElementById('coex-body');
  const rows  = Object.values(_coexData);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--muted)">No data yet.</td></tr>';
    return;
  }
  rows.sort((a, b) => a.channel - b.channel || a.sf - b.sf);
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td>CH${r.channel >= 0 ? r.channel : '?'}</td>
      <td>SF${r.sf}</td>
      <td>${r.frames}</td>
      <td>${(r.caf * 100).toFixed(3)} %</td>
      <td class="tl-${r.tl}">${r.tl.toUpperCase()}</td>
    </tr>
  `).join('');
}

// ---------------------------------------------------------------------------
// Panel 6 — Antenna
// ---------------------------------------------------------------------------

async function setAntenna(type) {
  try {
    await apiJSON('/api/antenna', { method: 'POST', body: JSON.stringify({ type }) });
    _applyAntenna(type);
    toast(`Antenna: ${type}`);
  } catch (e) {
    document.getElementById('ant-msg').textContent = `Error: ${e.message}`;
  }
}

function _applyAntenna(type) {
  document.getElementById('ant-indicator').textContent = type;
  document.getElementById('badge-antenna').textContent = `Antenna: ${type}`;
  document.getElementById('ant-3dbi').classList.toggle('active',  type === '3dbi');
  document.getElementById('ant-12dbi').classList.toggle('active', type === '12dbi');
}

// ---------------------------------------------------------------------------
// SSE — live event stream
// ---------------------------------------------------------------------------

function initSSE() {
  let es;
  const badgeSse = document.getElementById('badge-sse');

  function connect() {
    es = new EventSource('/api/events');

    es.onopen = () => {
      _sseConnected = true;
      badgeSse.textContent = 'SSE: connected';
    };

    es.onmessage = (e) => {
      try {
        handleEvent(JSON.parse(e.data));
      } catch (_) {}
    };

    es.onerror = () => {
      _sseConnected = false;
      badgeSse.textContent = 'SSE: reconnecting…';
      es.close();
      setTimeout(connect, 4000);
    };
  }

  connect();
}

function handleEvent(ev) {
  switch (ev.type) {
    case 'uplink': {
      const eui = ev.dev_eui;
      const prev = _devMetrics[eui] || {};
      _devMetrics[eui] = {
        rssi:           ev.rssi_dbm,
        snr:            ev.snr_db,
        sf:             ev.sf,
        f_cnt:          ev.f_cnt,
        pos_received:   ev.pos_received,
        pdr:            ev.pdr,
        downlinks_sent: prev.downlinks_sent,
        acked:          prev.acked,
        dl_pdr:         prev.dl_pdr,
      };
      renderLiveTable();
      flashRow(eui);
      break;
    }
    case 'ack': {
      const eui = ev.dev_eui;
      if (_devMetrics[eui]) {
        _devMetrics[eui].acked  = ev.acked;
        _devMetrics[eui].dl_pdr = ev.downlink_pdr;
        renderLiveTable();
      }
      break;
    }
    case 'join':
      toast(`Join: ${ev.dev_eui} → DevAddr ${ev.dev_addr}`);
      break;
    case 'coex':
      updateCoexTable(ev);
      break;
    case 'state':
      if (ev.antenna)  _applyAntenna(ev.antenna);
      if (ev.pos_id)   document.getElementById('cur-point').textContent = `Point: ${ev.pos_id}`;
      break;
  }
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

async function init() {
  // Trigger auth by fetching state; browser shows Basic dialog on 401
  try {
    const state = await apiJSON('/api/state');
    applyInitialState(state);
  } catch (_) {}

  initSSE();
  loadDevices();
}

function applyInitialState(s) {
  if (s.antenna) _applyAntenna(s.antenna);
  if (s.point && s.point.pos_id) {
    document.getElementById('cur-point').textContent  = `Point: ${s.point.pos_id}`;
    document.getElementById('badge-point').textContent = `Point: ${s.point.pos_id}`;
  }
  if (s.recording) {
    document.getElementById('badge-rec').textContent  = '● Recording';
    document.getElementById('badge-rec').className    = 'badge recording';
    document.getElementById('btn-rec-start').disabled = true;
    document.getElementById('btn-rec-stop').disabled  = false;
  }
  // Restore device metrics
  for (const [eui, m] of Object.entries(s.devices || {})) {
    _devMetrics[eui] = {
      rssi: m.rssi_dbm, snr: m.snr_db, sf: m.sf, f_cnt: m.f_cnt,
      downlinks_sent: m.downlinks_sent, acked: m.acked,
      dl_pdr: m.acked && m.downlinks_sent ? m.acked / m.downlinks_sent : null,
    };
  }
  renderLiveTable();
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function fmtNum(v) { return v != null ? Number(v).toFixed(1) : '—'; }

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

document.addEventListener('DOMContentLoaded', init);
