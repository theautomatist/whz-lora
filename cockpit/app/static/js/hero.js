// hero.js — Campaign status hero card: the goal-gradient ring that is never
// zero (principle 2) plus its per-device progress breakdown. Unchanged
// behaviour from the old app.js.
import { state } from './state.js';
import { esc, fmtHoursOfTotal } from './format.js';
import { liveRunProgress } from './run.js';

const HERO_RING_R    = 52;
const HERO_RING_CIRC = 2 * Math.PI * HERO_RING_R;

export function initHeroRing() {
  const ringFill = document.getElementById('hero-ring-fill');
  if (!ringFill) return;
  ringFill.style.strokeDasharray = `${HERO_RING_CIRC}`;
  ringFill.style.strokeDashoffset = `${HERO_RING_CIRC}`; // start fully empty, animates in on first render
}

/** Per-device progress term (0..1) feeding the campaign ring below, plus
 * enough detail (state/fraction/live run) for the hero's per-device
 * breakdown list (renderHeroDeviceList). Mutually exclusive states:
 *   not-placed -> 0
 *   placed     -> 0.4  (placed, never run)
 *   running    -> 0.4 + 0.6 x live elapsed/planned fraction (0..1, clamped;
 *                 0 when the run has no planned duration to extrapolate
 *                 against — e.g. a Phase A run with no sweep)
 *   done       -> 1.0  (a completed last_run and nothing running now)
 * liveRunProgress does the wall-clock extrapolation, so this stays accurate
 * between /api/nodes refreshes too. */
function deviceProgressTerm(n) {
  if (n.active_run && n.active_run.status === 'running') {
    const live = liveRunProgress(n.active_run);
    const frac = live.progress != null ? Math.max(0, Math.min(1, live.progress)) : 0;
    return { state: 'running', value: 0.4 + 0.6 * frac, run: n.active_run, live, frac };
  }
  if (n.last_run && n.last_run.status === 'done') {
    return { state: 'done', value: 1, run: n.last_run };
  }
  if (n.placement) {
    return { state: 'placed', value: 0.4, run: null };
  }
  return { state: 'not-placed', value: 0, run: null };
}

/** progress = (1 [Setup] + gatewayPlaced + Σ per-device term) / (2 + N_devices)
 * Setup contributes a flat 1 so the ring is never 0 — the operator always
 * sees credit for showing up and getting the app running. Each device's
 * term (see deviceProgressTerm) is fine-grained while a run is actually in
 * progress rather than a fixed step, so the ring moves smoothly. */
function computeCampaignProgress() {
  const gateway = state.nodes.find(n => n.kind === 'gateway');
  const devices = state.nodes.filter(n => n.kind === 'device');
  const gatewayPlaced = !!(gateway && gateway.placement);

  let deviceSum = 0, doneCount = 0, runningCount = 0, placedCount = 0;
  const deviceTerms = devices.map(n => {
    const term = deviceProgressTerm(n);
    deviceSum += term.value;
    if (term.state === 'done') doneCount++;
    if (term.state === 'running') runningCount++;
    if (n.placement) placedCount++;
    return Object.assign({ node: n }, term);
  });

  const numerator = 1 + (gatewayPlaced ? 1 : 0) + deviceSum;
  const denominator = 2 + devices.length;
  const progress = denominator > 0 ? Math.max(0, Math.min(1, numerator / denominator)) : 0.5;

  return { progress, gatewayPlaced, deviceCount: devices.length, doneCount, runningCount, placedCount, deviceTerms };
}

export function renderHero() {
  const pctEl     = document.getElementById('hero-pct');
  const ringFill  = document.getElementById('hero-ring-fill');
  const subEl     = document.getElementById('hero-sub');
  if (!pctEl || !ringFill || !subEl) return;

  const { progress, gatewayPlaced, deviceCount, doneCount, runningCount, deviceTerms } = computeCampaignProgress();

  pctEl.textContent = `${Math.round(progress * 100)}%`;
  ringFill.style.strokeDashoffset = `${HERO_RING_CIRC * (1 - progress)}`;

  const parts = [gatewayPlaced ? 'Gateway ✓' : 'Gateway not placed yet'];
  if (deviceCount > 0) parts.push(`${doneCount}/${deviceCount} done`);
  if (runningCount > 0) parts.push(`${runningCount} running`);
  subEl.textContent = parts.join(' · ');

  renderHeroDeviceList(deviceTerms);
}

// running first (live, worth watching), then placed (ready/todo), then
// done (finished), then not-placed (needs setup first) — see
// renderHeroDeviceList below.
const HERO_DEVICE_STATE_ORDER = { running: 0, placed: 1, done: 2, 'not-placed': 3 };

/** "47% · 14 h of 24 h" while running (falls back to just "running" when
 * the run has no planned duration to show progress against); "done ✓" /
 * "placed" / "not placed" otherwise. */
function deviceProgressLabel(term) {
  if (term.state === 'done') return 'done ✓';
  if (term.state === 'placed') return 'placed';
  if (term.state === 'not-placed') return 'not placed';
  if (!term.run || !term.run.planned_seconds) return 'running';
  const pct = Math.round((term.frac || 0) * 100);
  return `${pct}% · ${fmtHoursOfTotal(term.live.elapsedSeconds || 0, term.run.planned_seconds)}`;
}

/** Compact per-device slice of the ring above — a thin bar per device so
 * the operator can see each device's individual progress and how much is
 * left to 100%, not just the aggregate ring. */
function renderHeroDeviceList(deviceTerms) {
  const wrap = document.getElementById('hero-devices');
  if (!wrap) return;
  if (!deviceTerms.length) { wrap.innerHTML = ''; return; }

  const sorted = deviceTerms.slice().sort(
    (a, b) => HERO_DEVICE_STATE_ORDER[a.state] - HERO_DEVICE_STATE_ORDER[b.state]
  );

  wrap.innerHTML = sorted.map(term => `
    <div class="hdev-row hdev-${term.state}">
      <div class="hdev-hdr">
        <span class="hdev-name">${esc(term.node.name)}</span>
        <span class="hdev-label">${esc(deviceProgressLabel(term))}</span>
      </div>
      <div class="hdev-bar-track"><div class="hdev-bar-fill" style="width:${Math.round(term.value * 100)}%"></div></div>
    </div>
  `).join('');
}
