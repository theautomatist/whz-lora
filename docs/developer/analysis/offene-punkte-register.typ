#import "report-template.typ": *
#show: report.with(
  title: "Offene Punkte & Unsicherheiten — konsolidiertes Register",
  subtitle: "Was noch offen ist, wie groß die Kostenwirkung, und wodurch es sich schließen lässt — über Technik, Kosten und Prozess hinweg",
  meta: "Projekt whz-lora · WHZ · 2026-06-28 · Single Source für offene Punkte · verknüpft (dupliziert nicht) test-concept, grenzen-risiken, report-a/b, model, building-typology",
)

#callout(title: "Wozu dieses Register", color: accent)[
  Die offenen Punkte des Projekts waren bisher über mehrere Dokumente *verstreut* — Technik-
  Restrisiken im Grenzen/Risiken-Papier, Kosten-Bandbreiten in der Kostenanalyse, Modell-Annahmen
  im Modell-Dokument. Dieses Register führt sie an *einem Ort* zusammen: je offener Punkt eine
  *Bandbreite/Kostenwirkung*, ein *Schweregrad* und *wodurch er sich schließt* — mit Verweis auf
  die Quelle, die das Detail hält. Es ist ein *lebendes* Dokument: ist ein Punkt geschlossen
  (gemessen/entschieden), wird er hier abgehakt.
]

= Der Kernbefund in einem Bild

Die wichtigste offene Aussage des ganzen Projekts: Die Amortisation ist *keine Zahl, sondern ein
Band* — von rund *4 Jahren bis weit über 20* — und die beiden Faktoren, die das Band aufspannen
(*Einsparquote* und *Energieträger*), sind am realen Gebäude *noch nicht erhoben*.

#figure(
  image("assets/payback-band.svg", width: 100%),
  caption: [Dasselbe System ist je nach Annahme klar wirtschaftlich (~4 J.) oder nie (>20 J.). Hardware bewegt den Payback nur um ca. 2 Jahre — die großen Bänder kommen aus Einsparquote, Tarif und Betriebskosten (Quelle: report-b, Tornado/Netto-Effekt).],
)

#plain[Anders gesagt: Die größten Kosten-Unsicherheiten schließt man *nicht mit mehr Hardware*, sondern mit *Information und Entscheidungen* — einer Messung am Gebäude, einer Heizkostenrechnung, einem festgelegten Stundensatz, einem benannten Zielgebäude.]

= Register A — Kosten-Hebel (spannen das Payback-Band auf)

Quelle-Kürzel: Rn = Ranking-Zeile in `report-b-kostenanalyse`; §11 = `model.md` Open refinements; RevA = `report-a` Review.

#table(
  columns: (1.5fr, 1.4fr, auto, 1.5fr, 0.8fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Offener Punkt"), th("Bandbreite / Wirkung"), th("Schwere"), th("Schließen durch"), th("Quelle")),
  [*K1 · Einsparquote (netto)*], [5 % → *>20 J.* (unwirtschaftl.) · 9–15 % → *~4–6 J.*; brutto 8–12 % − Rebound 20–30 %], [#text(fill: bad)[*hoch*]], [am WHZ-Testbed/Pilot *messen*, Rebound rechnerisch einsetzen, als Band berichten], [report-b R1; §11],
  [*K2 · Energieträger / Tarif*], [Gas 0,12 → ~10,3 J. · Fernwärme 0,16 → ~6,5 J.; Fernwärme-Band 0,08–0,20 (*Faktor 2*)], [#text(fill: bad)[*hoch*]], [reale *Heizkostenrechnung* des Zielgebäudes; Monopol-Risiko Fernwärme notieren], [report-b R4; model §10],
  [*K3 · Monitoring / OPEX*], [960 €/a → 280 €/a senkt 10,3 → ~7,1 J.; Portfolio noch günstiger], [#text(fill: bad)[*hoch*]], [Betriebsmodell *ereignisgesteuert* entscheiden; Fixkosten über Portfolio teilen], [report-b R2],
  [*K4 · Stundensatz (Kosten vs. Verkauf)*], [80 €/h vs. 45–65 €/h → ±7–8 J. auf das Urteil], [#text(fill: bad)[*hoch*]], [WHZ-*Grenzkostensatz* festlegen; Verkaufssatz nur als Angebots-Szenario], [report-b R3],
  [*K5 · Aktor-Bulk-Preis*], [50–82 € → Kern-Payback 4,1–5,5 J.; Bulk-Rabatt ungehärtet], [#text(fill: warn)[*mittel*]], [echtes *120-Stück-Angebot* (dnt *und* Vicki/MClimate), Artikelnummer fixieren], [report-b R7; model §10],
  [*K6 · Hydraulischer Abgleich* (Co-Maßnahme)], [+9.000 €, verdoppelt Ersparnis (10→20 %) → ~4,0 J.], [#text(fill: warn)[*mittel*]], [eigene Wirtschaftlichkeit rechnen; vorher Schieflage prüfen], [report-b §6],
  [*K7 · Batterie-OPEX*], [228 €/a glatt vs. lumpige ~1.600-€-Welle; Lithium vs. Alkaline (Kälte −50 %)], [#text(fill: warn)[*mittel*]], [als geplante 120-Ventil-Welle modellieren; Lithium-Primärzellen], [report-b R8; risiken H2],
  [*K8 · Overhead-Doppelzählung* (sunk costs)], [~1.500 € Überschätzung; Schritte 1/2/5/6 redundant], [#text(fill: warn)[*mittel*]], [Schritte mergen, F-0005-Batch-Import, Skript-Commissioning], [RevA],
  [*K9 · Kaufmännisches fehlt*], [USt, Marge/Risiko, Gewährleistung, *Förderung BEG/BAFA*, diskontierter Payback], [#text(fill: warn)[*mittel*]], [im Modell ergänzen; Förder-/Netto-Szenarien rechnen], [§11; report-b §Verf.],
)

= Register B — Technik & Test-Grenzen (was der Feldtest nicht abdeckt)

Quelle-Kürzel: „risiken A1/B2 …" = Risiko-ID im Dossier `test-concept-grenzen-risiken`.

#table(
  columns: (1.5fr, 1.4fr, auto, 1.5fr, 0.8fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Offener Punkt"), th("Bandbreite / Wirkung"), th("Schwere"), th("Schließen durch"), th("Quelle")),
  [*T1 · Downlink-Erreichbarkeit*], [Uplink-PDR ≠ Downlink-PDR; Sollwerte/ADR-Kommandos kommen evtl. nicht an], [#text(fill: bad)[*hoch*]], [Downlink-Loopback-Test (confirmed Downlink → ACK) je Punkt], [risiken A1],
  [*T2 · Downlink-Duty-Cycle (Kapazität)*], [RX1 ~25–34/h je Subband · RX2 ~225–360/h *für alle Geräte*; im Kerlink-Pfad *kein* DC-Enforcement], [#text(fill: bad)[*hoch*]], [Duty-Cycle-Last-Simulation; Downlink-Grenze ins Sizing], [risiken A2],
  [*T3 · Kapazität / SF12-Well bei 35–120 Aktoren*], [3 Geräte zeigen es nicht; PDR-Kollaps < 10 % unter Last möglich], [#text(fill: bad)[*hoch*]], [`chirpstack-simulator`-Lasttest 35/120; ADR im Betrieb an, SF-Floor], [risiken A3/A4],
  [*T4 · Gateway-Position & Diversity*], [Sizing-Fehler bis *Faktor 2*; 2-GW-Nutzen mit 1 GW unmessbar (53 % nicht-nächster GW best)], [#text(fill: bad)[*hoch*]], [Alt-Position vergleichen; 2. Gateway leihen + A/B], [risiken B1/B2],
  [*T5 · Archetyp-Übertragung*], [nur Neubau (A) kalibriert; Plattenbau (D)/Altbau (C) ungesichert; RMSE 7–10 dB], [#text(fill: bad)[*hoch*]], [je Archetyp ≥1 Mess-Referenz; als Bandbreite mit Konfidenz], [risiken D1; b-typ §4],
  [*T6 · Bauzustand (WDVS/Low-E)*], [evtl. noch nicht final → Messung zu optimistisch (+5–17 dB Folie)], [#text(fill: bad)[*hoch*]], [Bauzustand protokollieren; Wiederholungsmessung nach Fertigstellung], [risiken E1/E2],
  [*T7 · Fremdnetz-Wachstum (Koexistenz)*], [CAF heute ≠ in 3 J.; 5–10 % → `P_Koll` 10–18 % (ungeplante Nachkosten)], [#text(fill: bad)[*hoch*]], [Dauer-CAF-Monitoring statt Einmal-Scan; SLA-Schwelle], [risiken G1],
  [*T8 · Geräte-Repräsentativität*], [Test-TRV ≠ Serie: ±3–6 dB Link-Budget → „1 vs. 2 GW" kann kippen], [#text(fill: bad)[*hoch*]], [A/B-Test Ziel-TRV vs. Test-TRV; Delta als Korrektur], [risiken H1],
  [*T9 · Schnappschuss / Saison / Statistik*], [bis ~10,6 dB Schwankung; 9–12 Punkte unterabgetastet (KI ±14 Pp)], [#text(fill: warn)[*mittel*]], [Walk-Survey (≥20 Pkt/Etage); Langzeit-Soak; Fade-Margin aus Literatur], [risiken C1/C2/F1/F2],
)

= Register C — Prozess & offene Entscheidungen

Quelle-Kürzel: Pn = Schritt in `process-model`; scope = `scope-and-requirements`; b-typ = `building-typology.md`.

#table(
  columns: (1.5fr, 1.4fr, auto, 1.5fr, 0.8fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Offener Punkt"), th("Bandbreite / Wirkung"), th("Schwere"), th("Schließen durch"), th("Quelle")),
  [*E1 · Zielgebäude X / Y nicht benannt*], [Modell läuft nur mit *Defaults* — kein konkretes Urteil möglich], [#text(fill: bad)[*hoch*]], [PO benennt 1–2 reale WHZ-Gebäude zur Instanziierung], [model §8; scope §6],
  [*E2 · Archetyp des Zielgebäudes*], [Neubau (A) vs. Plattenbau (D) bestimmt GW-Dichte (Faktor ~2)], [#text(fill: bad)[*hoch*]], [bei Gebäude-Benennung festlegen; ggf. RF-Referenz für D], [b-typ §4; risiken D1],
  [*P1 · Installateur-Varianz*], [Rollout 5–15 % höhere First-Time-Fail-Rate als der normierte Test], [#text(fill: warn)[*mittel*]], [Installations-Checkliste + Foto-Pflicht (P4-03); Stichprobe (P4-04)], [risiken I1],
  [*P2 · Provisionierungsfehler (Bulk)*], [1–5 % Fehlerrate bei 120 Geräten; 5–10 % offline möglich], [#text(fill: warn)[*mittel*]], [Charge-Abgleich Ware↔CSV (P2-05); Import-Format-/Dublettencheck (P3-03)], [risiken I2; P3-03],
  [*P3 · Zugang zu (Mieter-)Räumen*], [Batteriewellen 2–3× länger → OPEX zu optimistisch], [#text(fill: warn)[*mittel*]], [Fragenkatalog E10 verbindlich; reale Zugangsquote aus Pilot in OPEX], [risiken I3; P7-04],
  [*P4 · Survey-Tag / Zweit-Gateway-Kontingenz*], [stille 0-€-Annahme vs. *300–1.200 €*; evtl. leerer Installateur-Tag (~520 €)], [#text(fill: warn)[*mittel*]], [Survey-Gate (P1-07) mit Loopback; Kontingenz explizit ausweisen], [RevA; risiken B1],
  [*P5 · Markt: LoRaWAN-TRV-Verfügbarkeit*], [Nische vs. Massenmarkt unklar → Bulk-CAPEX-Annahme wackelt], [#text(fill: warn)[*mittel*]], [Beschaffungs-Research RQ4 vertiefen; 2 Hersteller anfragen], [prelim RQ4; ADR-0020],
)

= Prioritäten — die größten Bänder zuerst schließen

Bewusst zuerst die *billigen, aber wirkungsstärksten* Schritte: Die drei breitesten Kostenbänder
(K1, K2, K4) und die zwei blockierenden Entscheidungen (E1, E2) schließen mit *Information und
Entscheidungen*, nicht mit Hardware.

#table(
  columns: (auto, 1.9fr, 1.3fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: top + left,
  table.header(th("#"), th("Aktion"), th("schließt"), th("Aufwand")),
  [1], [*Zielgebäude X/Y benennen + Archetyp festlegen* (PO-Entscheidung)], [E1, E2, T5], [niedrig],
  [2], [*Heizkostenrechnung des Zielgebäudes einholen* (Tarif/Energieträger)], [K2], [niedrig],
  [3], [*WHZ-Grenzkostensatz festlegen* (45–65 €/h) für das Make-/Buy-Urteil], [K4], [niedrig],
  [4], [*Betriebsmodell entscheiden* (ereignisgesteuertes Monitoring + Portfolio)], [K3], [niedrig],
  [5], [*120-Stück-Bulk-Angebot* einholen (dnt + Vicki), Artikelnummern], [K5], [niedrig],
  [6], [*Downlink-Loopback in den Feldtest* + Simulator-Lasttest 35/120], [T1, T2, T3], [niedrig–mittel],
  [7], [*Einsparquote am Pilot messen* (netto, mit Rebound) — das breiteste Band], [K1], [hoch],
  [8], [*2. Gateway leihen* (Diversity/Position) + A/B Ziel-TRV; Walk-Survey], [T4, T8, T9], [mittel],
)

#callout(title: "Lesart der Prioritäten", color: teal)[
  Schritte 1–5 sind *Schreibtisch/Entscheidung* (Stunden bis Tage) und schließen die *größten
  Kostenbänder* — sie sollten vor jedem „wirtschaftlich ja/nein"-Urteil erledigt sein. Schritt 6–8
  sind die *messtechnischen* Lücken (Downlink, Kapazität, Diversity). Erst danach ist das
  Sizing-Modell verbindlich statt vorläufig.
]

#callout(title: "Pflege & Quellen", color: warn)[
  Dieses Register *dupliziert keine Details* — es verweist auf die Quelle, die sie hält:
  Kosten/Sensitivität → `report-b-kostenanalyse`; Prozess-/Overhead → `report-a-prozesskette`;
  Modell-Annahmen → `model.md` §10/§11; Technik-Restrisiken → `test-concept-grenzen-risiken`;
  Gebäude-/RF-Lücken → `building-typology.md` §4; Offene PO-Entscheidungen → `scope-and-requirements`
  §6/§8 und `model.md` §8. Wird ein Punkt geschlossen, hier abhaken und die Quelle aktualisieren.
]
