# Building-typology Defaults

> The preset values behind the model's two dropdowns ([model.md §9](model.md)),
> grounded in German building-stock sources (IWU TABULA / EPISCOPE, Destatis /
> Zensus 2022, ista/TU Dortmund, Heizspiegel, BBSR). Ranges in parentheses; the
> bare number is the representative default. Every value stays editable in the
> [calculator](model-calculator.html) — presets are a starting point, not a fact.

## 1. Size tier (Axis 1)

| Tier | Example class | Dwelling units | Floors | Living area m² | Radiators | Source |
|---|---|---|---|---|---|---|
| **Klein** | Mehrfamilienhaus | 7 (3–12) | 3–4 | 521 (~500) | 35 (7 × 5/unit) | [ista/TU Dortmund, n=74k](https://www.bundesbaublatt.de/artikel/bbb_So_sieht_es_aus_Deutschlands_typisches_Mehrfamilienhaus-3593523.html); [EPISCOPE/TABULA](https://episcope.eu/building-typology/country/de/) |
| **Mittel** | Größerer Wohnkomplex | 22 (13–50) | 4–8 | ~1,500 (900–3,500) | 120 (22 × 5.5/unit) | [EPISCOPE/TABULA](https://episcope.eu/building-typology/country/de/); [Destatis Wohnsituation 2022](https://www.destatis.de/DE/Themen/Gesellschaft-Umwelt/Wohnen/ergebnisse_zusatzprogramm.html) |
| **Groß** | Bürokomplex | — (offices) | 5–6 (2–25) | 1,841 NF (1,000–9,000) | 92 (1,841 ÷ 20 m²/rad) | [dena/IW Köln](https://www.tga-praxis.de/dena_analyse); [Destatis 2022](https://www.destatis.de/DE/Presse/Pressemitteilungen/2024/03/PD24_N010_61311.html) |

## 2. Construction / age (Axis 2)

| Preset | Era | Construction | Heating intensity (kWh/m²·yr) | RF-relevant materials | Source |
|---|---|---|---|---|---|
| **Neubau** | 2002–today (GEG/EH-55) | Massive masonry or timber + WDVS; wall U ≤0.20 | **70** (35 demand cap; ~70 measured) | Low-E metallised glazing (+24–40 dB); timber most RF-transparent | [GEG/Energiestandard](https://de.wikipedia.org/wiki/Energiestandard); [Heizspiegel](https://www.heizspiegel.de/heizkosten-pruefen/heizkosten-pro-m2-vergleich/) |
| **Saniert** | pre-1995, retrofit | Original + WDVS; wall U 0.20–0.45 | **90** (50–130) | Often retrofit low-E glazing; insulation over brick/RC | [GEG class scale](https://www.purpose-green.com/en/article/energieeffizienzklasse-fuer-gebaeude-richtig-einstufen); [HeizNorm](https://heiznorm.de/u-wert-tabellen) |
| **Altbau** | pre-1949 | Solid brick (Vollziegel); wall U 1.6–1.7 | **160** (160–250+) | Brick 10–15 dB/wall; clear glass 0–3 dB | [HeizNorm](https://heiznorm.de/u-wert-tabellen); [Brunata measured](https://ausbauundfassade.de/altbauten-brauchen-weniger-energie-als-angenommen/) |
| **Plattenbau** | 1958–1990 (East) | 3-layer RC sandwich (WBS 70); wall U ~1.2–1.5 | **140** (130–160) | Reinforced concrete 15–25 dB/wall-floor | [WBS 70](https://en.wikipedia.org/wiki/WBS_70); [RF Engineer](https://rfengineer.net/rf-engineering/lora-network-planning-rf-site-surveys/) |

Savings bands per construction (valve-only / +balancing) come from the
energy-savings research in [preliminary-research.md](preliminary-research.md),
not from this typology sweep.

## 3. Constants

- **Radiators per dwelling: 5** (band 5–6; 6–7 for larger units). Converges across
  heat-cost-allocator data, a real 900-apartment LoRaWAN deployment (5/apt), and a
  Berlin regulation example. Design rule: one radiator per heated room, hallways
  excluded.
- **m² per radiator: 20** (band 15–20 residential; 15–25 office). From Destatis
  4.2 rooms / 94 m² average dwelling + one-radiator-per-room.
- **No norm fixes a radiator count** — DIN EN 12831 / VDI 6030 size heating
  surfaces by watts, not unit count. The radiator counts above are derived, not
  measured.

## 4. Confidence & gaps

**Solid:** Klein/MFH dimensions (ista, n=74k); heating intensity per era
(Heizspiegel + Brunata, ~100k records); wall U-values & construction per era; 5
radiators/dwelling (four independent sources); brick/RC/low-E attenuation
magnitudes.

**Thin (treat as editable, refine later):**
- **Mittel/GMH living area (~1,500 m²)** — no national statistic for the 13–50-unit
  class; honest spread 900–3,500 m².
- **Office m²/radiator (20)** — a planning rule, not a DIN figure; the whole
  Groß-tier radiator count inherits this softness.
- **Plattenbau wall U (~1.2–1.5)** — inferred from the era table, not a WBS 70
  sandwich calculation.
- **RF attenuation at 868 MHz** — all values extrapolated from 900 MHz / cellular
  measurements; no 868 MHz LoRa measurement for Plattenbau RC or low-E glass found.
  (This is exactly what whz-lora can measure and calibrate.)
- **Floor-count distributions** — typology-derived, not distribution-weighted.
