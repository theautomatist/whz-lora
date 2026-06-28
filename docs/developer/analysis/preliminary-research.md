# Preliminary Research Findings

> **Status: preliminary research complete — input for the grill.** Founded
> pre-grill evidence for the [economic viability & sizing study](scope-and-requirements.md).
> Make side = RQ1–RQ6 sweep (7 research agents); buy side = RQ7. Figures are
> indicative retail / literature values **with sources**, not procurement quotes
> or final model outputs.

## Bottom line for the PO

- **The make side is buildable with real, open-market LoRaWAN components** —
  LoRaWAN-native radiator valves exist as off-the-shelf Class A products
  (MClimate Vicki, dnt LW-eTRV, Eurotronic Stella R/Pro, Milesight WT101,
  Micropelt/DEOS energy-harvesting), ~€67–190/valve, and the Vicki has a
  documented **ChirpStack v4 downlink codec** — directly reusable on the whz-lora stack.
- **"Homematic is not LoRaWAN"** is confirmed and load-bearing: it is proprietary
  BidCos 868 MHz with **no LoRaWAN bridge for actuators**. It stays purely on the
  *buy* side; it cannot enter a LoRaWAN device catalog.
- **The WHZ already owns the gateway + ChirpStack**, so the marginal infrastructure
  cost of adding TRVs is ~0. The make-side cost collapses to *valves + one-time
  integration*; consumer turnkey systems are cheaper per valve but cap at 12–250
  devices/hub and carry cloud/subscription/lock-in risk.
- **The economics are tighter than vendor claims suggest.** Honest controlled
  savings are 3.5–10% for valves alone (≈20% only *with hydraulic balancing*), but
  the German break-even is only **5.7–7.7%** — so the case is plausible, not
  guaranteed, and **hinges on hydraulic balancing and building type**.
- **The dynamic model can be built on existing open tooling** (ns-3 lorawan, FLoRa,
  published 868 MHz indoor path-loss parameters, downloadable datasets) — **no fresh
  measurement campaign is required** to start.

## Executive summary

LoRaWAN-based heating control for whole buildings is technically and commercially
feasible, but the economics hinge on construction type and on whether smart valves
are paired with hydraulic balancing. Indoor 868 MHz propagation is well characterised
by peer-reviewed measurement campaigns (path-loss exponent n ≈ 1.7–4.6, ~10 dB per
concrete floor, 15–20 dB per reinforced-concrete wall), and empirical evidence
suggests one indoor gateway covers roughly one floor every ~5 floors / ~30 m in heavy
multi-floor buildings, up to a whole ~30 000 m² single-floor hall in light
construction. LoRaWAN-native radiator valves genuinely exist as Class A products from
multiple vendors (≈€67–190/valve) but are squarely targeted at commercial/institutional
buildings — the consumer market is owned by non-LoRaWAN protocols (Homematic IP BidCos,
Zigbee, DECT ULE), a load-bearing nuance for any device catalog. Measured energy
savings cluster at 3–25% (most honest controlled benchmarks: 3.5% for zoning added to
already-programmed systems; ~20% only when TRVs are combined with hydraulic balancing),
with German break-even thresholds of just 5.7–7.7%. Mature open tooling exists for the
RF/coverage block (ns-3, FLoRa, LoRaSim, open datasets), so the sizing model can be
built largely on existing artefacts rather than a fresh measurement campaign.

## Make side — open LoRaWAN (RQ1–RQ6)

### B — RF / coverage

**Path-loss exponent (n) at 868 MHz indoor.** Fitted single-floor office: n = 3.85,
with brick-wall attenuation 6.87 dB and wood-partition 2.01 dB, shadowing sigma 7–8 dB,
R² = 0.82–0.86 ([arXiv 2510.04346](https://arxiv.org/html/2510.04346v1)). A
COST231-style multi-wall fit gives n = 2.85, per-wall loss 1.41 dB, per-floor loss
10 dB ([COMPLETE H2020](https://complete-h2020network.eu/sites/default/files/upload/2019-11/08739575%20Empirical%20indoor%20propagation%20models%20for%20LoRa%20radio%20link%20in%20an%20office%20environment.pdf)).
Indoor corridor (NLOS): n = 1.96–3.01, sigma 2.16–4.47 dB
([PMC10055865](https://pmc.ncbi.nlm.nih.gov/articles/PMC10055865/)). A literature
review spans n = 2.1–7.7, RMSE 2.47–18.35 dB across indoor studies
([PMC11207269](https://pmc.ncbi.nlm.nih.gov/articles/PMC11207269/)).

**Per-floor / per-material attenuation.** COST231-fitted ~10 dB/floor at 868 MHz;
FAF = 5.52 dB/floor measured at 433 MHz in a 4-storey university building (lower-bound
proxy for 868 MHz) ([PubMed 41755093](https://pubmed.ncbi.nlm.nih.gov/41755093/)).
ITU-R P.1238-9: ~9 dB for the first floor, softening above
([ITU-R P.1238-9](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.1238-9-201706-I!!PDF-E.pdf)).
NIST IR 6055 at 900 MHz (directly applicable to EU868): 10 cm concrete ~12 dB, 9 cm
brick ~3.5 dB, lumber 2.8 dB, plain glass ~2 dB
([NIST IR 6055](https://www.nist.gov/publications/electromagnetic-signal-attenuation-construction-materials)).
Double-mesh reinforced-concrete wall (25 cm): 15–20 dB at 900 MHz
([Academia.edu](https://www.academia.edu/27011705/Attenuation_Measurements_for_Double_Mesh_Reinforced_Concrete_Walls_at_the_900_MHz_Cellular_Band)).
Low-emissivity glass: 35–60 dB — a near-blocker (low confidence; from patent/5G
literature, not LoRa measurements)
([US Patent 8,927,069](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/8927069)).
Exterior building-entry loss ~30 dB mean (sigma ~8 dB) at 460–880 MHz
([SmartMakers](https://smartmakers.io/en/lorawan-range-part-2-range-and-coverage-of-lorawan-in-practice/)).

**Single-gateway coverage / gateway density.** Upper bound: one 868 MHz gateway
covered ~30 000 m² of a single-floor industrial hall at SF12, PDR 96.7%
([Haxhibeqiri et al., IEEE 2018](https://www.researchgate.net/publication/322322331_LoRa_indoor_coverage_and_performance_in_an_industrial_environment_Case_study)).
Densest empirical evidence: 390 nodes, 4 gateways, 8 floors, 86 M transmissions over
2 years → robust coverage needs ~1 gateway per 5 floors and per ~30 m horizontally
([ScienceDirect, DISN 2022](https://www.sciencedirect.com/science/article/pii/S1574119222000700)).
A single central gateway gave decodable signal across a 4-storey brick/concrete
building (RSSI −62 to −99 dBm)
([RAK Wireless](https://news.rakwireless.com/signal-mapping-in-a-building-a-lorawan-experiment/)).
Higher SFs compensate for floor penetration: Duisburg basement PDR rose from 62% at
SF7 to 100% at SF10–12
([Duisburg study](https://www.researchgate.net/publication/327635518_Analysis_of_LoRaWAN_technology_in_an_Outdoor_and_an_Indoor_Scenario_in_Duisburg-Germany));
SF10 recommended for a 9-floor concrete building, and 868 MHz beat 433 MHz on PDR
([Bobkov et al., MWENT 2020](https://ieeexplore.ieee.org/document/9067427/)).
Practitioner rules (low confidence, vendor): 1 gateway per 4–5 floors of ~900 m²
([Tektelic](https://tektelic.com/expertise/iot-building-coverage-tips-and-techniques-for-success/)).

**Link budget / fade margin.** SF7 sensitivity −123 dBm, SF12 −137 dBm (~2.5 dB/SF
step, 14 dB span ≈ 1–2 extra concrete floors); ~157 dB total budget at SF12 with
14 dBm + 3 dBi ([Hubble link-budget guide](https://hubble.com/community/guides/how-to-calculate-lorawan-link-budget/)).
Calibrated fade margin for 99% PDR indoors: 25.7 dB
([arXiv 2510.04346](https://arxiv.org/html/2510.04346v1)). Environmental factors
(temp/humidity/CO2/PM) shift attenuation by up to 10.58 dB
([arXiv 2505.06375](https://arxiv.org/html/2505.06375v1)).

> **Gap / low-confidence:** No peer-reviewed *868 MHz* per-floor FAF in
> reinforced-concrete buildings was found — the 10 dB/floor figure is secondary-sourced.
> Low-E glass and metallised-insulation (Passivhaus) attenuation are not LoRa-measured.
> No study covers mixed-construction buildings (RC skeleton + light partitions), the
> dominant German university/office type. Gateway-per-m² sizing rests on vendor rules +
> one DISN building, not a first-principles methodology.

### C — Hardware (gateways, antennas, devices)

**Gateways (EU868, indoor).** All surveyed indoor gateways are **8-channel**
(8×125 kHz multi-SF + 1×FSK); no indoor 16-channel unit exists in this price class —
the 16-channel RAK7289V2 is outdoor only
([RAK store](https://store.rakwireless.com/products/rak7289-8-16-channel-outdoor-lorawan-gateway)).
Price band ~€100–450, SF12 RX sensitivity −137 to −141 dBm.

| Gateway | Chipset | TX | RX @ SF12 | Price | Source |
|---|---|---|---|---|---|
| MikroTik wAP LR8G | SX1301 | 14 dBm | −137 dBm | ~€102 ex-VAT | [MikroTik](https://help.mikrotik.com/docs/pages/viewpage.action?pageId=27131931) |
| RAK WisGate Edge Lite 2 (RAK7268V2) | SX1302 | 27 dBm | −139 dBm | €139–154 ex-VAT | [RAK](https://docs.rakwireless.com/product-categories/wisgate/rak7268v2/datasheet/) |
| Dragino LPS8N | SX1302 | n/p | −140 dBm | €142.68 incl. VAT | [iot-shop.de](https://iot-shop.de/en/shop/dragino-lps8n-indoor-lorawan-gateway-5609) |
| Kerlink iFemtoCell Evolution | SX1302 | 5–24 dBm cond. (≤27 dBm EIRP) | −140/−141 dBm | €227–321 | [Choovio](https://www.choovio.com/product/kerlink-wirnet-ifemtocell-evolution-lorawan-gateway/) |
| Tektelic KONA Micro Gen 2 | — | 14–27 dBm | −139.5/−141 dBm | €434 incl. VAT | [iot-shop.de](https://iot-shop.de/en/shop/tektelic-kona-micro-gen-2-iot-gateway-with-backup-battery-and-poe-7124) |
| MultiTech Conduit AP (MTCAP3) | SX1303 | 24.6 dBm cond. | n/p | £251–336 ex-VAT | [Concept13](https://www.concept13.co.uk/shop/lorawan-gateways/indoor/multitech-conduit-ap-lorawan-gateway/) |
| Ezurio Sentrius RG186 | SX1301 | 14 dBm | −127 dBm @ SF7 | USD 265 / €329 | [Ezurio](https://www.ezurio.com/part/rg186) |

**Regulatory ceiling.** EU868 standard uplink sub-bands K/L/M/N/Q: max 25 mW / 14 dBm
ERP (≈ 40 mW / 16 dBm EIRP), duty cycle 0.1–1%
([TTN EU868](https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/);
[ETSI EN 300 220-2](https://www.etsi.org/deliver/etsi_en/300200_300299/30022002/03.02.01_60/en_30022002v030201p.pdf)).
The "27 dBm" on datasheets is legal only on the RX2 downlink channel 869.525 MHz in
sub-band P (500 mW / 10% duty cycle)
([Option.com](https://support.option.com/support/solutions/articles/36000126577-can-i-let-lora-send-with-27dbm-power-eu-)).
LoRa Alliance RP002 sets device max EIRP +16 dBm
([RP002-1.0.3](https://lora-alliance.org/wp-content/uploads/2021/05/RP002-1.0.3-FINAL-1.pdf)).

**Antennas (868 MHz indoor).** Regulatory-safe default is a 2–3 dBi rubber-duck/dipole:
at 14 dBm TX the 16 dBm EIRP ceiling leaves only ~0–2 dBi of headroom, so a 5 dBi
antenna needs TX reduced to stay legal
([TTN EU868](https://www.thethingsnetwork.org/docs/lorawan/regional-parameters/eu868/)).
RX is unregulated, so a better antenna helps the uplink receive path regardless. Types:
dipole 2–3 dBi, collinear 3–8 dBi, PCB 0–2 dBi
([RAKwireless](https://news.rakwireless.com/selecting-the-right-antenna-for-your-lorawan-gateway-a-comprehensive-guide/)).
High-gain collinears narrow the vertical beam (~25° at 5 dBi, ~15° at 8 dBi), creating
floor-to-floor coverage holes — so multi-floor deployments favour the wider 2–3 dBi
dipole ([RF Essentials](https://rfessentials.com/rf-knowledge-base/how-do-i-design-a-collinear-antenna-array-for-omnidirectional-coverage-with-gain/)).
**Height beats gain:** ~14 dB RSSI gain from 1.5 m to 10 m antenna height (medium
confidence) ([IJRISS](https://rsisinternational.org/journals/ijriss/Digital-Library/volume-9-issue-8/7711-7718.pdf));
outdoor/window placement worth 15–20 dB in field tests
([TTN forum](https://www.thethingsnetwork.org/forum/t/diy-external-antenna-for-gateway/3011)).
Cable loss at ~900 MHz: RG-174 ~1.0 dB/m, RG-58 ~0.66 dB/m, LMR-200 ~0.33 dB/m,
LMR-400 ~0.13 dB/m — a 5 m RG-58 run (~3.3 dB) cancels a 3 dBi upgrade
([W4RP](https://www.w4rp.com/ref/coax.html)). The project's Kerlink iFemtoCell Evolution
ships a 3 dBi swivel antenna on an SMA/RP-SMA connector
([QSG](https://www.manualslib.com/manual/1876143/Kerlink-Wirnet-Ifemtocell-Evolution-868.html)).
Antenna diversity yields ~6–10 dB in multipath but is rarely implemented on compact
SX1301/SX1302 gateways (low confidence).

**Devices (LoRaWAN TRVs / heating actuators).** LoRaWAN-native TRVs **do exist** as
purchasable Class A EU868 products, all targeted at commercial/institutional buildings:

| Product | Power / battery | Price | Source |
|---|---|---|---|
| MClimate Vicki | up to 10 yr (2×AA Li) | €77.50–97 ex-VAT | [mclimate.eu](https://mclimate.eu/products/vicki-lorawan) |
| dnt LW-eTRV (sealed, anti-tamper) | ~5 yr (2×AA) | €66.50 ex-VAT | [m2mgermany.de](https://www.m2mgermany.de/shop/produkt/dnt-lw-etrv-lorawan-heizkoerperthermostat) |
| dnt LW-eTRV-C (e-paper, dial) | ~4 yr (2×AA) | €79.61 incl. VAT | [iot-shop.de](https://iot-shop.de/shop/dnt-lw-etrv-c-dnt-lw-etrv-c-lorawan-heizkorperthermostat-bedienbar-7516) |
| Eurotronic Stella R | ~5 yr (2×AA) | €83.18 | [iot-shop.de](https://iot-shop.de/en/shop/ert-700269-eurotronic-stella-r-lorawan-radiator-thermostat-11010) |
| Eurotronic Stella Pro | up to 10 yr (3.6 V Li) | €94.95 | [reichelt.com](https://www.reichelt.com/de/en/shop/product/radiator_thermostat_stella_pro_lorawan-422240) |
| Milesight WT101 / WT102 | ~8 yr / energy-harvesting | ~£78 / ~£95 | [Milesight](https://www.milesight.com/iot/product/lorawan-sensor/wt101) |
| Micropelt MLR003R / DEOS TEO | energy-harvesting (TEG, no battery) | €155–190 | [Elbesoft](https://www.elbesoft-iot.de/shop/p/mlr003-lorawan) |
| Sontay RF-LW-TRV | 10 yr (claim) | n/p | [Sontay](https://www.sontay.com/en-gb/products/smart-devices/lorawan/rf-lw-trv-lorawan-trv-smart-radiator-thermostat/) |

All confirmed TRVs are **Class A**: downlink setpoints arrive only in the RX window
after an uplink (~up to 10 min latency at typical 10-min uplink intervals) — fine for
heating, not for rapid switching. MClimate Vicki has documented ChirpStack v3/v4
integration with a JSON downlink codec (e.g. `setTargetTemperature:20` → `0x0E14`) —
directly relevant to the whz-lora stack
([MClimate ChirpStack docs](https://docs.mclimate.eu/mclimate-lorawan-devices/integrations/chirpstack)).

> **Gap / low-confidence:** Dragino LPS8N and MultiTech TX/RX specs are partly
> unpublished; Ezurio RG186 TX is contradictory (14 vs 27 dBm); SF7–SF11 sensitivities
> are unpublished for nearly all gateways. TRV class is *inferred* for Eurotronic
> Stella R/Pro and Micropelt. Battery-life figures are idealised vendor claims.

### E — Benefit (energy savings)

**Most honest controlled benchmarks.** RCT of zonal controls added to already-programmed
gas systems (68 UK homes): mean **3.5%** gas reduction, one-third of homes *increasing*
([Sunikka-Blank et al., 2021](https://www.sciencedirect.com/science/article/pii/S0378778821008562)).
Long-term field evaluation (9 PL multi-family buildings, 6 heating seasons): TRVs alone
**10.3%**, TRVs **+ hydraulic balancing 20.8%** (19.1–23.3%), payback < 2.5 seasons
([Szczotka et al.](https://www.academia.edu/34306214/Actual_energy_savings_from_the_use_of_thermostatic_radiator_valves_in_residential_buildings_Long_term_field_evaluation)).
The hydraulic-balancing effect (≈ doubling of savings) is the single most
decision-relevant finding.

**German field/comparison studies.** KIT (3 class-D multi-family buildings, 27 units,
3 months): **15.5%** weather-adjusted / 21% raw ([KIT 2023](https://www.kit.edu/kit/32405.php)).
**EffKom** (WHZ Zwickau + Brunata-Metrona, 312 apartments, 2019–2023): ~15% new build,
~20% renovated existing stock, 30% district-heating pilot in Jena — directly relevant
project context, but only project-website/press figures
([klimaschutz.de](https://www.klimaschutz.de/de/projekte/effkom-energieeffizienter-wohnkomfort)).

**Simulation studies (upper end).** Strathclyde ESP-r: **12–31%** (avg ~20%)
([Cockroft et al., 2016](https://strathprints.strath.ac.uk/58937/1/Cockroft_etal_EB2016_Potential_energy_savings_achievable_by_zoned_control.pdf));
Fraunhofer IBP ~15% typical, >30% best-case
([Fraunhofer IBP](https://www.ibp.fraunhofer.de/de/projekte-referenzen/smart-home.html));
IBP Report 579 (tado-commissioned): up to 28%, claimed 22% average
([tado/Fraunhofer](https://www.tado.com/en/about/fraunhofer-study)).

**Heat-pump combination (emerging).** Salford lab: TRV zone-trimming cuts ASHP
space-heating energy **6–8%** without COP penalty if a radiator stays open + bypass
fitted ([pv-magazine 2026](https://www.pv-magazine.com/2026/04/17/thermostatic-radiator-valves-can-reduce-energy-consumption-in-air-source-heat-pumps-by-6-8/)).

**Economics (Germany).** Peer-reviewed cost-effectiveness model: break-even within 10
years needs only **5.7%** (single-family, ~€670 invest) to **7.7%** (apartment, ~€340)
([Schäuble et al., Applied Energy 2020 / RIFS](https://www.rifs-potsdam.de/en/news/smart-thermostats-prove-their-worth-poorly-insulated-buildings)).
German hardware: €40–80/valve, €320–1,060/apartment system, payback ~2.1 yr with BAFA
subsidy ([reduco.ai](https://reduco.ai/blog/heizung/smarte-thermostate-kosten-vergleich)).
Stiftung Warentest: realistic **5–10%** (8 h setback), max 10–15%
([Stiftung Warentest 2023](https://www.test.de/Heizkoerperthermostat-Test-5115581-0/)).

**Critical counter-evidence.** Which? shows manufacturer claims (8.4–31%) rest on
inflated baselines (17+ h assumed vs ~8 h actual heating)
([Which?](https://www.which.co.uk/news/article/smart-thermostats-can-you-save-what-the-companies-claim-aPhUI1z1HPCX)).
BBSR/TU Dresden on *institutional* buildings: claimed savings "not always realized,"
higher investment/maintenance costs, no measured % given
([BBSR](https://www.bbsr.bund.de/BBSR/DE/forschung/programme/zb/Auftragsforschung/5EnergieKlimaBauen/2008/Einzelraumregelung/01_start.html)).

> **Gap / low-confidence:** No peer-reviewed *German* measured study with a matched
> control group (KIT closest: n=27, 3 months). EffKom's figures lack a formal
> publication. Rebound/comfort-takeback is poorly quantified. Real-world heat-pump +
> smart-TRV savings are unmeasured. **Institutional/university-building room-level
> savings have no strong European field study — a direct gap for this project.**

### Model tooling (datasets & simulators)

**Simulators.** ns-3 `signetlabdei/lorawan` (GPLv2, actively maintained) plugs into the
full ns-3 propagation library — LogDistance, OkumuraHata, COST-231, ThreeGppIndoorOffice,
Nakagami — the strongest open starting point for the coverage block
([GitHub](https://github.com/signetlabdei/lorawan);
[ns-3 propagation](https://www.nsnam.org/docs/models/html/propagation.html)). FLoRa
(OMNeT++/INET) gives a GUI + full LoRaWAN stack + energy model but lacks
interference/mobility ([GitHub](https://github.com/florasim/flora)). LoRaSim
(Python/SimPy) is the lightest collision/scalability tool but uplink-only and
unmaintained since 2017 ([LoRaSim](https://mcbor.github.io/lorasim/)).

**Gateway-placement / sizing.** DPLACE computes optimal gateway count/position via Gap
Statistics + K-Means with Okumura-Hata, open NS-3 code — but Okumura-Hata is designed
for >1 km macro and its sub-100 m indoor applicability is unvalidated
([PMC7435864](https://pmc.ncbi.nlm.nih.gov/articles/PMC7435864/)).

**Link-budget / ToA.** Semtech LoRa Calculator is the authoritative (closed) tool: SF7
−123 dBm … SF12 −137 dBm, ~154 dB max budget at SF12/125 kHz
([Semtech](https://www.semtech.com/design-support/lora-calculator)). Open MIT-licensed
`tanupoo/lorawan_toa` covers time-on-air only ([GitHub](https://github.com/tanupoo/lorawan_toa)).

**Datasets (downloadable).** Industrial harbour RSSI (Bushehr, SF7/868 MHz, >1500
records, [Zenodo](https://pmc.ncbi.nlm.nih.gov/articles/PMC10859256/));
[oliveiraleo/LoRa-RSSI-dataset-outdoor](https://github.com/oliveiraleo/LoRa-RSSI-dataset-outdoor);
[emanueleg/lora-rssi](https://github.com/emanueleg/lora-rssi);
[mclab-hbrs/lora-bonn](https://github.com/mclab-hbrs/lora-bonn). Ready-to-run indoor
path-loss notebooks: [nahshonmokua/LoRaWAN-Indoor-PL-parametrics](https://github.com/nahshonmokua/LoRaWAN-Indoor-PL-parametrics)
(COST-231 multi-wall + Bayesian regression on the Siegen testbed). The Siegen indoor
office campaign (1.3 M measurements, SF7–12) is the best-matched indoor reference, raw
data availability unconfirmed ([arXiv 2505.06375](https://arxiv.org/abs/2505.06375)).

> **Gap / low-confidence:** No confirmed downloadable multi-room, multi-gateway,
> multi-SF *academic-building* dataset (Siegen closest, availability unconfirmed). No
> open, scriptable link-budget calculator across the full SF/BW/CR space. The ns-3
> ThreeGppIndoorOffice + lorawan combination is unvalidated against measured LoRaWAN
> data and would need calibration.

## Buy side — turnkey commercial systems (RQ7)

Representative complete smart-heating systems, as the make-vs-buy benchmark for a
~50-radiator building.

| System | RF protocol | What's included | Thermostat (€) | Gateway/CCU (€) | ~50-radiator total (€) | Recurring / cloud | Local-capable | Scalability |
|---|---|---|---|---|---|---|---|---|
| **Homematic IP — CCU3** | Proprietary BidCos, 868 MHz | CCU3 hub + HmIP-eTRV-2 + app | ~44–60 | CCU3 ~180 | ~2,380 | None mandatory | **Yes** — local | ≤250 dev/CCU3; expert WebUI |
| **Homematic IP — Access Point 2** | Homematic IP, 868 MHz | HAP2 gateway + TRVs + app | ~44–60 | HAP2 ~60 | ~2,260 | Cloud for app (free) | No — needs eQ-3 cloud | ≤120 dev/HAP2 |
| **tado° X** | Thread / Matter, 2.4 GHz | Bridge X + TRV X + cloud app | 65–100 | Bridge X ~55 | ~3,305 | Free tier; AI €3.99/mo; *tested* €0.99/mo basic | Partial | ~100 m²/bridge |
| **Bosch Smart Home** | ZigBee 3.0 (+Matter) | Controller II + TRV II + app | 49–76 | Controller II ~90 | ~2,700 | None mandatory | **Yes** | "hundreds" (unverified) |
| **Danfoss Ally** | ZigBee 3.0 | Ally Gateway + TRVs + app | ~66–75 | Gateway ~142 | ~3,450 (2 GW) | App cloud; ZHA local | Partial | **32 TRVs/gateway** |
| **Eurotronic Comet ZigBee** | ZigBee 3.0 | TRV only; any ZigBee hub | ~40–50 | hub ~40 | ~2,040 | None (open ZigBee) | **Yes** | mesh; no vendor console |
| **Wundasmart** | Proprietary sub-GHz | HubSwitch + heads + room stats | ~36–72 | HubSwitch ~180 | ~2,050–3,780 | None; LAN-local | **Yes** | **50 heads/30 rooms**; UK only |
| **AVM FRITZ!DECT 302** | DECT ULE, 1.9 GHz | FRITZ!Box + TRVs + app | ~54–60 | FRITZ!Box 0–250 | ~2,750 | None | **Yes** | **~12 TRVs/box → unsuitable** |
| **MClimate Vicki** *(LoRaWAN)* | **LoRaWAN EU868 Class A** | Vicki + any LoRaWAN GW + LNS | ~77–97 | reuse GW; else 189–224 | ~4,850 valves (GW present) | None for device; Enterprise optional | **Yes** — self-host | **Building-scale**; open API/BMS |
| **Milesight WT101** *(LoRaWAN)* | **LoRaWAN EU868 Class A** | WT101 + GW + LNS | ~83–107 | as above | ~5,350 valves | None for device | **Yes** | Building-scale; 100–268-unit deployments |
| **DEOS TEO** *(LoRaWAN, pro)* | **LoRaWAN**, batteryless | TEO + GW + DEOS suite | n/p | n/p | n/p | DEOS suite | **Yes** — on-prem BMS | Non-residential; BMS via MQTT/BACnet |

**The comparison.** Cheapest credible consumer system for 50 radiators is Eurotronic
ZigBee (~€2,040, if a coordinator exists) or Homematic IP CCU3 (~€2,380); LoRaWAN-native
TRVs cost ~€4,850–5,350 in valves alone at single-unit retail. **But** at WHZ the
gateway + ChirpStack already exist (marginal infra ~0), and both LoRaWAN vendors offer
unpublished volume pricing (typically −20–40% at building scale). The **real asymmetry
is administration, not upfront cost:** consumer systems are app/WebUI-centric with hard
hub ceilings (FRITZ!Box ~12, Danfoss 32, Wundasmart 50, HAP2 120, CCU3 250) and no
BMS/API/research-data path; the open-LoRaWAN path has full REST/gRPC provisioning,
downlink scheduling, MQTT events and a data pipeline, at the price of one-time
integration engineering and **no vendor lock-in**. For a university research building
with existing LoRaWAN infrastructure, "buy LoRaWAN TRVs + self-host LNS" is
architecturally superior despite higher per-valve retail price.

### Buy-side open gaps / low-confidence

- FRITZ!Box ~12-thermostat ceiling: community summaries, not an AVM spec page.
- Danfoss Ally Gateway €142 is reseller pricing (list €189.76); official channel may differ.
- Eurotronic Comet ZigBee starter-set price not published.
- tado° mandatory-fee status: tested early 2025; current page shows only optional AI Assist.
- Wundasmart EUR availability: GBP-only, UK market.
- MClimate Vicki / Milesight WT101 bulk pricing not published (building-scale likely −20–40%).
- DEOS TEO pricing fully opaque (professional BMS budget).
- Bosch device ceiling "hundreds" is third-party, not a Bosch spec.

## Solid vs. thin

| Block | Rating | Reason |
|---|---|---|
| B — RF / coverage | **Solid** | Many peer-reviewed 868 MHz campaigns + NIST/ITU material data; per-floor RC at 868 MHz and mixed-construction extrapolated. |
| C — Gateways | **Solid** | Multiple datasheets, consistent specs + EUR prices; gaps only in per-SF sensitivity and a few TX figures. |
| C — Antennas | **Partial** | Regulatory limits and cable-loss solid; gain/height/diversity numbers from blogs/forums. |
| C — Devices / TRVs | **Solid** | Several real Class A products with EUR pricing and ChirpStack integration; class inferred for two. |
| E — Benefit | **Partial** | Strong trials vary 3.5–25%; no German matched-control study, EffKom unpublished, institutional segment unmeasured. |
| Model tooling | **Solid** | Mature open simulators + downloadable datasets + reusable notebooks; missing a matched indoor academic dataset + open link-budget calculator. |
| F — Buy side (turnkey) | **Partial** | Retail prices + protocols solid; volume LoRaWAN pricing and a few systems (DEOS) opaque. |

## Key surprises / things the PO should know

- **"Homematic is not LoRaWAN."** Confirmed: Homematic IP (eQ-3) runs proprietary
  **BidCos** at 868 MHz — not LoRaWAN, needs a CCU3/cloud hub, **no LoRaWAN
  interoperability**, and **no commercial Homematic-to-LoRaWAN bridge**; open-source
  LoRaBridge only forwards Zigbee *sensors* uplink-only (no actuator downlink). The
  device catalog must be built from genuinely LoRaWAN-native TRVs.
- **LoRaWAN TRVs are a commercial/institutional niche, not a consumer market** — they
  exist and are buyable, but the consumer segment is owned by non-LoRaWAN protocols.
  This *aligns* with the project's whole-building institutional target.
- **The WHZ already owns the gateway + ChirpStack** → marginal infrastructure cost ~0;
  the make-side cost collapses to valves + one-time integration. Consumer hubs cap at
  12–250 devices and carry cloud/subscription/lock-in risk.
- **Hydraulic balancing roughly doubles savings** (10.3% → 20.8%) — the economic case
  may hinge more on balancing than on the valves themselves.
- **The honest controlled benchmark is low (3.5%)** when zoning is added to
  already-programmed systems; vendor claims of 22–31% rest on inflated baselines. But
  German break-even is only 5.7–7.7%, so even modest savings can pay back.
- **WHZ has direct prior art:** the EffKom project was co-developed by WHZ Zwickau (312
  apartments, ~20% renovated-stock savings) — in-house knowledge and possibly data.
- **Class A latency is fine for heating but not switching** (~up to 10 min) — the model
  should assume slow control loops.
- **Energy-efficient glazing/insulation can block the signal** (low-E glass 35–60 dB,
  metallised vapour barriers ~85 dB) — modern/renovated envelopes can defeat
  through-wall coverage (low confidence; non-LoRa sources).
- **No indoor 16-channel gateway exists** in this price class — densification means
  *more* 8-channel gateways, not higher-capacity ones.
- **Institutional-building savings are essentially unmeasured** in the European
  literature; the one institutional study (BBSR) warns claimed savings are "not always
  realized" — a real risk flag for a whole-building academic deployment.

## Recommended deep-research targets

1. **Dense Indoor Sensor Networks (ScienceDirect, 2022)** — [link](https://www.sciencedirect.com/science/article/pii/S1574119222000700) — largest empirical gateway-density dataset (390 nodes, 4 GW, 8 floors); grounds the gateway-count model.
2. **Environment-Aware Indoor LoRaWAN Path Loss (arXiv 2510.04346, 2025)** — [link](https://arxiv.org/html/2510.04346v1) — most complete 868 MHz indoor model parameters; avoids a fresh campaign.
3. **Conditions for cost-effective smart thermostats in Germany (Schäuble et al., 2020)** — [link](https://www.rifs-potsdam.de/en/news/smart-thermostats-prove-their-worth-poorly-insulated-buildings) — the peer-reviewed German economic model (break-even 5.7%/7.7%); the economic backbone.
4. **Actual energy savings from TRVs — long-term field evaluation (Szczotka et al.)** — [link](https://www.academia.edu/34306214/Actual_energy_savings_from_the_use_of_thermostatic_radiator_valves_in_residential_buildings_Long_term_field_evaluation) — strongest measured savings + the hydraulic-balancing finding.
5. **Domestic zonal heating controls RCT (Sunikka-Blank et al., 2021)** — [link](https://www.sciencedirect.com/science/article/pii/S0378778821008562) — the honest 3.5% benchmark calibrating vendor optimism.
6. **GitHub signetlabdei/lorawan (ns-3 module)** — [link](https://github.com/signetlabdei/lorawan) — recommended foundation for building the coverage/sizing model.
7. **MClimate Vicki — ChirpStack integration docs** — [link](https://docs.mclimate.eu/mclimate-lorawan-devices/integrations/chirpstack) — official ChirpStack v4 downlink codec, reusable on whz-lora.
8. **WHZ EffKom project (in-house)** — [link](https://www.klimaschutz.de/de/projekte/effkom-energieeffizienter-wohnkomfort) — internal prior art and possibly measured data; chase the final report and contacts directly.
