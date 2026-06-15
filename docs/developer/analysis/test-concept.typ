#import "report-template.typ": *
#show: report.with(
  title: "Testkonzept — LoRaWAN-Funkabdeckung & -Stabilität",
  subtitle: "Mini-Messkampagne im WHZ-Neubau · empirische Kalibrierung des Sizing-Modells (Phase 4)",
  meta: "Projekt whz-lora · WHZ · 2026-06-15 · 1 Kerlink-Gateway + dedizierter Testknoten + wenige TRV-Aktoren · ADR aus, feste SF",
)

#callout(title: "Worum es geht", color: accent)[
  Das Sizing-Modell der Studie stützt sich auf einige Funk-Kennzahlen, die bisher nur
  *aus der Literatur* (teils nicht einmal LoRa-spezifisch) stammen. Diese Kampagne misst
  sie *am realen Neubau* nach — mit minimalem Aufbau, in einem halben bis ganzen Tag,
  systematisch und reproduzierbar. Ergebnis: belastbare, gebäudespezifische Zahlen statt
  geschätzter Defaults.
]

= Ausgangslage & Erkenntnisse

Aus der Studie (`preliminary-research.md`, `model.md`) stehen die folgenden Größen fest —
mit *sehr unterschiedlicher Konfidenz*. Genau die unsicheren Werte sind das Ziel des Tests.

#table(
  columns: (1.5fr, auto, auto, 1.4fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 1 { center } else { left },
  table.header(th("Modellgröße"), th("Studienwert"), th("Konfidenz"), th("Herkunft")),
  [Dämpfung pro Geschossdecke], [~10 dB], [#text(fill: warn)[mittel]], [sekundär belegt, kein 868-MHz-Direktwert],
  [Low-E-Glas-Dämpfung], [35–60 dB], [#text(fill: bad)[niedrig]], [Patent/5G-Literatur, *nicht* LoRa-gemessen],
  [Funk-Reserve für 99 % PDR], [25,7 dB], [#text(fill: warn)[Hypothese]], [arXiv 2510.04346, *anderes* Gebäude],
  [Gateway-Empfindlichkeit @ SF12], [−140 dBm], [#text(fill: good)[hoch]], [Kerlink-Datenblatt (Referenz)],
  [Gateway-Dichte (Archetyp A)], [~1 GW / 2–3 Etagen], [#text(fill: bad)[niedrig]], [Faustregel],
)
#plain[Wir vertrauen den drei rot/gelb markierten Zahlen nicht blind — wir messen sie nach.]

= Forschungsfragen & Hypothesen

Vier testbare Fragen, jede mit Erwartung und der Entscheidung, die sie trägt:

#table(
  columns: (auto, 1.3fr, 1fr, 1.2fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("#"), th("Frage"), th("Hypothese / Erwartung"), th("Entscheidung, die davon abhängt")),
  [H1], [Wie stark dämpft eine *Geschossdecke* real (868 MHz, Neubau)?], [8–12 dB/Etage], [Gateway-Dichte für Archetyp A],
  [H2], [Reicht *ein* Gateway bis zum entferntesten Heizkörper bei SF12?], [hängt an dB/Etage × Etagen + Low-E], [Fragenkatalog F7 → *1 vs. 2 Gateways*],
  [H3], [Wie viel dämpft das *Low-E-Glas* real (LoRa, 868 MHz)?], [20–40 dB (erstmals LoRa-gemessen)], [RF-Klasse / Pfadverlust — der wertvollste Einzelwert],
  [H4], [Bringt eine *High-Gain-Antenne* indoor messbar mehr?], [horizontal ja, vertikal evtl. schlechter; Netto gering], [Antennen- & Platzierungswahl (Kostenfrage)],
)

= Wirkungskette: von der Messung zur Entscheidung

#figure(
  image("assets/test-wirkungskette.svg", width: 100%),
  caption: [Jede Messgröße speist genau einen Modell-Parameter und damit eine konkrete Entscheidung — nichts wird "auf Vorrat" gemessen.],
)

= Messgrößen & Qualitätskriterien

Welche Werte erfassen wir, und welche Bereiche sind interessant?

#table(
  columns: (auto, 1.2fr, 1fr, 1.4fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Größe"), th("Bedeutung"), th("Erfasst über"), th("Interessanter Bereich")),
  [RSSI], [Empfangspegel (dBm)], [`rxInfo.rssi` je Uplink], [sehr gut über −80; brauchbar bis ~−110; kritisch unter −120 (nahe −140 Empfindlichkeit)],
  [SNR], [Abstand zum Rauschen (dB)], [`rxInfo.snr` je Uplink], [LoRa funkt *unter* dem Rauschen → negativ ist normal; über 0 komfortabel; −20 dB = Demod-Limit (gesättigt)],
  [PDR], [Paket-Zustellrate (%)], [empfangen ÷ gesendet (fCnt)], [ab 99 % exzellent; ab 80 % für Heizung ausreichend; unter 50 % = Abdeckungslücke],
  [SF], [genutzter Spreizfaktor], [im Test fest gesetzt], [SF7 reicht ⇒ ~14 dB Reserve bis SF12 ⇒ Punkt sicher],
  [Airtime/ToA], [Sendedauer je Paket], [aus SF/BW berechnet], [Duty-Cycle-Budget (SF12 ~1,15 s)],
  [σ(RSSI), σ(SNR)], [*Stabilität* über die Zeit], [Streuung der N Werte], [kleine Streuung = stabil; große = wackelig (Stabilitäts-Indikator)],
)
#plain[„Abdeckung" = *kommt das Signal an?* (RSSI/SNR über der Schwelle). „Stabilität" = *kommt es zuverlässig und gleichmäßig an?* (hohe PDR, kleine Streuung).]

= Messmethodik (De-Confounding)

#figure(
  image("assets/test-messpunkte.svg", width: 92%),
  caption: [Erst jeden Effekt einzeln isolieren, dann den kombinierten Worst-Case — sonst lässt sich aus einem schlechten Messwert nicht zurückrechnen, *woran* es lag.],
)

Drei Methodik-Regeln machen die Messung wissenschaftlich verwertbar:
- *ADR aus, festes SF* je Phase — sonst regelt ChirpStack den Spreizfaktor selbst und keine zwei Messwerte sind vergleichbar (H2 wäre nie gemessen).
- *Baseline zuerst und zuletzt* (P0, Sichtlinie 5–10 m): beweist, dass Aufbau und Knoten funktionieren, bevor man einem „schlechten" Wert traut; der Schluss-Baseline ist der Drift-Check.
- *Duty-Cycle-konform senden* (EU868, 1 %): Sendeintervall aus der Airtime ableiten — sonst werden Protokoll-Pausen als Funkverlust fehlgedeutet und verfälschen genau die Reserve-Zahl.

= Messpunkt-Plan

#table(
  columns: (1.2fr, 1.6fr, auto, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x >= 2 { center } else { left },
  table.header(th("Punkt-Typ"), th("Isoliert"), th("Phase / SF"), th("N")),
  [P0 Baseline], [Setup-Korrektheit (Sichtlinie)], [Anfang+Ende, SF9], [20],
  [Vertikale Säule (≥3 Etagen, selbes Treppenhaus)], [Dämpfung dB/Etage (H1)], [Phase 1, SF9], [20/Pkt],
  [Horizontaler Lauf (eine Etage, 0 Decken)], [Wand-/Distanz-Dämpfung], [Phase 1, SF9], [20/Pkt],
  [Low-E-Paar (innen an der Scheibe vs. 3–5 m im Raum)], [Glas-Dämpfung (H3)], [Phase 1, SF9], [20/Pkt],
  [Worst-Case (entfernteste Ecke, höchstes/tiefstes Geschoss)], [Funk-Reserve (H2, F7)], [Phase 2, SF12], [20/Pkt],
)

= Antennen-Vergleich (H4)

#figure(
  image("assets/test-antenne.svg", width: 96%),
  caption: [Mehr Antennengewinn heißt indoor nicht automatisch mehr Abdeckung: eine High-Gain-Kollinearantenne bündelt flach und kann Etagen über/unter dem Gateway schwächer versorgen.],
)

*Aufbau:* Gateway-Position einfrieren, *nur die Antenne tauschen* (A/B), an denselben
2–3 Worst-Case-Punkten plus je einem Punkt ein Geschoss über und unter dem Gateway; je
20 Pakete; gemessen wird ΔRSSI und ΔPDR gegenüber der Standardantenne.

#table(
  columns: (1.2fr, auto, 1.6fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Variante"), th("Gewinn"), th("Erwartung / Nebenwirkung")),
  [Standard-Stab (Referenz)], [3 dBi], [breite Vertikalkeule — versorgt Etagen ober/unter dem GW],
  [High-Gain-Kollinear], [~8 dBi], [mehr horizontale Reichweite, aber flache Keule → Etagen ober/unter schwächer],
  [Standard, nur *höher/freier* platziert], [3 dBi], [Höhe schlägt Gewinn (~14 dB von 1,5→10 m) — die *kostenlose* Alternative],
)
#callout(color: warn)[
  *Zwei Physik-Fallen, die der Test sichtbar macht:* (1) Die EU868-Grenze von 16 dBm EIRP
  deckelt die *Sendeleistung* — beim Uplink (Gerät → Gateway) hilft mehr Antennengewinn nur
  am Empfang, nicht beim Senden. (2) *Kabelverlust* frisst Gewinn: 5 m RG58 ≈ −3,3 dB ≈ ein
  ganzes 3-dBi-Upgrade. Deshalb gehört die Variante „höher/freier platzieren" mit in den Test.
]

= Technischer Aufbau

*Hardware* — die Strom- und Compose-Grundlage steht bereit; der Stack lässt sich am
Gateway-Standort betreiben und frei im Gebäude positionieren:
- *Gateway:* Kerlink Wirnet iFemtoCell Evolution, EUI vom Geräte-Label; Standardantenne 3 dBi + eine High-Gain-Antenne für H4.
- *Messknoten (tragend):* ein dedizierter, konfigurierbarer Testknoten (z. B. Dragino LHT52 ~21 €) — ADR aus, feste TX-Leistung 14 dBm, festes SF, Intervall 20–120 s.
- *TRV-Aktoren:* nur als unbeaufsichtigter Langzeit-/Soak-Monitor an 2–3 festen Punkten — *nicht* als Walk-Survey-Instrument (zu träge: ~1 Uplink/10 min).
- *Strom/Backhaul:* Netz am Standort (jetzt verfügbar) + LAN, oder der bewährte USB-C-RNDIS-Pfad aus ADR-0018 (Strom + Backhaul über ein Kabel).

*Software* — der vorhandene whz-lora-Stack:
- `docker compose up -d --wait` (ChirpStack v4, Gateway Bridge, Mosquitto, PostgreSQL, Redis).
- `scripts/field_logger.py` (MQTT-Subscribe → CSV je Frame, nach dem `smoke_test.py`-Muster).
- Device-Profil mit *ADR = Disabled*; Gateway mit *`stats_interval` = 30*.

= ChirpStack startklar machen

+ *Vortag (Generalprobe am Schreibtisch):* `docker compose up -d --wait`, dann `py -3.12 scripts/smoke_test.py` — muss grün sein. Eliminiert die Klasse „stiller Stack" vor dem Termin.
+ *Reales Gateway registrieren* mit echter EUI vom Label und `stats_interval` = 30 (sonst meldet die UI fälschlich „offline" trotz ankommender Frames). Smoke-Test-Gateway und Real-Gateway sind zwei getrennte Einträge.
+ *Device-Profil „WHZ-Feldtest-EU868"* anlegen: Region EU868, ADR = Disabled, DR fest (DR0 = SF12 / DR3 = SF9 je Phase). Testknoten + TRVs per OTAA mit gedruckten Schlüsseln registrieren.
+ *Join bestätigen* (im selben Gebäude wie der Stack), bevor es losgeht — falscher AppKey loggt still „MIC invalid".
+ *`field_logger.py` vorbereiten:* `app_id` der Test-Application eintragen; Firewall-Regeln (UDP 1700 + ICMPv4) aktiv; Laptop-Standby aus.
+ *Vor Ort:* Gateway am fixen, zentralen Standort montieren (Antenne ≥ 2 m, senkrecht, ≥ 1 m von Metall/Aufzug/Low-E-Fassade); Position für die *gesamte* Kampagne einfrieren.

= Testparameter (Übersicht)

#table(
  columns: (1.4fr, 1fr, 1.6fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Parameter"), th("Wert"), th("Begründung")),
  [ADR], [*Disabled*], [nicht verhandelbar — sonst keine vergleichbaren Messwerte],
  [SF Phase 1 (Coverage)], [SF9 (DR3)], [Screen über viele Punkte, Airtime ~144 ms],
  [SF Phase 2 (Reserve)], [SF12 (DR0)], [robustester Modus — misst die Reserve],
  [TX-Leistung], [14 dBm ERP], [EU868-Obergrenze],
  [Intervall SF9], [20 s], [Duty-Cycle 1 % + Puffer],
  [Intervall SF12], [≥ 120 s/Kanal o. Kanalrotation], [Duty-Cycle 1 % (SF12 ~1,15 s Airtime)],
  [N je Punkt], [20 Pakete], [trägt eine PDR-Aussage + Streuung],
  [Gateway `stats_interval`], [30 s], [verhindert die Falsch-„offline"-Anzeige],
  [Messpunkte], [~6–8], [De-Confounding-Leiter, ein Tag],
)

= Erfolgskriterien

- *Setup verifiziert:* Baseline P0 liefert RSSI −60…−80 dBm und PDR 100 % (sonst Setup- statt Funkproblem).
- *H1 erfüllt:* Dämpfung dB/Etage als Zahl aus einer vertikalen Säule über ≥ 3 Etagen.
- *H2 / F7 beantwortet:* am ungünstigsten Punkt bei SF12 ist PDR ≥ 80 % *und* RSSI über −112 dBm ⇒ ein Gateway genügt; sonst ist ein zweiter Standort dokumentiert (F8).
- *H3 erfüllt:* Low-E-Dämpfung als gebäudespezifischer LoRa-Messwert (ersetzt den 35–60-dB-Schätzwert).
- *H4 beantwortet:* ΔRSSI/ΔPDR High-Gain vs. Standard je Etagenlage — klare Aussage „lohnt sich / lohnt sich nicht".
- *Reproduzierbar:* persistente CSV + Punktblatt + Grundriss-Foto in `docs/developer/analysis/`; Gateway-Position protokolliert.

= Stolperfallen

- *TRVs als Survey-Instrument* (Test-Killer): ~1 Uplink/10 min, ADR-gelockt ⇒ 20 Pakete dauern Stunden. Lösung: dedizierter Testknoten; TRVs nur als Soak.
- *ADR vergessen zu deaktivieren* — häufigster Methodenfehler; macht jede RSSI/PDR-Messung wertlos.
- *Duty-Cycle-Falle bei SF12:* zu schnelles Senden wird gedrosselt, die Lücken sehen wie Funkverlust aus. Intervall aus der Airtime rechnen, im Bridge-Log Akzeptanz prüfen.
- *Empfindlichkeits-Referenz mischen:* −137 (generisch) vs. −140 (Kerlink). Eine Zahl pinnen (−140 dBm) und alle Schwellen konsistent daraus ableiten.
- *Bauzustand:* ein Rohbau (Low-E/Dampfsperre noch nicht final) *unterschätzt* die Dämpfung des fertigen Gebäudes — RF-relevante Schichten protokollieren und die Kalibrierung caveaten.
- *Geltungsbereich:* ein Gebäude/eine Gateway-Position kalibriert nur *Archetyp A* (Neubau, RF-hostile), nicht den Plattenbau/Stahlbeton-Fall — als *einen* empirischen Anker berichten.

#pagebreak()
#page(flipped: true)[
= Messblatt (zum Ausfüllen vor Ort)

Pro Messpunkt nur die Kontext-Angaben hier eintragen. *RSSI, SNR, SF, Frequenz, fCnt und PDR*
loggt `field_logger.py` je `pos_id` automatisch in die CSV
(Spalten: `timestamp_utc, dev_eui, pos_id, rssi_dbm, snr_db, sf, freq_hz, f_cnt, gw_eui`).
Punkt-Typ: `BASELINE` · `VERTIKALE_SAEULE` · `HORIZONTAL` · `LOW_E_INNEN` · `LOW_E_RAUM` · `WORST_CASE` · `ANTENNE_HIGH_GAIN`.
#v(4pt)
#table(
  columns: (auto, auto, auto, 1fr, 1.2fr, auto, auto, auto, auto, 1.4fr),
  stroke: 0.5pt + rulec, inset: 5pt,
  table.header(th("POS_ID"), th("Phase"), th("Etage"), th("Raum / Lage"), th("Punkt-Typ"), th("SF"), th("Antenne"), th("Decken→GW"), th("Uhrzeit"), th("Bemerkung (Bauzustand)")),
  ..range(16).map(i => ([#v(12pt)], [], [], [], [], [], [], [], [], [])).flatten()
)
]
