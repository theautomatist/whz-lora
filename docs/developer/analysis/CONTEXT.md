# whz-lora Economic Viability Study — Glossary

The shared language for the economic viability & sizing study (see
[scope-and-requirements.md](scope-and-requirements.md)). This file is a glossary
**only** — decisions live in ADRs, model mechanics in the model docs. It is
deliberately scoped to the study, not the repo root, to avoid creating a second
root source of truth.

## Language

**Building**:
The unit of analysis — one whole multi-storey building, described by a small
parameter set. An apartment is a degenerate small Building; a campus / portfolio
is a sum of Buildings (out of scope for v1).
_Avoid_: site, property, flat (use "Apartment" only as a Building special case)

**Actuator** (alias: TRV):
A LoRaWAN-native radiator thermostat (thermostatic radiator valve) controlling
one radiator. The only device class in the catalog; proprietary valves are
explicitly excluded.
_Avoid_: thermostat (ambiguous), Stellantrieb (German alias — same thing),
"Homematic device" (not an Actuator — wrong protocol)

**Make**:
The self-built option — a self-operated LoRaWAN network from open-market
components, *including* the cost of running its own administration.
_Avoid_: DIY, "self-hosted" (that describes only the LNS, not the whole option)

**Buy**:
A complete commercial smart-heating system (central hub + thermostats +
app/cloud), evaluated as the benchmark against Make.
_Avoid_: turnkey (fine as an adjective), COTS

**Archetype**:
A named building class bundling a thermal profile (heating-energy intensity +
attributable savings band) and an RF profile (attenuation class → gateway
density). The operator picks one Archetype instead of tuning physical numbers.
_Avoid_: building type (too vague), category

**Baseline**:
The Building's space-heating energy demand before smart control, as an intensity
(kWh/m²·yr) carried by the Archetype. Sets the absolute savings.
_Avoid_: consumption (ambiguous), load

**Savings fraction**:
The share of Baseline energy saved by smart per-room control, as an Archetype
band — reported valve-only and with hydraulic balancing. Conservative
(literature-measured), never vendor-claimed.
_Avoid_: efficiency, reduction rate

**Hydraulic balancing**:
A separate plumbing measure evening radiator flow; roughly doubles the Savings
fraction. A co-measure with its own cost — **not** part of the LoRaWAN system.
_Avoid_: balancing (unqualified)

**Verdict** (alias: economical):
The model's answer for a Building: economical iff payback ≤ horizon. Computed by
back-calculation — the maximum allowable system cost for that payback — for Make
and for Buy.
_Avoid_: profitability, ROI (use payback / NPV precisely)

## Example dialogue

> **Analyst:** For Building Y, how many Actuators?
> **PO:** ~50 radiators, so 50 Actuators.
> **Analyst:** And is this a Make or a Buy comparison?
> **PO:** Both — that's the point. Make is our LoRaWAN network with the existing
> gateway; Buy is e.g. Homematic IP as the benchmark.
> **Analyst:** Note Homematic valves aren't Actuators in our sense — different
> protocol — so they only ever appear on the Buy side, never in the catalog.
