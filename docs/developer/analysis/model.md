# Economic & Sizing Model — Design (DRAFT)

> Blueprint from the grill, recorded in [ADR-0021](../decisions/adr-0021.md).
> All numbers below are **explicit default assumptions** to be refined in Phase 3
> (deep research) and Phase 4 (testbed calibration). Not yet implemented. Sources
> for every figure are in [preliminary-research.md](preliminary-research.md).

## 1. What the model computes

Inputs → two outputs:

- **Sizing** — number of gateways for a Building.
- **Verdict** — economical yes/no + cost ceiling, for **Make** and for **Buy**.

## 2. Inputs (tiered by influence)

| Tier | Inputs | Role |
|---|---|---|
| **1 — drive the yes/no** | archetype, energy_price (€/kWh), horizon (yr), balancing flag | the per-radiator verdict |
| **2 — scale & sizing** | actuator_count, floors, footprint_m² | absolute € and gateway count |
| **3 — constants (defaults, sensitivity-checked)** | cost_per_actuator, install_per_actuator, gateway_cost, battery_interval_yr, discount_rate, m²_per_radiator | rarely touched |

## 3. Building archetypes (default assumptions)

Each archetype bundles a **thermal** profile and an **RF** profile.

| Archetype | Heating intensity (kWh/m²·yr) | Savings: valve-only / +balancing | RF class | Gateway density (rule of thumb) |
|---|---|---|---|---|
| **A — Modern / new-build** | 40–70 | 3–5% / 6–10% | hostile (low-E glass, metallised insulation) | ~1 per 2–3 floors |
| **B — Renovated mid-century** | 80–120 | 5–8% / 10–15% | moderate (concrete + insulation) | ~1 per 3–4 floors |
| **C — Old, unrenovated (pre-1980 brick)** | 150–250 | 8–12% / 15–22% | mild (brick attenuates less) | ~1 per 4–5 floors |
| **D — RC institutional (1960s–70s, the likely WHZ case)** | 120–180 | 10–15% / 18–25% | heavy (~10 dB/floor reinforced concrete) | ~1 per 3–5 floors |

Savings bands are **conservative, literature-measured** (not vendor claims):
valve-only ≈ honest controlled benchmarks; *+balancing* ≈ doubling per Szczotka.
Savings are highest where insulation is worst (C/D) and where room usage is
irregular (D, institutional) — which is exactly whz-lora's target.

## 4. Equations

Per-radiator (the verdict path):

```
baseline_per_radiator   = intensity × m²_per_radiator                # kWh/yr
benefit_per_radiator    = baseline_per_radiator × savings × price    # €/yr
cost_per_radiator(Make) = cost_per_actuator + install_per_actuator   # €
payback_per_radiator    = cost_per_radiator / benefit_per_radiator   # yr
economical              ⇔ payback_per_radiator ≤ horizon
cost_ceiling_per_radiator = benefit_per_radiator × horizon           # (NPV variant uses discount_rate)
```

`savings` = valve-only or +balancing per the flag. `m²_per_radiator` defaults to
~15 (near-constant; a Tier-3 knob).

Absolute path (totals & sizing):

```
gateways      = sizing(RF class, floors, footprint)   # at WHZ marginal cost = 0 (gateway already owned)
Make_CAPEX    = actuator_count × (cost+install) + gateways × gateway_cost [+ balancing cost if flag]
Make_OPEX/yr  = battery_replacements + LNS_hosting + admin_labour
Buy_CAPEX/OPEX = from RQ7 per chosen benchmark, respecting hub ceilings
NPV, payback   over horizon at discount_rate
```

## 5. Make-side administration & operations (the PO's "Verwaltung")

Make explicitly carries its own running cost:

- **One-time integration** — the provisioning workflow. For whz-lora this is
  largely the **already-built provisioning app (F-0005)** → mostly *sunk*, not a
  fresh cost. This is a key reason Make is cheap for WHZ specifically.
- **LNS self-hosting** — runs on the existing host (whole stack ~190 MB RAM idle,
  fits a Raspberry Pi 4) → ~0 marginal.
- **Ongoing** — provisioning new actuators, monitoring online/offline state
  (small labour line).

## 6. Worked sanity check (defaults, illustrative only)

| Case | baseline/radiator | × savings × €0.12 | benefit/yr | cost/radiator | payback |
|---|---|---|---|---|---|
| **C — old** | 200 × 15 = 3000 kWh | × 10% | €36 | €110 | **~3 yr ✓** |
| **A — modern** | 50 × 15 = 750 kWh | × 4% | €3.6 | €110 | **~30 yr ✗** |

The model discriminates correctly out of the box — it reproduces the literature
(pays back in poorly-insulated buildings, not in well-insulated ones). This is
evidence the parameter choice is right, **not** a result claim.

## 7. Sizing model (RF) — v1

Link budget (SF7 −123 dBm … SF12 −137 dBm, ~157 dB budget at SF12) minus a
multi-wall / multi-floor path-loss term (published 868 MHz parameters) → coverage
per gateway → count, with a fade-margin reserve (~25.7 dB for 99% PDR). Calibrate
later (Phase 4) with real whz-lora RSSI/SNR; ns-3 `signetlabdei/lorawan` optional
for a second opinion. No fresh measurement campaign for v1.

## 8. Open PO defaults (runnable, override anytime)

| Knob | Default | Note |
|---|---|---|
| Perspective | institutional owner-operator | no split incentive (owner = bill-payer); rented-residential split mode is a later variant |
| Horizon | 10 yr | matches device lifetime + the German break-even study frame |
| Energy price | €0.12 / kWh | conservative German institutional gas/district-heat; **confirm** |
| Discount rate | 3% | institutional |
| **Target buildings X / Y** | **TBD** | name 1–2 real WHZ buildings to instantiate the model |

## 9. Input presets — the interactive front-end

The model is driven from an HTML page: free-entry fields for what the user knows,
plus **two preset dropdowns** that load defaults for the rest (KISS: unsure → load
a preset, then override what you know). The two axes are **orthogonal** — a
medium-size building can be Neubau or Altbau.

**Axis 1 — Size tier** (scale → actuator_count, floors, footprint). The PO's three
exemplary scenarios:

| Tier | Example class | Dwelling units | Floors | Living area (m²) | Radiators |
|---|---|---|---|---|---|
| **Klein** | Mehrfamilienhaus | TBD | TBD | TBD | TBD |
| **Mittel** | Größerer Wohnkomplex | TBD | TBD | TBD | TBD |
| **Groß** | Bürokomplex / Super-Komplex | TBD | TBD | TBD | TBD |

**Axis 2 — Construction / age** (type → archetype = intensity + savings + RF class):

| Preset | Archetype (§3) | Era / method | Intensity | RF class |
|---|---|---|---|---|
| **Neubau** | A modern | GEG / Effizienzhaus, concrete frame | TBD | TBD |
| **Saniert** | B renovated | retrofit insulation | TBD | TBD |
| **Altbau** | C old | pre-1980 masonry | TBD | TBD |
| **Plattenbau / RC** | D institutional | 1960s–70s reinforced concrete | TBD | TBD |

`TBD` defaults are filled by the **building-typology deep-research** (IWU TABULA,
Destatis / Zensus 2022, BBSR non-residential typology). Every preset value stays
editable; presets are a starting point, not a constraint.
