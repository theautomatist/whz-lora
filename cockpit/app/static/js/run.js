// run.js — start/stop a device's timed SF-sweep run, its live progress
// computation, the glowing segmented sweep timeline, and the one-shot
// "done ✓" celebration. Unchanged behaviour from the old app.js.
import { state } from './state.js';
import { apiFetch, apiJSON, extractDetail } from './api.js';
import { esc, setMsg, toast, fmtHoursOfTotal } from './format.js';
import { confirmModal } from './overlays.js';
import { loadNodes } from './nodes.js';

export const RUN_PRESETS = {
  sf7_sf9_sf12: [7, 9, 12],
  sf9_sf12:     [9, 12],
  sf9:          [9],
  sf12:         [12],
};

// ---------------------------------------------------------------------------
// Loss aversion — status text shared by the stop-run confirm and the
// gateway-move conflict list (sheet.js, principle 5)
// ---------------------------------------------------------------------------

/** "SF7 ✓, SF9 running — SF12 missing · 142 packets" */
export function sweepStatusText(run) {
  if (!run) return '';
  if (!run.sf_schedule || !run.sf_schedule.length) return `${run.packets} packets`;
  const idx = run.segment_index ?? 0;
  const doneParts = run.sf_schedule.slice(0, idx).map(s => `SF${s.sf} ✓`);
  const current = run.sf_schedule[idx] ? [`SF${run.sf_schedule[idx].sf} running`] : [];
  const missing = run.sf_schedule.slice(idx + 1).map(s => `SF${s.sf}`);
  let text = doneParts.concat(current).join(', ');
  if (missing.length) text += ` — ${missing.join('/')} missing`;
  return `${text} · ${run.packets} packets`;
}

// ---------------------------------------------------------------------------
// Start / stop run (selected device) — timed SF-sweep
// ---------------------------------------------------------------------------

/** Whether the "Downlink test" toggle is checked — read fresh on every run
 * start (the checkbox itself isn't reset between renders, see index.html). */
function isDownlinkTestEnabled() {
  const el = document.getElementById('run-downlink-test');
  return el ? el.checked : true;
}

/** Primary one-tap button: 24 h sweep SF7 -> SF9 -> SF12, 5-min interval. */
export async function startSweepDefault() {
  const totalSeconds = 24 * 3600;
  const per = Math.floor(totalSeconds / 3);
  const schedule = [
    { sf: 7,  seconds: per },
    { sf: 9,  seconds: per },
    { sf: 12, seconds: totalSeconds - 2 * per },
  ];
  await startRunWithSchedule({
    duration_seconds: totalSeconds,
    sf_schedule: schedule,
    interval_minutes: 5,
    downlink_test: isDownlinkTestEnabled(),
  });
}

/** "Customize" submit: build a schedule from the duration/interval/preset fields. */
export async function startSweepCustom() {
  const hours       = parseFloat(document.getElementById('run-duration-h').value) || 24;
  const intervalMin = parseInt(document.getElementById('run-interval-min').value, 10) || 5;
  const presetKey   = document.getElementById('run-preset').value;
  const sfList      = RUN_PRESETS[presetKey] || RUN_PRESETS.sf7_sf9_sf12;

  const totalSeconds = Math.max(1, Math.round(hours * 3600));
  const per = Math.floor(totalSeconds / sfList.length);
  const schedule = sfList.map((sf, i) => ({
    sf,
    seconds: i === sfList.length - 1 ? totalSeconds - per * (sfList.length - 1) : per,
  }));

  await startRunWithSchedule({
    duration_seconds: totalSeconds,
    sf_schedule: schedule,
    interval_minutes: intervalMin,
    downlink_test: isDownlinkTestEnabled(),
  });
}

async function startRunWithSchedule(payload) {
  const msg = document.getElementById('selected-msg');
  if (state.selectedNodeId == null) return;
  try {
    const res = await apiFetch('/api/run/start', {
      method: 'POST',
      body: JSON.stringify(Object.assign({ device_node_id: state.selectedNodeId }, payload)),
    });
    if (res.ok) {
      toast('Run started — good luck with the measurement!');
      setMsg(msg, '');
      await loadNodes();
    } else {
      setMsg(msg, `Run not started: ${await extractDetail(res)}`, 'err');
    }
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  }
}

/** Loss aversion: stopping a sweep early is framed as a concrete loss —
 * which SF stages are still missing — before it happens. */
export async function stopSelectedRun() {
  const msg = document.getElementById('selected-msg');
  if (state.selectedNodeId == null) return;
  const node = state.nodesById[state.selectedNodeId];
  const run = node && node.active_run;

  if (run && run.sf_schedule && run.sf_schedule.length) {
    const idx = run.segment_index ?? 0;
    const missing = run.sf_schedule.slice(idx + 1).map(s => `SF${s.sf}`);
    const statusText = sweepStatusText(run);
    const warnLine = missing.length
      ? `Stopping now will leave the <strong>${esc(missing.join('/'))}</strong> data missing.`
      : 'The last stage is almost complete.';
    const ok = await confirmModal({
      icon: '⚠️',
      title: 'Really end the measurement?',
      message: `<p>${esc(statusText)}</p><p>${warnLine} Really end it?</p>`,
      okLabel: 'End measurement',
      cancelLabel: 'Keep running',
    });
    if (!ok) return;
  }

  try {
    await apiJSON('/api/run/stop', {
      method: 'POST',
      body: JSON.stringify({ device_node_id: state.selectedNodeId }),
    });
    toast('Run stopped.');
    setMsg(msg, '');
    await loadNodes();
  } catch (e) {
    setMsg(msg, `Error: ${e.message}`, 'err');
  }
}

// ---------------------------------------------------------------------------
// Run progress — smooth client-side ticking between SSE events, snapped
// back to server truth (segment_index/current_sf/done) whenever a fresh
// /api/nodes payload arrives (loadNodes(), triggered by the 'nodes' SSE
// event or the 30 s ticker).
// ---------------------------------------------------------------------------

/** Recompute elapsed/progress/current segment from wall-clock time for a
 * *running* sweep; done/finished runs just echo the frozen server values. */
export function liveRunProgress(run) {
  if (!run) return { elapsedSeconds: null, progress: null, currentSf: null, segmentIndex: null };
  if (run.status !== 'running' || !run.planned_seconds || !run.started_at) {
    return {
      elapsedSeconds: run.elapsed_seconds,
      progress: run.progress,
      currentSf: run.current_sf,
      segmentIndex: run.segment_index,
    };
  }

  const startedMs = new Date(run.started_at).getTime();
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
  const progress = Math.max(0, Math.min(1, elapsedSeconds / run.planned_seconds));

  let segmentIndex = run.segment_index;
  let currentSf = run.current_sf;
  if (run.sf_schedule && run.sf_schedule.length) {
    let acc = 0;
    for (let i = 0; i < run.sf_schedule.length; i++) {
      acc += run.sf_schedule[i].seconds;
      if (elapsedSeconds < acc || i === run.sf_schedule.length - 1) {
        segmentIndex = i;
        currentSf = run.sf_schedule[i].sf;
        break;
      }
    }
  }
  return { elapsedSeconds, progress, currentSf, segmentIndex };
}

/** Glowing segmented SF-sweep timeline (wow factor) + an anchored label:
 * "SF9 · 2 of 3 SF stages · 14 h of 24 h". Returns '' for a run with no
 * schedule (Phase A fixed run) — caller decides what to show instead. */
export function runProgressHtml(run, opts = {}) {
  if (!run || !run.planned_seconds || !run.sf_schedule || !run.sf_schedule.length) return '';
  const compact = !!opts.compact;

  const live = liveRunProgress(run);
  const idx = live.segmentIndex ?? 0;
  const total = run.sf_schedule.length;
  const sfLabel = live.currentSf != null ? `SF${live.currentSf}` : '—';
  const stepsLabel = `${Math.min(idx + 1, total)} of ${total} SF stages`;
  const timeLabel = fmtHoursOfTotal(live.elapsedSeconds || 0, run.planned_seconds);

  const segs = run.sf_schedule.map((seg, i) => {
    let segState = 'future';
    let fillPct = 0;
    if (run.done || i < idx) {
      segState = 'done'; fillPct = 100;
    } else if (i === idx) {
      segState = 'current';
      const segStart = run.sf_schedule.slice(0, i).reduce((a, s) => a + s.seconds, 0);
      const segElapsed = Math.max(0, (live.elapsedSeconds || 0) - segStart);
      fillPct = Math.max(0, Math.min(100, (segElapsed / seg.seconds) * 100));
    }
    return `
      <div class="sweep-seg ${segState}">
        <div class="sweep-seg-track"><div class="sweep-seg-fill" style="width:${fillPct.toFixed(0)}%"></div></div>
        <div class="sweep-seg-label">SF${seg.sf}${segState === 'done' ? ' ✓' : ''}</div>
      </div>`;
  }).join('');

  const label = run.done
    ? `<strong>done ✓</strong> · ${esc(stepsLabel)} · ${esc(timeLabel)}`
    : `<strong>${esc(sfLabel)}</strong> · ${esc(stepsLabel)} · ${esc(timeLabel)}`;

  return `
    <div class="sweep-timeline${compact ? ' compact' : ''}">${segs}</div>
    <div class="run-progress-label${run.done ? ' done' : ''}">${label}</div>
  `;
}

// ---------------------------------------------------------------------------
// "done ✓" celebration — one-shot pop/glow on the transition to done
// ---------------------------------------------------------------------------

const _prevDone = {}; // { nodeId: bool } — tracks last_run.status==='done' to fire the celebration once

export function checkCelebration(node) {
  if (!node || node.kind !== 'device') return;
  const isDone = !!(node.last_run && node.last_run.status === 'done');
  const was = _prevDone[node.id];
  _prevDone[node.id] = isDone;
  if (isDone && was === false) fireCelebration(node.id);
}

function fireCelebration(nodeId) {
  const card = document.getElementById(`nc-${nodeId}`);
  if (card) {
    card.classList.remove('celebrate-glow');
    void card.offsetWidth;
    card.classList.add('celebrate-glow');
  }
  if (nodeId === state.selectedNodeId) {
    const pill = document.getElementById('sel-run-pill');
    if (pill) {
      pill.classList.remove('celebrate');
      void pill.offsetWidth;
      pill.classList.add('celebrate');
    }
  }
}

// ---------------------------------------------------------------------------
// Wiring (called once from app.js)
// ---------------------------------------------------------------------------

export function initRunControls() {
  document.getElementById('btn-run-stop').addEventListener('click', stopSelectedRun);
  document.getElementById('btn-run-start').addEventListener('click', startSweepDefault);
  document.getElementById('btn-run-start-custom').addEventListener('click', startSweepCustom);
}
