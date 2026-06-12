# Economic Viability & Sizing Study — Scope & Requirements (DRAFT)

> **Status: draft for the grill session.** This document structures the Product
> Owner's intent so we have a concrete thing to interrogate. Every *Open question*
> in §6 is to be resolved in the grill, then refined into a proper analysis
> structure. This is **not yet a committed directive** and not yet reflected in
> the concept paper.

## 1. Why this exists — the real purpose behind whz-lora

The whz-lora ChirpStack stack is not an end in itself. It is the **measurement
instrument** for a study:

> **For a given building, is LoRaWAN-based heating control economically
> worthwhile — yes or no — and within which cost envelope does it stay
> worthwhile?**

The [concept paper](../concept/concept-paper.md) currently frames whz-lora
generically as a *Forschungs-Sensorik LoRaWAN-Basis*. This document records the
concrete research purpose behind it: **sizing and economic assessment of
LoRaWAN heating control for whole buildings.** Whether to fold this purpose into
the concept paper proper (a `/onboarding` revision) is itself an open question
(§6.6) — flagged here, not decided.

## 2. Nature of the answer

- **A dynamic model, not a single number.** Parameters in (building, hardware,
  prices, savings) → economic verdict out. Conservative, transparent, every
  assumption explicit. A "rough, cautious estimate", never a final guarantee.
- **Back-calculation.** The verdict is computed *inversely*: given the
  achievable benefit (energy/cost savings for that building), what is the
  **maximum allowable system cost** for the investment to pay back within a
  chosen horizon? Then: does real hardware + installation cost fit under that
  ceiling? → economical: yes / no.
- **The testbed calibrates it.** Real RSSI/SNR/coverage measurements from
  whz-lora ground and refine the model's RF side over time.

## 3. Model decomposition

The model is assembled from parameter blocks. Each block is a building-specific
input, a research-grounded catalog, or a computed result.

| Block | Name | Kind | Feeds |
|---|---|---|---|
| A | Building model | input (the "building X / Y") | B |
| B | RF / coverage model | research + testbed | number of gateways |
| C | Hardware catalog | research | cost |
| D | Cost model (CAPEX + OPEX) | computed | verdict |
| E | Benefit model (energy savings) | research + assumptions | verdict |
| F | Economic verdict | computed (back-calculation) | the answer |

### A — Building model (the independent variable)
- Construction era / type (modern low-energy, post-war concrete, old brick, mixed).
- Materials that drive RF loss (reinforced concrete, brick, steel, glass facade,
  **metal-foil insulation** — a strong attenuator).
- Geometry (floors, area per floor, basement, layout).
- Heating topology: radiators per room, rooms → **actuator count**.

### B — RF / coverage model (the technical crux)
- In-building path loss & penetration by material / floor (literature + own
  measurements).
- Link budget per *gateway × antenna × device* combination
  (EU868: TX ≤ 14 dBm / 25 mW + duty cycle, managed by the LNS).
- → coverage per gateway → **number of gateways needed** (with margin) to reach
  every actuator.

### C — Hardware catalog (parametric, research-grounded)
- **Gateways:** indoor / outdoor, channel count, TX power, RX sensitivity,
  antenna options, € price (Kerlink iFemtoCell Evolution as the reference unit).
- **Antennas:** internal vs. external connector, gain (dBi), placement, cable
  loss — the PO's explicit *externer Antennenanschluss* interest.
- **Devices:** LoRaWAN radiator thermostats / actuators — class, battery life,
  € price. *Open:* does a real LoRaWAN-native TRV market exist, or is it mostly
  proprietary 868 MHz (e.g. Homematic) needing a bridge? → RQ4.

### D — Cost model
- **CAPEX** = gateways + antennas + devices (counts from A/B × unit prices from
  C) + installation labour.
- **OPEX** = maintenance (battery-replacement cadence × labour) + backhaul +
  LNS hosting / operations.

### E — Benefit model
- Energy / cost savings from smart, zoned, per-room / per-radiator control
  (€/year) — from literature + per-building assumptions.

### F — Economic verdict
- Back-calculation: maximum allowable cost for payback ≤ horizon; compare to D.
- Sensitivity analysis across the levers (§4).

## 4. Evaluation lenses — perspectives × levers

Every design choice is judged from five stakeholder perspectives against four
levers (matrix filled during the analysis):

- **Perspectives:** User · Operator · Maintenance · Installation · Manufacturer
- **Levers:** Cost · Speed · Robustness · Scalability

These structure *which* parameters matter and surface trade-offs; they are an
analytical lens over blocks D/E, not separate models.

## 5. Explicitly out of scope (for now)

- Room / apartment assignment of devices (possibly a later third-party tool).
- Mobile / camera / QR provisioning UI work (deferred; separate track).
- A final, authoritative cost statement — the model gives conservative
  estimates, not guarantees.

## 6. Open questions for the grill

Each becomes a decision; a recommended default is noted.

1. **Payback horizon** for "economical" — device lifetime (~10 yr)? an
   institutional threshold? *Rec: parameterise; default 5–10 yr.*
2. **Building scope** — a fixed set of archetypes, or fully parametric?
   *Rec: 3–4 archetypes plus parametric inputs.*
3. **Whose money** — CAPEX by the operator (WHZ) vs. benefit to the tenant; who
   pays, who saves? *Rec: model both; default operator-funded.*
4. **Benefit definition** — energy saved only, or also comfort / labour /
   monitoring value? *Rec: start energy-only, note the rest.*
5. **Device reality** — LoRaWAN-native TRVs vs. proprietary + bridge?
   *Rec: resolve via RQ4 before fixing the catalog.*
6. **Concept-paper / team impact** — does this purpose warrant an `/onboarding`
   revision and/or a research specialist agent (RF + economics)?
   *Rec: decide after the preliminary research.*
7. **Output format** — interactive HTML + PDF report (the PO wanted both).
   *Rec: confirm in the grill.*

## 7. Preliminary research questions (founded briefs)

Each is tied to a model block and run as a **preliminary sweep before the
grill** — to ground the discussion in evidence, not guesswork ("nicht ins
Blaue").

- **RQ1 → B:** in-building LoRa/LoRaWAN propagation & coverage — range,
  penetration loss per wall / floor / material, gateways-per-area rules of
  thumb. Papers EN/DE, arXiv, IEEE, measurement datasets.
- **RQ2 → C:** indoor LoRaWAN gateway hardware — types, EU868 TX power, RX
  sensitivity, antenna options, price ranges.
- **RQ3 → C:** indoor LoRa antenna technique — internal vs. external, gain,
  placement, cable loss; realistic indoor gains.
- **RQ4 → C:** LoRaWAN radiator thermostat / actuator market — models, LoRaWAN
  class, battery life, price; LoRaWAN-native vs. proprietary + bridge.
- **RQ5 → E:** energy-savings evidence for smart / zoned heating control —
  typical % / € savings, payback periods.
- **RQ6 → model:** open datasets, path-loss models, and simulators / GitHub
  repos for LoRa coverage & link budget that the dynamic model could reuse.
