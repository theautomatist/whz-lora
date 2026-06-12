# Preliminary Research Findings (DRAFT)

> **Status: preliminary, in consolidation.** This document gathers the founded
> pre-grill research for the [economic viability & sizing study](scope-and-requirements.md).
> The **buy side (RQ7)** below is complete. The **make side (RQ1–RQ6)** — in-building
> propagation, gateways, antennas, LoRaWAN devices, energy savings, model tooling —
> is being consolidated from the parallel research sweep and will be inserted above
> the buy side. Numbers are indicative retail figures from the sources cited, not
> procurement quotes.

## Headline (so far)

- **LoRaWAN-native radiator thermostats exist as off-the-shelf products** — this
  settles the §6.5 open question on the device catalog: the *make* side is buildable
  with real open-market LoRaWAN TRVs, not only sensors. Confirmed products:
  **MClimate Vicki** (~€97), **Milesight WT101** (~€107), plus professional
  **DEOS TEO** (batteryless, thermal energy harvesting) and **Sontay RF-LW-TRV**.
- **"Homematic" is a proprietary 868 MHz system, not LoRaWAN** — CCU3 (or Access
  Point) hub + per-radiator HmIP-eTRV thermostats. Cheap (~€2,380 for 50 radiators)
  and locally operable, but siloed, no BMS/API path → it is a clean *buy*-side
  benchmark, exactly as the PO suspected.
- **The decisive cost reframe:** WHZ already owns the gateway (Kerlink iFemtoCell)
  and self-hosts ChirpStack, so the **marginal gateway cost of adding TRVs is ~0**.
  The make-side cost collapses to TRVs plus a one-time integration effort; the
  consumer turnkey systems are cheaper per radiator at retail but cap at 50–250
  devices/hub and carry cloud/subscription/lock-in risk.

## Make side — open LoRaWAN (RQ1–RQ6)

*Pending consolidation from the sweep workflow — to be inserted here.*

## Buy side — turnkey commercial systems (RQ7)

Representative complete smart-heating systems, as the make-vs-buy benchmark for a
~50-radiator building.

| System | RF protocol | What's included | Thermostat (€) | Gateway/CCU (€) | ~50-radiator total (€) | Recurring / cloud | Local-capable | Scalability |
|---|---|---|---|---|---|---|---|---|
| **Homematic IP — CCU3** | Proprietary BidCos / Homematic IP, 868 MHz | CCU3 hub + HmIP-eTRV-2 TRVs + app | ~44–60 | CCU3 ~180 | ~2,380 | None mandatory (optional 3rd-party remote) | **Yes** — CCU3 fully local | ≤250 devices/CCU3; expert WebUI admin; indoors needs repeaters |
| **Homematic IP — Access Point 2** | Homematic IP, 868 MHz | HAP2 cloud gateway + TRVs + app | ~44–60 | HAP2 ~60 | ~2,260 | Cloud for app access (free now) | No — needs eQ-3 cloud | ≤120 devices/HAP2; consumer admin |
| **tado° X** | Thread / Matter, 2.4 GHz | Bridge X + Smart Radiator Thermostat X + cloud app | 65–100 | Bridge X ~55 | ~3,305 | Free tier; AI Assist €3.99/mo; *tested* mandatory €0.99/mo basic in early 2025 | Partial — schedules local, app needs cloud | ~100 m²/bridge; no facility dashboard |
| **Bosch Smart Home** | ZigBee 3.0 (+Matter/Thread on new TRV) | Controller II + Radiator Thermostat II + app | 49–76 | Controller II ~90 | ~2,700 | None mandatory; optional Home+ | **Yes** — local automations | "hundreds" of devices (unverified); ZigBee mesh |
| **Danfoss Ally** | ZigBee 3.0, 2.4 GHz | Ally Gateway + Ally TRVs + app | ~66–75 | Gateway ~142 | ~3,450 (2 gateways) | App cloud-connected; ZHA local possible | Partial — local via Home Assistant ZHA | **32 TRVs/gateway** → 2 needed for 50 |
| **Eurotronic Comet ZigBee** | ZigBee 3.0, 2.4 GHz | TRV only; pairs with any ZigBee hub | ~40–50 | 3rd-party hub ~40 | ~2,040 | None — open ZigBee (Zigbee2MQTT free) | **Yes** — local hub | Mesh self-extends; no vendor console |
| **Wundasmart** | Proprietary sub-GHz | HubSwitch + Radiator Heads + Room Thermostats | ~36–72 | HubSwitch ~180 | ~2,050–3,780 | None published; LAN-local | **Yes** — local LAN | **50 heads / 30 rooms per hub**; UK only (GBP) |
| **AVM FRITZ!DECT 302** | DECT ULE, 1.9 GHz | FRITZ!Box (DECT base) + TRVs + app | ~54–60 | FRITZ!Box 0–250 | ~2,750 | None — fully local | **Yes** | **~12 thermostats/FRITZ!Box → unsuitable >12** |
| **MClimate Vicki** *(LoRaWAN)* | **LoRaWAN EU868, Class A** | Vicki TRV + any LoRaWAN gateway + LNS | ~96–97 | none extra (reuse gateway); else 189–224 | ~4,850 TRVs (gateway already present) | None for device; MClimate Enterprise optional (free ≤10 / €50 building·mo ≤50 / €0.88 device·mo >50) | **Yes** — self-host ChirpStack | **Building-scale**: 1 gateway covers building; open API; BMS via BACnet/Modbus/MQTT |
| **Milesight WT101** *(LoRaWAN)* | **LoRaWAN EU868, Class A** | WT101 TRV + gateway + LNS | ~83–107 | as above | ~5,350 TRVs | None for device; optional cloud | **Yes** — self-host LNS | Building-scale; documented 100–268-unit deployments |
| **DEOS TEO** *(LoRaWAN, pro)* | **LoRaWAN**, thermal-harvesting (batteryless) | TEO TRV + gateway + DEOS pro.Building Suite | not published | not published | not published | DEOS suite (undisclosed) | **Yes** — on-prem BMS coupling | Non-residential (offices, schools, hospitals); BMS via MQTT/BACnet |

### Make vs. buy — the conceptual comparison

**Cost.** Cheapest credible consumer system for 50 radiators: Eurotronic ZigBee
(~€2,040, if a coordinator exists) or Homematic IP CCU3 (~€2,380). LoRaWAN-native
TRVs cost ~€4,850–5,350 in TRVs alone at single-unit retail. **But** at WHZ the
LoRaWAN gateway + ChirpStack already exist, so the marginal infrastructure cost is
~0, and both LoRaWAN vendors offer (unpublished) volume pricing that typically cuts
20–40% at building scale — narrowing the gap.

**Administration is the real asymmetry, not upfront cost.** Consumer systems are
app- or WebUI-centric, designed for a homeowner: no bulk schedule import, no (or
rate-limited) API, no floor-plan/BMS integration, and hard hub ceilings (FRITZ!Box
~12, Danfoss 32/gateway, Wundasmart 50, HAP2 120, CCU3 250). The open-LoRaWAN path
has full REST/gRPC provisioning, downlink scheduling, MQTT event streams, and feeds
a research data pipeline (InfluxDB/PostgreSQL) — at the price of one-time
integration engineering and no vendor lock-in.

**Conclusion for the model.** For a university research building *with existing
LoRaWAN infrastructure*, "buy LoRaWAN TRVs + self-host LNS" is architecturally
superior despite higher per-unit TRV retail price; consumer turnkey systems win on
raw hardware cost but lose on scale ceiling, cloud/subscription exposure, and the
absence of any BMS/research-data path. This trade-off is the core make-vs-buy output.

### Buy-side sources

Homematic IP: [product page](https://homematic-ip.com/en/product/radiator-thermostat),
[HmIP-eTRV-2 Geizhals €43.70+](https://geizhals.de/eq-3-homematic-ip-hmip-etrv-2-v113288.html),
[CCU3 Geizhals €179.90+](https://geizhals.de/eq-3-homematic-zentrale-ccu3-151965a0-a1839573.html),
[Access Point 2 €59.95](https://www.piotek.de/?a=1852&lang=eng),
[device limits FAQ](https://homematic-ip.com/en/faqs),
[CCU3 local operation](https://homematic-forum.de/forum/viewtopic.php?t=78149).
tado°: [shop](https://shop.tado.com/en), [app tiers](https://www.tado.com/en/app-services/app),
[Heise: mandatory-fee test Feb 2025](https://www.heise.de/en/news/Tado-tests-payment-model-for-basic-app-functions-of-smart-heating-thermostats-10291678.html).
Bosch: [Controller II €87.70+](https://geizhals.at/bosch-smart-home-controller-ii-8750002101-a2869619.html),
[Thermostat II €49.99+](https://geizhals.de/bosch-smart-home-heizkoerper-thermostat-ii-v115415.html).
Danfoss Ally: [TRV €65.70+](https://geizhals.de/danfoss-ally-heizkoerperthermostat-014g2420-a2835161.html),
[Gateway €142 + 32-device limit](https://store.danfoss.com/en/Heating-and-District-Energy/Smart-Heating/Danfoss-Ally-%E2%80%93-Smart-Heating/Gateway/Danfoss-Ally%E2%84%A2-Gateway,-Zigbee/p/014G2400).
Eurotronic: [Comet ZigBee €39.95](https://www.reichelt.com/de/en/shop/product/radiator_thermostat_comet_zigbee-335410),
[product page](https://eurotronic.org/produkte/comet-zigbee/).
Wundasmart: [Radiator Head](https://www.wundasmart.co.uk/products/wundasmart-radiator-he),
[HubSwitch + 50/30 limit](https://www.wundasmart.co.uk/products/wundasmart-hub-switch).
AVM: [FRITZ!DECT 302 €53.92+](https://geizhals.de/avm-fritz-dect-302-funk-heizkoerperthermostat-a2684845.html),
[FRITZ!Smart Thermo 302 €59.99](https://fritz.com/en/products/fritz-smart-thermo-302-20003120).
LoRaWAN TRVs: [MClimate Vicki €97](https://mclimate.eu/products/vicki-lorawan),
[MClimate Enterprise pricing](https://mclimate.eu/pages/enterprise),
[Vicki iot-shop.de €96.27](https://iot-shop.de/en/shop/mclimate-vicki-lorawan-radiator-thermostat-4969),
[Milesight WT101 spec](https://www.milesight.com/iot/product/lorawan-sensor/wt101),
[WT101 iot-shop.de €106.98](https://iot-shop.de/en/shop/mil-wt101-868-milesight-wt101-868-lorawan-smart-radiator-thermostat-6661),
[DEOS TEO](https://www.deos-ag.com/en/products/sensors-thermostats/lorawan/radiator-thermostat-deos-teo/),
[Sontay RF-LW-TRV](https://www.sontay.com/en-gb/products/smart-devices/lorawan/rf-lw-trv-lorawan-trv-smart-radiator-thermostat/).
Gateways: [Dragino LPS8N €189 / Kerlink iFemtoCell €224](https://invibitshop.com/collections/gateways).

### Buy-side open gaps / low-confidence

- FRITZ!Box ~12-thermostat ceiling: from community summaries, not an AVM spec page — verify against FRITZ!OS release notes.
- Danfoss Ally Gateway €142 is reseller (Bola) pricing, list shown €189.76 — official channel price may differ.
- Eurotronic Comet ZigBee starter-set price not published; only single-TRV retail confirmed.
- tado° mandatory-fee status: tested early 2025; current page shows only optional AI Assist — rollback/segmentation unconfirmed.
- Wundasmart EUR availability: GBP-only, UK market; EUR via ~1.20 GBP/EUR approximation.
- MClimate Vicki / Milesight WT101 bulk pricing not published; building-scale procurement likely 20–40% lower.
- DEOS TEO pricing fully opaque (professional BMS budget; ~€150–300/unit guessed, unsourced).
- Bosch device ceiling "hundreds" is third-party, not Bosch spec.
