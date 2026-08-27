// state.js — the handful of pieces of state genuinely shared across
// feature modules (the current node list/selection and live per-device
// metrics). Everything else (sheet fields, map markers, event-log filters,
// …) stays a local module-scoped `let` in the module that owns it — see
// cockpit-redesign-spec.md §16 Stage 2, "no behaviour change" — this file
// only relocates existing module-scope `let`s from the old app.js, it does
// not introduce a new state-management layer.
//
// A single mutable object (not exported primitives) so other modules can
// read/write its fields directly (`state.selectedNodeId = id`) without
// needing setter functions — ES module bindings for exported primitives
// are read-only from the importing side, but object field mutation is not.

export const state = {
  nodes: [],       // last GET /api/nodes result
  nodesById: {},   // node.id -> node
  selectedNodeId: null,
  devMetrics: {},  // dev_eui -> { rssi, snr, sf, f_cnt, pdr, acked, downlinks_sent, dl_pdr, lastUplinkAt, intervalSeconds }
  currentView: 'devices', // 'devices' | 'events' | 'radio' | 'map' | 'detail' | 'history' — see view-switch.js
  // eui -> runs (newest first), from GET /api/runs — set by nodes.js's
  // loadNodes(), read by severity.js's computeSeverity/runForActivePlacement
  // (via nodes.js and hero.js). Shared here rather than passed down through
  // render calls because both the device list and the campaign hero need
  // it (cockpit-redesign Stage 2b addendum, spec §7 applied to hero.js).
  runsByEui: {},
};
