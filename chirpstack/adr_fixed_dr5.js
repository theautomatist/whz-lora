// adr_fixed_dr5.js — WHZ field-test ADR plugin.
//
// Pins every device on this algorithm to DR5 (SF7, EU868) at maximum TX
// power. Used as the first ("Screening") segment of the F-0006 Phase-B
// auto-SF-sweep (SF7 → SF9 → SF12). Fixed SF is held network-server-side
// because the MClimate Vicki has no device-side DR command; selected via the
// device profile's ADR algorithm. See feature F-0006.
export function id() {
  return "fixed_dr5";
}

export function name() {
  return "WHZ fixed DR5 (SF7)";
}

export function handle(req) {
  return {
    dr: 5, // DR5 = SF7 in EU868
    txPowerIndex: 0, // 0 = max TX power (no attenuation)
    nbTrans: req.nbTrans > 0 ? req.nbTrans : 1,
  };
}
