// adr_fixed_dr3.js — WHZ field-test ADR plugin.
//
// Pins every device on this algorithm to DR3 (SF9, EU868) at maximum TX
// power, regardless of link quality. Used for the "Coverage" phase (SF9)
// of the field test, where a fixed spreading factor is mandatory — the
// MClimate Vicki has no device-side ADR/DR command, so the spreading
// factor is held here on the network-server side (ChirpStack v4 ADR plugin,
// selected via the device profile's ADR algorithm). See ADR / feature
// F-0005 (Feldtest-Cockpit) and docs/developer/analysis/test-concept.
export function id() {
  return "fixed_dr3";
}

export function name() {
  return "WHZ fixed DR3 (SF9)";
}

export function handle(req) {
  // Always return the pinned data rate; ChirpStack enqueues a LinkADRReq
  // whenever the device's current DR differs (in either direction).
  return {
    dr: 3, // DR3 = SF9 in EU868
    txPowerIndex: 0, // 0 = max TX power (no attenuation)
    nbTrans: req.nbTrans > 0 ? req.nbTrans : 1,
  };
}
