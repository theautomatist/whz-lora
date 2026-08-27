// api.js — thin fetch wrappers shared by every feature module. Unchanged
// behaviour from the old app.js: 401 shows a toast and rejects, non-2xx
// bodies raise with the server's `detail` text via extractDetail().
import { toast } from './format.js';

export async function apiFetch(path, opts = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const res = await fetch(path, Object.assign(defaults, opts));
  if (res.status === 401) { toast('Not authenticated — use the browser dialog.'); throw new Error('401'); }
  return res;
}

export async function apiJSON(path, opts = {}) {
  const res = await apiFetch(path, opts);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

/** Extract a human-readable message from a FastAPI error response body. */
export async function extractDetail(res) {
  try {
    const body = await res.json();
    const d = body.detail;
    return typeof d === 'string' ? d : JSON.stringify(d);
  } catch (_) {
    return `HTTP ${res.status}`;
  }
}

/** Upload a photo file to a placement — must NOT set Content-Type manually
 * (the browser sets the multipart boundary). */
export async function uploadPhoto(placementId, file) {
  const fd = new FormData();
  fd.append('file', file, file.name || 'photo.jpg');
  const res = await fetch(`/api/photo/${placementId}`, { method: 'POST', body: fd });
  if (res.status === 401) { toast('Not authenticated.'); throw new Error('401'); }
  if (!res.ok) throw new Error(await extractDetail(res));
  return res.json();
}
