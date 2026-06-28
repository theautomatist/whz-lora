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

**Build constraint (PO).** The self-built option is **pure LoRaWAN** with
**components freely available on the open market** — no proprietary RF.
Proprietary smart-heating systems are *not* excluded from the study; they enter
as the **buy** side of a make-vs-buy comparison (see below and RQ7), benchmarked
against the self-built network's cost *and* its administration/operation overhead.

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

### Make vs. buy (comparison axis)

The verdict (F) is computed for **two scenarios** and compared:

- **Make** — a self-operated **LoRaWAN** network from open-market components
  (blocks A–E), *including* the cost of running its own management /
  administration (LNS hosting, provisioning, monitoring).
- **Buy** — a complete **commercial** smart-heating system (e.g. Homematic IP
  and alternatives): central gateway/bridge + radiator thermostats + app/cloud.
  What is in the box, per-building cost, protocol, recurring/cloud cost and who
  administers it are researched in RQ7.

The make side is open LoRaWAN by deliberate choice; proprietary systems live on
the buy side. The comparison is a core output of the study, not a footnote.

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

## 6. Decisions from the grill

Resolved during the grill (recorded in [ADR-0020](../decisions/adr-0020.md),
[ADR-0021](../decisions/adr-0021.md) and the [model design](model.md); glossary in
[CONTEXT.md](CONTEXT.md)). Items marked **[PO]** are policy defaults — runnable but
overridable.

1. **Unit of analysis** — one whole Building, parametric; apartment = small
   Building; campus = sum of Buildings (out of scope v1).
2. **Parameters** — minimal operator set: archetype, actuator count, energy price,
   horizon, balancing flag. The verdict is **per radiator** (size cancels for the
   yes/no); size is kept only for absolute € and gateway sizing.
3. **Building scope** — 3–4 named **archetypes**, each bundling a thermal and an RF
   profile; everything else defaults + a sensitivity (tornado) check.
4. **Device catalog** — Make uses **LoRaWAN-native actuators only**; proprietary
   systems live solely on the Buy side (ADR-0020).
5. **Benefit** — energy-cost savings only in v1 (comfort / labour noted, not
   monetised); conservative literature savings, not vendor claims; **hydraulic
   balancing** modelled as an explicit on/off co-measure (≈ doubles savings, has
   its own cost).
6. **Verdict** — back-calculation: max allowable cost for payback ≤ horizon;
   headline = simple payback, NPV as a check.
7. **Make admin/ops** — included (LNS hosting, provisioning, monitoring); the
   one-time integration is largely the already-built provisioning app (F-0005).
8. **Buy benchmark** — Homematic IP CCU3 as the anchor + one professional
   alternative; compared at whole-floor and whole-building size, respecting hub
   ceilings.
9. **Model build** — KISS parametric model (Python notebook + module); simulators
   (ns-3 / FLoRa) reserved for later RF calibration only (ADR-0021).
10. **Team / concept paper** — no new specialist (KISS); fold the study purpose
    into the concept paper via `/onboarding` after the model v1 exists.
11. **Output** — interactive HTML + static PDF report.
12. **[PO]** Perspective = institutional owner-operator (no split incentive);
    horizon = 10 yr; energy price = €0.12/kWh; discount = 3%. Real target buildings
    **X / Y still to be named** by the PO to instantiate the model.

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
- **RQ7 → F (buy side):** turnkey commercial smart-heating systems (Homematic IP
  and alternatives) — what is included, protocol, per-building cost, recurring /
  cloud cost, administration model — as the make-vs-buy benchmark.

## 8. Geplante Folgephasen (nach der Report-Überarbeitung)

PO-Direktive 2026-06-14. Nach der Verständlichkeits-Überarbeitung von Report A/B
(`report-a-prozesskette`, `report-b-kostenanalyse`) sind zwei Schritte vorgesehen:

1. **Fragenkatalog** — ein Workflow leitet aus Report A + B ab, *welche
   Informationen nötig sind, um für ein konkretes Gebäude eine verbindliche
   Kostenkalkulation zu erstellen*. Beispiel-Fragen: Räume gesamt; Größe je Raum;
   Heizkörper je Raum; Heizkörper gesamt; Baumaterial; Strom im Treppenhaus
   vorhanden; Wände verputzt; Auf-/Unterputz; Entfernung Raum ↔ Treppenhaus; …
   **✅ Erledigt:** [`fragenkatalog.md`](fragenkatalog.md) / `fragenkatalog.pdf`
   (Abschnitte A–F, ~50 Fragen, je an einen Modellparameter gekoppelt, vor-Ort-Punkte
   markiert).
2. **Entscheidungs- & Messplan-System** — ein Workflow entwickelt aus dem
   *beantworteten* Katalog ein System, das **Entscheidungen ableitet** (z. B.
   „Raum X liegt weit vom Treppenhaus → Begehung nötig; der Techniker bringt
   1 Gateway + 3–5 Aktoren zum Funktest mit, um die Abdeckung zu prüfen und zu
   klären, ob ein Zweit-Gateway oder eine andere Antenne nötig ist"). Es markiert,
   **welche Punkte der Katalog nicht abdecken kann** und vor Ort gemessen werden
   müssen → ein **Messplan / Validierungsplan** für die physische Welt.
