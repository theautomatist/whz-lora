// format.js — formatting/utility helpers with no DOM ownership of their
// own (besides the shared #toast element and message-line helper),
// reused across nearly every other module. Pure functions, unchanged
// behaviour from the old app.js.

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------

export function toast(msg, ms = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), ms);
}

export function setMsg(el, text, cls = '') {
  if (!el) return;
  el.textContent = text;
  el.className = 'msg' + (cls ? ' ' + cls : '');
}

// ---------------------------------------------------------------------------
// HTML escaping
// ---------------------------------------------------------------------------

export function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Numbers / time
// ---------------------------------------------------------------------------

export function fmtNum(v) { return v != null ? Number(v).toFixed(1) : '—'; }

export function fmtTime(iso) {
  if (!iso) return '—';
  return String(iso).replace('T', ' ').substring(0, 16);
}

/** "YYYY-MM-DD HH:MM" in the browser's LOCAL timezone (unlike fmtTime
 * above, which shows the raw stored UTC string as-is) — for the History
 * list/detail, where the operator needs a real wall-clock start/end time. */
export function fmtDateTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** "HH:MM:SS" from a stored ts (already UTC, same raw-substring approach as
 * fmtTime — no local-timezone conversion anywhere else in this app). */
export function fmtHms(iso) {
  if (!iso) return '—';
  const t = String(iso).split('T')[1] || '';
  return t.substring(0, 8);
}

export function fmtAgo(ms) {
  if (ms == null) return '';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 5) return 'just now';
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  return `${h} h ago`;
}

/** Whole-days-capable age, no trailing "ago" — for the device-severity
 * reason line (cockpit-redesign Stage 2b, spec §7/§9), which needs "33 d"
 * for a placement/run that is genuinely weeks old, not "792 h ago" like
 * fmtAgo/fmtDuration would produce past the 60 min mark. */
export function fmtAgeShort(ms) {
  if (ms == null) return '—';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return 'just now';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h`;
  const d = Math.floor(h / 24);
  return `${d} d`;
}

/** ≥60 -> "~N min" (rounded), else "~N s"; null -> "—". Shows the actual
 * measured cadence so the operator can confirm a Vicki interval change
 * (e.g. the 5-min downlink) has really taken effect. */
export function fmtInterval(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `~${Math.round(seconds)} s`;
  const minutes = seconds / 60;
  // Hours once we're well past the minute range (e.g. a Vicki device still
  // on its ~4 h factory default, before the 5-min command has taken effect)
  // — "~240 min" is technically correct but much less glanceable than "~4 h".
  if (minutes < 60) return `~${Math.round(minutes)} min`;
  return `~${Math.round(minutes / 60)} h`;
}

/** Duration without the "ago"/"silent for" wrapper, e.g. "12 s", "4 h". */
export function fmtDuration(ms) {
  if (ms == null) return '';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return `${h} h`;
}

/** Whole-hours "elapsed of total" — anchors the part against the whole
 * plan (contrast/anchoring), e.g. "14 h of 24 h" instead of a bare
 * "10 h left" that hides how big the plan actually is. */
export function fmtHoursOfTotal(elapsedSeconds, totalSeconds) {
  const eh = Math.floor(Math.max(0, elapsedSeconds) / 3600);
  const th = Math.max(1, Math.round(totalSeconds / 3600));
  return `${eh} h of ${th} h`;
}

export function ageFromUplinkAt(lastUplinkAt) {
  if (!lastUplinkAt) return '—';
  return fmtAgo(Date.now() - new Date(lastUplinkAt).getTime());
}

/** "Last packet: 12 s ago · Send interval: ~5 min" — small muted
 * metadata line shown on each Overview card (the selected-device panel
 * shows the same two facts, more prominently, in the Device status block
 * instead — not repeated here). */
export function metaLineText(m) {
  const age = m ? ageFromUplinkAt(m.lastUplinkAt) : '—';
  const interval = m ? fmtInterval(m.intervalSeconds) : '—';
  return `Last packet: ${age} · Send interval: ${interval}`;
}

// ---------------------------------------------------------------------------
// Colour-tier classifiers (reused across selected panel + dashboard + RF)
// ---------------------------------------------------------------------------

export function rssiClass(v) {
  if (v == null) return '';
  if (v > -80)   return 'm-good';
  if (v > -110)  return 'm-ok';
  if (v > -120)  return 'm-warn';
  return 'm-bad';
}

export function snrClass(v) {
  if (v == null) return '';
  if (v >= 0)    return 'm-good';
  if (v >= -10)  return 'm-ok';
  if (v >= -15)  return 'm-warn';
  return 'm-bad';
}

export function pdrClass(v) {
  if (v == null) return '';
  if (v >= 0.99) return 'm-good';
  if (v >= 0.80) return 'm-ok';
  if (v >= 0.50) return 'm-warn';
  return 'm-bad';
}

/** excellent / good / marginal / poor — same thresholds as rssiClass,
 * labelled so the number is never shown "bare" (contrast/anchoring). */
export function rssiQualityLabel(v) {
  if (v == null) return { cls: '', label: '—' };
  if (v > -80)  return { cls: 'm-good', label: 'excellent' };
  if (v > -110) return { cls: 'm-ok',   label: 'good' };
  if (v > -120) return { cls: 'm-warn', label: 'marginal' };
  return { cls: 'm-bad', label: 'poor' };
}

export function histStatusLabel(s) {
  return { running: 'Running', done: 'Done', aborted: 'Aborted' }[s] || s;
}
