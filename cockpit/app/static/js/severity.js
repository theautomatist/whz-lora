// severity.js — cockpit-redesign Stage 2b (spec §7/§9/§20): derives each
// device's need-for-action severity from EXISTING data only. Nothing is
// stored — no schema change, no new column (Tabu list, directive §"Tabu").
//
// The rule (four states, colour never carries meaning alone — text does):
//   red   — the ACTIVE placement has no run at all yet ("never measured"),
//           or its most recent run is still running with zero packets.
//   amber — the ACTIVE placement's most recent run has finished (done or
//           aborted) and the device has not been relocated since.
//   green — the ACTIVE placement's most recent run is running and has
//           received at least one packet.
//   grey  — reserved for `node.retired_at` (does not exist in the schema
//           yet — directive says not to add it in this stage). Unreachable
//           today; the CSS class exists so the state is a defined no-op,
//           not a hole in the system.
// A gateway is not subject to this run-based scale at all — it gets its
// own neutral "info" treatment ("placed N d ago" / "not placed yet").
//
// The critical piece: it is the run that belongs to the CURRENT active
// placement, not the device's last run ever (spec §7's "done ✓ for a run
// that ended 45 days ago in a room the device has since left"). GET
// /api/nodes' `last_run` is the most recent run for the DEVICE, regardless
// of which placement it belongs to — exactly the wrong thing to key
// severity off. `belongs_to_current_placement` is not a field the API
// exposes (and adding one is a backend change this stage avoids — see the
// PR notes) but it is fully derivable client-side: placements are
// sequential, non-overlapping intervals per node (enforced procedurally in
// create_placement, spec §14), so a run belongs to the active placement iff
// it started at or after that placement's own started_at. `node.active_run`
// (if present) always qualifies by construction — a run can only start
// while its device is currently placed.
import { fmtAgeShort } from './format.js';
import { liveRunProgress } from './run.js';

/** Every run for one device (GET /api/runs?node_id=… shape), newest first
 * (as the backend already returns it) → the run belonging to the given
 * active placement, or null if none does. */
export function runForActivePlacement(node, runsForDevice) {
  if (node.active_run) return { run: node.active_run, live: true };
  if (!node.placement || !runsForDevice || !runsForDevice.length) return null;
  const placedAt = new Date(node.placement.started_at).getTime();
  if (isNaN(placedAt)) return null;
  const match = runsForDevice.find(r => new Date(r.started_at).getTime() >= placedAt);
  return match ? { run: match, live: false } : null;
}

/** { severity: 'red'|'amber'|'green'|'grey'|'info', reason: string,
 *    meta: string } — meta is the secondary line (location · packets ·
 * age), reason is the dominant line variant B's cards lead with. */
export function computeSeverity(node, runsByEui) {
  if (node.kind === 'gateway') {
    if (!node.placement) return { severity: 'info', reason: 'not placed yet', meta: '' };
    const ageMs = Date.now() - new Date(node.placement.started_at).getTime();
    return { severity: 'info', reason: `placed ${fmtAgeShort(ageMs)} ago`, meta: locationLine(node.placement) };
  }

  if (node.retired_at) {
    return { severity: 'grey', reason: 'retired', meta: locationLine(node.placement) };
  }

  if (!node.placement) {
    return { severity: 'red', reason: 'not placed yet', meta: '' };
  }

  const placedAgeMs = Date.now() - new Date(node.placement.started_at).getTime();
  const runsForDevice = (runsByEui && runsByEui[node.eui]) || [];
  const found = runForActivePlacement(node, runsForDevice);
  const meta = locationLine(node.placement, found ? found.run : null);

  if (!found) {
    return { severity: 'red', reason: `placed ${fmtAgeShort(placedAgeMs)} ago · never measured`, meta };
  }

  const run = found.run;
  if (run.status === 'running') {
    if (!run.packets) {
      const runAgeMs = Date.now() - new Date(run.started_at).getTime();
      return { severity: 'red', reason: `running · 0 packets for ${fmtAgeShort(runAgeMs)}`, meta };
    }
    const live = liveRunProgress(run);
    const pct = live.progress != null ? Math.round(live.progress * 100) : null;
    const sfPart = live.currentSf != null ? ` · SF${live.currentSf}` : '';
    const reason = pct != null ? `running · ${pct}%${sfPart}` : `running${sfPart}`;
    return { severity: 'green', reason, meta };
  }

  // done | aborted
  const endedAgeMs = Date.now() - new Date(run.ended_at || run.started_at).getTime();
  return { severity: 'amber', reason: `finished ${fmtAgeShort(endedAgeMs)} ago · not relocated`, meta };
}

function locationLine(placement, run) {
  const parts = [];
  if (placement && (placement.floor || placement.room)) {
    parts.push(`${placement.floor || '—'} · ${placement.room || '—'}`);
  } else {
    parts.push('No location recorded');
  }
  if (run) parts.push(`${run.packets} pkt`);
  return parts.join(' · ');
}

/** Sort order for the landing list (spec §7): red, amber, green, grey —
 * need-for-action first, never alphabetical, never by raw run state. The
 * gateway's 'info' card sorts last (it is not a need-for-action item), and
 * within a tier the most recently relevant one first (a stable fallback —
 * Array.prototype.sort is stable since ES2019). */
const SEVERITY_ORDER = { red: 0, amber: 1, green: 2, grey: 3, info: 4 };

export function sortByNeed(entries) {
  return entries.slice().sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
}
