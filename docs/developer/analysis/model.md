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
irregular (D, institutional) — which is exactly whz-lora's target. Representative
per-preset defaults (intensity, sizes, radiator counts) are locked in
[building-typology.md](building-typology.md).

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
~20 (near-constant; a Tier-3 knob; [building-typology.md](building-typology.md)).

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
| **C — Altbau** | 160 × 20 = 3,200 kWh | × 10% | €38 | €110 | **~3 yr ✓** |
| **A — Neubau** | 70 × 20 = 1,400 kWh | × 4% | €6.7 | €110 | **~16 yr ✗** |

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
| Energy price | €0.12 gas / €0.16 Fernwärme | sourced (§10); the **energy source is the decisive swing** |
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
| **Klein** | Mehrfamilienhaus | 7 | 4 | 500 | 35 |
| **Mittel** | Größerer Wohnkomplex | 22 | 6 | 1,500 | 120 |
| **Groß** | Bürokomplex / Super-Komplex | — | 6 | 1,800 | 92 |

**Axis 2 — Construction / age** (type → archetype = intensity + savings + RF class):

| Preset | Archetype (§3) | Era / method | Intensity (kWh/m²·yr) | RF class |
|---|---|---|---|---|
| **Neubau** | A modern | GEG / Effizienzhaus, masonry/timber + WDVS | 70 | hostile (low-E) |
| **Saniert** | B renovated | retrofit WDVS insulation | 90 | moderate |
| **Altbau** | C old | pre-1949 solid brick | 160 | mild (brick) |
| **Plattenbau / RC** | D institutional | 1958–90 reinforced-concrete sandwich | 140 | heavy (RC) |

Defaults and their sources are in [building-typology.md](building-typology.md)
(IWU TABULA, Destatis / Zensus 2022, ista, Heizspiegel). Every preset value stays
editable in the **[calculator](model-calculator.html)**; presets are a starting
point, not a constraint. The full print/PDF study report is **[report.html](report.html)**
(includes the virtual-company process chain, cost flow and full-cost vs. core-cost analysis).

## 10. Cost inputs (sourced defaults)

The initial placeholder constants are replaced with researched German figures.
**Cost per radiator (device + install) stays ~€110** — the cheaper bulk device
exactly offsets the higher install labour, so the headline paybacks barely move;
what moves is the *balancing* scenario and the *energy source*.

| Input | Placeholder | Sourced default | Range | Conf. | Source |
|---|---|---|---|---|---|
| LoRaWAN TRV (€/valve, building scale, ex-VAT) | 90 | **70** | 50–82 | med | [m2mgermany](https://www.m2mgermany.de/shop/produkt/wt101-868m-smartes-heizkoerper-thermostat); [Concept13 ladder](https://www.concept13.co.uk/shop/sensors/heating/vicki-lorawan-trv-heating-control/) |
| Install / valve (head swap + provisioning, batched) | 20 | **40** | 30–60 | med | [enpal head-swap](https://www.enpal.de/waermepumpe/thermostat-wechseln) |
| Hydraulic balancing (€/radiator, Verfahren B, pre-subsidy) | 25 | **75** | 50–120 | high | [co2online](https://www.co2online.de/energie-sparen/heizenergie-sparen/hydraulischer-abgleich/hydraulischer-abgleich-kosten-amortisationszeit/); [Finanztip](https://www.finanztip.de/hydraulischer-abgleich/) |
| Energy — gas (€/kWh, all-in institutional) | 0.12 | **0.12** | 0.09–0.13 | high | [Destatis H2 2025](https://www.destatis.de/DE/Presse/Pressemitteilungen/2026/03/PD26_111_61243.html); [BDEW](https://www.bdew.de/service/daten-und-grafiken/bdew-gaspreisanalyse/) |
| Energy — district heating (€/kWh, Arbeitspreis) | 0.12 | **0.16** | 0.08–0.20 | high | [vzbv median 17 ct](https://www.vzbv.de/pressemitteilungen/teure-fernwaermepreise-verbraucherzentrale-fordert-preisdeckel); [DIW Wärmemonitor 2024](https://www.diw.de/de/diw_01.c.990772.de/publikationen/wochenberichte/2025_49_1/waermemonitor_2024__nach_energiekrise_entwickeln_sich_preise_der_heizenergietraeger_sehr_unterschiedlich.html) |

**Decisive swing = the energy source.** Benefit scales linearly with price; a
Fernwärme building (€0.16) has ~30 % more annual benefit than a gas one (€0.12)
and can flip a borderline Altbau from ✗ to ✓. Still soft: bulk TRV pricing is
login-gated (estimated −10–15 %), install is a batch figure, Fernwärme is a local
monopoly price (factor-2 spread) — a real WHZ quote hardens all three.

## 11. Open refinements (WF3 audit)

For a **binding** (not preliminary) verdict, several single numbers must be decomposed
into their drivers — recorded here so the model stays honest:

- **Savings net, not gross:** gross band − rebound (20–30 %) = net ~6–9 % (Altbau); run the
  *net* band through the payback, relative to the declared baseline control state (not the
  vendor's inflated baseline).
- **Energy price:** working-price band (gas 0.09–0.13 / district heating 0.08–0.20) **plus**
  a separate base fee (not reducible by savings) + price trajectory (CO₂/BEHG) + generation
  efficiency (1 saved kWh of heat avoids >1 kWh of fuel at an ~85 % boiler).
- **Install (§10):** model as a *sum* (mobilisation + swap labour + provisioning +
  p(proprietary) × adapter/valve-body surcharge), not a flat figure.
- **OPEX:** a driver model instead of flat lines (battery 4–10 yr; monitoring bottom-up
  ~200–400 €/yr; software maintenance and incident handling as own lines; hosting case-dependent).
- **m² per radiator:** a residential/office pair, band 15–25; for office/university a
  "radiator-heated?" gate + radiator count instead of area/20.
- **RF figures:** flag every value as 868-MHz **extrapolated**; replace the categorical
  RF-class token with a range-based sizing until measured. Calibration: the
  [test concept](test-concept.pdf) measures dB/floor, Low-E attenuation and the SF12 reserve
  at the real new building.
- **Payback:** also report *discounted* (3 %); use device lifetime (4–10 yr) as a cut-off
  ("payback below the shortest plausible lifetime").
