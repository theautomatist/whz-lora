// registration.js — Device registration (collapsible "Device registration"
// card): register + list OTAA devices in ChirpStack, and the bulk Vicki
// (MClimate) convenience downlinks sent to every registered device.
// Unchanged behaviour from the old app.js; inline onclick replaced with
// addEventListener (cockpit-redesign Stage 2a, spec §6).
import { apiJSON } from './api.js';
import { esc, setMsg, toast } from './format.js';

let _currentDevices = []; // last /api/devices (ChirpStack) result — used by Vicki bulk

async function registerDevice() {
  const name     = document.getElementById('dev-name').value.trim();
  const dev_eui  = document.getElementById('dev-eui').value.trim().toLowerCase();
  const app_key  = document.getElementById('dev-appkey').value.trim().toLowerCase();
  const join_eui = document.getElementById('dev-joineui').value.trim() || '0000000000000000';
  const msg      = document.getElementById('dev-msg');

  if (!name || !dev_eui || !app_key) {
    setMsg(msg, 'Name, DevEUI and AppKey are required.', 'err');
    return;
  }
  try {
    const data = await apiJSON('/api/devices', {
      method: 'POST',
      body: JSON.stringify({ name, dev_eui, app_key, join_eui }),
    });
    setMsg(msg, `Registered: ${data.dev_eui}`);
    toast('Device registered.');
    loadDevices();
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  }
}

export async function loadDevices() {
  try {
    const data = await apiJSON('/api/devices');
    renderDeviceList(data.devices || []);
  } catch (e) {
    setMsg(document.getElementById('dev-msg'), `Error loading: ${e.message}`, 'err');
  }
}

function renderDeviceList(devices) {
  _currentDevices = devices;
  const tbody = document.getElementById('dev-list-body');
  if (!devices.length) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:12px 0">— no devices —</td></tr>';
    return;
  }
  tbody.innerHTML = devices.map(d => `
    <tr>
      <td class="mono">${esc(d.dev_eui)}</td>
      <td>${esc(d.name)}</td>
      <td>${esc(d.device_profile_name || '—')}</td>
      <td>${d.last_seen_at ? d.last_seen_at.replace('T', ' ').substring(0, 19) : '—'}</td>
    </tr>
  `).join('');
}

async function sendVickiKeepalive() {
  const msg = document.getElementById('vicki-msg');
  if (!_currentDevices.length) {
    setMsg(msg, 'No devices — load the device list first (above).', 'err');
    return;
  }
  let ok = 0, fail = 0, firstErr = null;
  for (const d of _currentDevices) {
    try {
      // 0x02 SetSendPeriod, 0x05 = 5 minutes
      // count:false — interval command doesn't count towards the DL-PDR denominator
      await apiJSON('/api/downlink', {
        method: 'POST',
        body: JSON.stringify({ dev_eui: d.dev_eui, f_port: 1, data_hex: '0205', count: false }),
      });
      ok++;
    } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  const txt = `Interval queued: ${ok} ok` + (fail ? `, ${fail} failed: ${firstErr}` : '') + '.';
  setMsg(msg, txt, fail ? 'err' : '');
  toast(`Vicki interval: ${ok} queued.`);
}

async function sendVickiLoopback() {
  const msg = document.getElementById('vicki-msg');
  if (!_currentDevices.length) {
    setMsg(msg, 'No devices — load the device list first (above).', 'err');
    return;
  }
  let ok = 0, fail = 0, firstErr = null;
  for (const d of _currentDevices) {
    try {
      // 0x04 = read HW/SW version (confirmed, counts towards DL-PDR; count:true)
      await apiJSON('/api/downlink', {
        method: 'POST',
        body: JSON.stringify({ dev_eui: d.dev_eui, f_port: 1, data_hex: '04', count: true }),
      });
      ok++;
    } catch (e) { fail++; if (!firstErr) firstErr = e.message; }
  }
  const txt = `HW/SW version queued: ${ok} ok` + (fail ? `, ${fail} failed: ${firstErr}` : '') + '.';
  setMsg(msg, txt, fail ? 'err' : '');
  toast(`Vicki HW/SW version: ${ok} queued.`);
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initRegistration() {
  document.getElementById('btn-register-device').addEventListener('click', registerDevice);
  document.getElementById('btn-load-devices').addEventListener('click', loadDevices);
  document.getElementById('btn-vicki-keepalive').addEventListener('click', sendVickiKeepalive);
  document.getElementById('btn-vicki-loopback').addEventListener('click', sendVickiLoopback);
}
