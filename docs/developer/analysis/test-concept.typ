#import "report-template.typ": *
#show: report.with(
  title: "Testkonzept — LoRaWAN-Funkabdeckung, -Stabilität & -Koexistenz",
  subtitle: "Mini-Messkampagne im WHZ-Neubau · empirische Kalibrierung des Sizing-Modells (Studien-Phase 4)",
  meta: "Projekt whz-lora · WHZ · Rev. 2026-07-02 · 1 Kerlink-Gateway + dedizierter Testknoten + wenige TRV-Aktoren · ADR aus, feste SF · fünf Messphasen, abgestimmt auf das Register offener Punkte",
)

#callout(title: "Worum es geht", color: accent)[
  Das Sizing-Modell der Studie stützt sich auf einige Funk-Kennzahlen, die bisher nur
  *aus der Literatur* (teils nicht einmal LoRa-spezifisch) stammen. Diese Kampagne misst
  sie *am realen Neubau* nach — mit minimalem Aufbau, systematisch und reproduzierbar.
  Neu in dieser Revision ist die *Abstimmung auf das Register offener Punkte*
  (`offene-punkte-register.pdf`): Jede Messung liefert gezielt Daten für einen dort
  benannten offenen Punkt. Dafür kommen zwei Phasen hinzu — ein *passiver*
  Fremd-LoRaWAN-Scan (Koexistenz, H5) und ein *Downlink-Loopback* (H6), der erstmals prüft,
  ob auch der *Rückweg* zum Aktor (Sollwerte, Stellbefehle) am ungünstigsten Punkt ankommt.
  Ergebnis: belastbare, gebäudespezifische Zahlen statt geschätzter Defaults — und ein
  Feldtest, dessen Ausbeute nachweislich die richtigen offenen Fragen bedient.
]

= Ausgangslage & Erkenntnisse

Aus der Studie (`preliminary-research.md`, `model.md`) stehen die folgenden Größen fest —
mit *sehr unterschiedlicher Konfidenz*. Genau die unsicheren Werte sind das Ziel des Tests.

#table(
  columns: (1.5fr, auto, auto, 1.4fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 1 { center } else { left },
  table.header(th("Modellgröße"), th("Studienwert"), th("Konfidenz"), th("Herkunft")),
  [Dämpfung pro Geschossdecke], [ca. 10 dB], [#text(fill: warn)[mittel]], [sekundär belegt, kein 868-MHz-Direktwert],
  [Low-E-Glas-Dämpfung], [35–60 dB], [#text(fill: bad)[niedrig]], [Patent/5G-Literatur, *nicht* LoRa-gemessen],
  [Funk-Reserve für 99 % PDR], [25,7 dB], [#text(fill: warn)[Hypothese]], [arXiv 2510.04346, *anderes* Gebäude],
  [Gateway-Empfindlichkeit @ SF12], [−140 dBm], [#text(fill: good)[hoch]], [Kerlink-Datenblatt (Referenz)],
  [Gateway-Dichte (Archetyp A)], [ca. 1 GW / 2–3 Etagen], [#text(fill: bad)[niedrig]], [Faustregel],
  [Fremd-LoRaWAN-Last am Standort], [unbekannt], [#text(fill: bad)[offen]], [bisher nicht erhoben — Ziel H5],
  [Downlink-Erreichbarkeit (Rückweg)], [ungeprüft], [#text(fill: bad)[offen]], [nur Uplink belegt — Ziel H6 (Register T1)],
)
#plain[Den rot/gelb markierten Zahlen vertrauen wir nicht blind — wir messen sie nach. Fremd-LoRaWAN-Last und Downlink-Erreichbarkeit sind überhaupt erst zu erheben.]

= Das Gebäude als Messumgebung

Bevor eine einzige Zahl entsteht, muss klar sein, *wo* und *wogegen* gemessen wird. Der
WHZ-Neubau ist mehrgeschossig und hat unterschiedliche Wandaufbauten — teils ohne
gesicherte Planwerte. Dieses Kapitel macht die Unsicherheit explizit und legt fest, wie
der Test sie *auflöst* statt sie zu überspielen.

== Mehrgeschossige Messung: warum die Etage zählt

Ein LoRaWAN-Gateway versorgt nicht ein einzelnes Stockwerk, sondern idealerweise das ganze
Gebäude. Der dominierende Pfadverlust ist dabei *nicht* die horizontale Distanz innerhalb
einer Etage, sondern die *Zahl der Geschossdecken* zwischen Gateway und Endgerät.
Literaturwerte für Stahlbetondecken liegen bei 8–15 dB je Decke (868 MHz); für diesen
Neubau (GEG/EH-55, Verbundaufbau unbekannt) existiert kein Direktwert. Deshalb wird als
*vertikale Säule* über mindestens drei Etagen im selben Treppenhaus gemessen — erst dann
lässt sich ein Dämpfungs-Gradient (dB/Etage) mit der nötigen statistischen Absicherung
ableiten (H1).

== Unbekannte Wandtypen: Bandbreite statt Annahme

Mehrere Wandaufbauten sind nicht durch Planunterlagen gesichert. RF-kritisch sind:

- *Low-E-Metallic-Verglasung* (GEG/EH-55): ca. +24–40 dB gegenüber Klarglas — die größte
  Einzelunsicherheit im Modell und der wertvollste gebäudespezifische LoRa-Direktmesswert (H3).
- *WDVS-Folienlagen an der Außenwand*: ca. +5–17 dB je nach Ausführung. Da die Folie von
  innen nicht sichtbar ist, lässt sie sich nicht nachträglich aus Fotos rekonstruieren —
  sie *muss* während des Zugangs dokumentiert werden.
- *Innenwände*: Gipskarton-Ständer (ca. 1–3 dB), Kalksandstein (ca. 8–12 dB),
  Stahlbeton mit Ausfachung (ca. 15–25 dB) — drei Klassen, die sich im Messbild deutlich
  unterscheiden.

#plain[Wo das Material nicht sicher bestimmbar ist, weisen wir keinen Mittelwert aus, sondern eine *Bandbreite*: untere Grenze = der Messwert selbst, obere Grenze = Worst-Case der Materialklasse + 20–25 dB Fade-Margin. Gesichert ist die Abdeckung erst, wenn *beide* Grenzen das Kriterium H2 erfüllen.]

== Protokollpflicht vor Ort

Vor jeder Messreihe wird der Bauzustand protokolliert — sonst ist ein „schlechter" Wert
später nicht interpretierbar:

- Foto des Wandquerschnitts (sichtbare Lagen), beschriftet mit Kurzcode: `GK` = Gipskarton,
  `KS` = Kalksandstein, `SB` = Stahlbeton, `LoE` = Low-E-Verglasung, `WDVS` = Dämmfassade.
- Vermerk, ob Low-E-Folie erkennbar ist (Stift-Spiegeltest: einfaches Glas zeigt *ein*
  Spiegelbild, Low-E *zwei* versetzte).
- Etage und Raumlage jedes Messpunkts im Grundriss markiert (Foto genügt).

Punkte, deren Material nach der Messung nicht zweifelsfrei feststeht, erhalten in CSV und
Bericht den Tag `MATERIAL_UNSICHER` — ihr Wert fließt in die Bandbreite ein, nicht in den
kalibrierten Einzelwert.

= Forschungsfragen & Hypothesen

Sechs testbare Fragen, jede mit Erwartung und der Entscheidung, die sie trägt:

#table(
  columns: (auto, 1.3fr, 1fr, 1.2fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("#"), th("Frage"), th("Hypothese / Erwartung"), th("Entscheidung, die davon abhängt")),
  [H1], [Wie stark dämpft eine *Geschossdecke* real (868 MHz, Neubau)?], [8–12 dB/Etage], [Gateway-Dichte für Archetyp A],
  [H2], [Reicht *ein* Gateway bis zum entferntesten Heizkörper bei SF12?], [hängt an dB/Etage × Etagen + Low-E], [Fragenkatalog F7 → *1 vs. 2 Gateways*],
  [H3], [Wie viel dämpft das *Low-E-Glas* real (LoRa, 868 MHz)?], [20–40 dB (erstmals LoRa-gemessen)], [RF-Klasse / Pfadverlust — der wertvollste Einzelwert],
  [H4], [Bringt eine *High-Gain-Antenne* indoor messbar mehr?], [horizontal ja, vertikal evtl. schlechter; Netto gering], [Antennen- & Platzierungswahl (Kostenfrage)],
  [H5], [Ist am Standort ein *fremdes LoRaWAN* aktiv, und wie hoch ist dessen Kanal-Airtime-Anteil?], [CAF < 2 % (unkritisch; typisch für Wohngebiete)], [Kanalplan, Zweit-Gateway-Risiko & PDR-Erwartung (Begehung)],
  [H6], [Erreicht ein *bestätigter Downlink* (Sollwert) den Aktor auch am Worst-Case-Punkt?], [Downlink-PDR ≥ 95 % bei SF12 (Rückweg schwächer als Uplink)], [ob eine Klasse-A-Steuerung trägt (Register T1); Budget bei Last → Simulator (T2)],
)

= Abstimmung auf das Register offener Punkte

Diese Kampagne ist bewusst so zugeschnitten, dass jede Messung *Daten für einen konkreten
offenen Punkt* des Projekts liefert. Grundlage ist das konsolidierte Register
(`offene-punkte-register.pdf`, Register B „Technik & Test-Grenzen"). Die folgende Tabelle
macht die Zuordnung explizit — und benennt ehrlich, was der Feldtest *schließt*, was er nur
*informiert* und was *außerhalb* seiner Reichweite bleibt (mit Verweis auf die ergänzende
Methode). Sie ist zugleich die Abhak-Liste: Jeder gemessene Wert wird im Register am
zugehörigen Punkt vermerkt.

#table(
  columns: (auto, 1.4fr, 1.5fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: top + left,
  table.header(th("Offener Punkt"), th("Was er braucht"), th("Wie dieser Test ihn bedient"), th("Grad")),
  [*T1* Downlink-Erreichbarkeit], [Downlink-PDR je Punkt], [Messphase 5 — Downlink-Loopback (bestätigter Downlink, ACK-Quote; am Test-TRV, Zielgerät via T8-Korrekturfaktor)], [#text(fill: good)[schließt (Feld)]],
  [*T4* GW-Position & Diversity], [Alternativ-Standort / 2. GW im A/B], [Kontingenz-Szenario B: zweiter Anker + geliehenes 2. GW an denselben Punkten], [#text(fill: warn)[informiert → schließt bei Leihgerät]],
  [*T6* Bauzustand WDVS/Low-E], [Materialprotokoll + Wiederholung], [Protokollpflicht + `MATERIAL_UNSICHER`-Tag + Low-E-Paar (H3)], [#text(fill: good)[schließt (bei Fertigbau-Wdh.)]],
  [*T7* Fremdnetz (Koexistenz)], [CAF-Momentaufnahme + Trend], [Messphase 4 — passiver CAF-Scan (H5)], [#text(fill: warn)[Momentaufnahme; Trend → Monitoring]],
  [*T8* Geräte-Repräsentativität], [A/B Ziel-TRV gegen Test-TRV], [A/B an 1 Punkt: Δ Link-Budget als Korrekturfaktor], [#text(fill: warn)[schließt bei vorliegendem Ziel-TRV]],
  [*T9* Schnappschuss & Statistik], [≥ 20 Punkte/Etage, Soak, Fade-Margin], [Fixpunkt-Soak + optionaler Walk-Knoten + Fade-Margin-Ansatz], [#text(fill: warn)[räumlich geschlossen; Saison offen (1 Termin)]],
  [*T2* Downlink-Duty-Cycle], [Last-Simulation Downlink-Budget], [→ `chirpstack-simulator` (Labor, Ergänzung zu Phase 5)], [#text(fill: muted)[außerhalb Feld → Simulator]],
  [*T3* Kapazität / SF12-Well], [Lasttest 35/120 Aktoren], [→ `chirpstack-simulator` (Labor)], [#text(fill: muted)[außerhalb Feld → Simulator]],
  [*T5* Archetyp-Übertragung], [Referenz je Archetyp], [nur Neubau A kalibriert], [#text(fill: muted)[außerhalb → 2. Archetyp-Messung]],
  [*K1* Einsparquote], [Energie-Ersparnis am Pilot], [Funktest misst keine Energie], [#text(fill: muted)[außerhalb → Pilot/Testbed]],
)
#plain[„schließt" = der Test liefert den belastbaren Wert selbst · „informiert" = er verengt die Unsicherheit, schließt aber erst mit einer Zusatzbedingung (Leihgerät, Fertigbau, Zielgerät) · „außerhalb" = am Feldtermin nicht erzeugbar, gehört in Simulator, zweite Messung oder Pilot.]

= Die fünf Messphasen im Überblick

Die Kampagne ist in fünf Blöcke gegliedert. Die ersten drei *senden aktiv* im Uplink mit
festem Spreizfaktor; die vierte *hört nur passiv mit*; die fünfte prüft den *Downlink*
(Rückweg) und läuft an denselben aktiven Punkten wie Phase 1/2 mit — ohne zusätzliche Begehung.

#table(
  columns: (auto, 1.4fr, 1fr, 1.3fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 2 { center } else { left },
  table.header(th("Messphase"), th("Ziel / Frage"), th("Modus"), th("Ergebnis")),
  [*1 · Abdeckung*], [Decken- & Wanddämpfung screenen (H1, H3)], [aktiv, SF9], [dB/Etage, Low-E-Dämpfung],
  [*2 · Reserve*], [reicht ein Gateway im Worst-Case? (H2)], [aktiv, SF12], [Funk-Reserve, 1-vs-2-Gateways],
  [*3 · Antenne*], [Nutzen High-Gain vs. Standard (H4)], [aktiv, A/B-Tausch], [ΔRSSI/ΔPDR je Etagenlage],
  [*4 · Koexistenz*], [stört fremdes LoRaWAN? (H5)], [passiv, alle SF], [CAF + Ampel + Begehungs-Befund],
  [*5 · Downlink*], [kommt der Sollwert an? (H6)], [aktiv, bestätigt, SF12], [Downlink-PDR je Punkt + Budget-Hinweis],
)

= Wirkungskette: von der Messung zur Entscheidung

#figure(
  image("assets/test-wirkungskette.svg", width: 100%),
  caption: [Jede der sechs Messgrößen speist genau einen Modell-Parameter und damit eine konkrete Entscheidung — nichts wird „auf Vorrat" gemessen. Die sechs Fragen H1–H6 verteilen sich auf fünf Phasen (H1 und H3 teilen sich Phase 1). Zeile 5 ergänzt die passive Koexistenz-Messung, Zeile 6 den Downlink-Rückweg zum Aktor.],
)

= Messgrößen & Qualitätskriterien

Welche Werte erfassen wir, und welche Bereiche sind interessant?

#table(
  columns: (auto, 1.2fr, 1fr, 1.4fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Größe"), th("Bedeutung"), th("Erfasst über"), th("Interessanter Bereich")),
  [RSSI], [Empfangspegel (dBm)], [`rxInfo.rssi` je Uplink], [sehr gut über −80; brauchbar bis ca. −110; kritisch unter −120 (nahe −140 Empfindlichkeit)],
  [SNR], [Abstand zum Rauschen (dB)], [`rxInfo.snr` je Uplink], [LoRa funkt *unter* dem Rauschen → negativ ist normal; über 0 komfortabel; −20 dB = Demod-Limit (gesättigt)],
  [PDR (Uplink)], [Paket-Zustellrate Hinweg (%)], [empfangen ÷ gesendet (fCnt)], [ab 99 % exzellent; ab 80 % für Heizung ausreichend; unter 50 % = Abdeckungslücke],
  [PDR (Downlink)], [Zustellrate Rückweg (%) — Sollwert erreicht den Aktor (H6)], [bestätigte Downlinks: ACKs ÷ gesendet], [ab 95 % gut; unter 80 % = Steuerbarkeit kritisch, RX2-Anteil/Budget prüfen],
  [SF], [genutzter Spreizfaktor], [im Test fest gesetzt], [SF7 reicht ⇒ ca. 14 dB Reserve bis SF12 ⇒ Punkt sicher],
  [Airtime/ToA], [Sendedauer je Paket], [aus SF/BW berechnet], [Duty-Cycle-Budget (SF12 ca. 1,15 s)],
  [σ(RSSI), σ(SNR)], [*Stabilität* über die Zeit], [Streuung der N Werte], [kleine Streuung = stabil; große = wackelig (Stabilitäts-Indikator)],
  [`CAF` (fremd)], [Kanal-Airtime-Anteil fremder Frames je Kanal/SF (Koexistenz, H5)], [Gateway-Topic, `phyPayload` parsen], [< 2 % unkritisch · 2–10 % beobachten · > 10 % kritisch (Ampel)],
  [Fremd-SF-Verteilung], [SF7–SF12 des Fremdverkehrs; SF12 dominiert Airtime ca. 30×], [`spreadingFactor` je Fremd-Frame], [SF12-Anteil > 30 % = schlecht konfiguriertes Fremdnetz],
)
#plain[„Abdeckung" = *kommt das Signal an?* (RSSI/SNR über der Schwelle). „Stabilität" = *kommt es zuverlässig und gleichmäßig an?* (hohe PDR, kleine Streuung). „Koexistenz" = *wie voll ist der Funkkanal schon?* (Fremd-Airtime `CAF`).]

= Messmethodik (De-Confounding)

#figure(
  image("assets/test-messpunkte.svg", width: 92%),
  caption: [Erst jeden Effekt einzeln isolieren, dann den kombinierten Worst-Case — sonst lässt sich aus einem schlechten Messwert nicht zurückrechnen, *woran* es lag.],
)

Fünf Methodik-Regeln machen die Messung wissenschaftlich verwertbar:
- *ADR aus, festes SF* je Phase — sonst regelt ChirpStack den Spreizfaktor selbst und keine zwei Messwerte sind vergleichbar (H2 wäre nie gemessen).
- *Baseline zuerst und zuletzt* (P0, Sichtlinie 5–10 m): beweist, dass Aufbau und Knoten funktionieren, bevor man einem „schlechten" Wert traut; der Schluss-Baseline ist der Drift-Check.
- *Duty-Cycle-konform senden* (EU868, 1 %): Sendeintervall aus der Airtime ableiten — sonst werden Protokoll-Pausen als Funkverlust fehlgedeutet und verfälschen genau die Reserve-Zahl.
- *Koexistenz passiv und parallel:* Messphase 4 sendet nichts, sondern hört nur mit — sie braucht kein De-Confounding (rein beobachtend) und läuft am besten über die gesamte Termin-Dauer mit.
- *Downlink-Loopback am selben Punkt:* Messphase 5 sendet je aktivem Punkt ein bis mehrere *bestätigte* Downlinks (z. B. `DevStatusReq` oder ein TRV-Konfig-Kommando) und zählt die ACKs im nächsten Uplink — so entsteht die Downlink-PDR ohne eigene Begehung. Das Gateway *als Sender* unterliegt dabei selbst dem Duty-Cycle (ca. 1 % auf RX1-, 10 % im RX2-Subband): im Test unkritisch (wenige Frames), im Betrieb die Kapazitätsgrenze aus Register T2.

= Aufbau im Gelände: ein Gateway, drei Thermostate

Der Test nutzt die real verfügbare Hardware: *ein* Gateway und derzeit *drei*
LoRaWAN-Heizkörper-Thermostate (TRV). Alles ist frei im WHZ-Gelände platzierbar.
Damit daraus ein belastbarer Abdeckungs-Befund wird, müssen Standorte *und* die
Funkstrecke dazwischen lückenlos dokumentiert sein — sonst ist ein „schlechter"
Messwert später nicht zuzuordnen.

== Was bewegt wird — und was dokumentiert werden muss

Das Gateway bleibt je *Szenario* an einem festen Standort; die drei TRVs werden über
die Messpunkte verteilt. Zwei Protokoll-Ebenen halten das fest:

- *Gateway-Anker* (einmal je Szenario/Runde): EUI, Raum + Etage, Position im Grundriss
  (Foto mit Markierung), Montagehöhe, Antenne (Typ/Gewinn/Orientierung), Abstand zu
  Metall/Aufzug/Low-E-Fassade. Wird das Gateway umgesetzt, ist das ein *neues* Szenario
  mit neuer Baseline.
- *Funkstrecken-Protokoll* (je TRV-Punkt): Geraden-Distanz zum Gateway, Sichtlinie
  (LOS/NLOS), Anzahl Geschossdecken sowie Anzahl und Typ der Wände dazwischen
  (`GK`/`KS`/`SB`/`LoE`/`WDVS`), Montagehöhe und Antennen-Orientierung des TRV.

#plain[Kurz: *wo steht das Gateway, wo der Thermostat — und was liegt zwischen beiden?* Erst diese drei Angaben machen aus einem RSSI-Wert eine verwertbare Aussage über Decken, Wände und Reichweite.]

== Soak in Runden statt Walk

Drei TRVs sind das Mess-Instrument — aber als *Fixpunkt-Soak*, nicht als Lauf-Survey:
ein TRV sendet nur ca. 1 Uplink/10 min. Man platziert deshalb alle drei gleichzeitig,
sammelt je Punkt N Pakete (Soak) und setzt dann gemeinsam um. Eine Runde deckt so
*drei* Punkte parallel ab; die Runden bilden die De-Confounding-Leiter (Baseline →
vertikale Säule → horizontal → Low-E-Paar → Worst-Case).

#callout(color: warn)[
  *Zeitbudget realistisch rechnen:* Soak-Dauer ≈ N × Sendeintervall — und das gilt für
  alle drei TRVs einer Runde *gleichzeitig*. Bei Default-Intervall 10 min und N = 20 sind
  das ca. 200 min je Runde → fünf Runden ≈ 16–17 h (Zwei-Tage-Aufwand). *Gegenmittel:* das
  TRV-Sendeintervall vorab per Downlink auf ca. 5 min setzen (z. B. Milesight WT101 Kanal
  `0x8e`; MClimate Vicki Minimum 3 min) → ca. 8–9 h (ein Arbeitstag). Wer schneller screenen
  will, ergänzt einen dedizierten Testknoten (z. B. Dragino LHT52, 20-s-Intervall) für den
  Walk — die TRVs bleiben dann der realitätsnahe Soak.
]

== Realistische Montage: das fehlende Heizkörper-Metall

#figure(
  image("assets/test-trv-montage.svg", width: 100%),
  caption: [Echte TRVs sitzen am Heizkörper — das Metall schirmt eine Seite ab. Lose auf der Fensterbank fehlt dieses Metall völlig (Ergebnis zu optimistisch); ein 3D-Halter stellt wenigstens Orientierung und Höhe richtig, ein A/B-Test mit Metallplatte beziffert den Rest.],
)

Im echten Einbau sitzt der TRV am Ventil, mit dem *Heizkörper als Metallplatte* dicht
dahinter (wenige Zentimeter). Dieses Metall verstimmt die kleine Antenne, schluckt
Leistung und schattet eine Richtung ab. Die Industrie-Faustregel nennt *3–10 dB*
Effizienzverlust durch Metallnähe (Antenova) — beim geringen TRV-Einbauabstand eher im
unteren Teil dieses Fensters. Das ist eine *Größenordnung*, kein gemessener Wert: eine
868-MHz-Direktmessung am TRV-Heizkörper-Setup existiert nicht.

*Konsequenz für den Test:* Legt man den TRV lose auf die Fensterbank, fehlt dieses Metall
— das Ergebnis ist um die genannte Größenordnung *zu optimistisch*. Deshalb:

- *3D-Halter* (Ventilstutzen-Nachbau): stellt Orientierung und Höhe realitätsgetreu ein
  (Kunststoff ist bei 868 MHz funktechnisch unsichtbar). Behebt den Orientierungsfehler,
  *nicht* das fehlende Metall.
- *A/B-Metallcheck* an 1–2 Punkten: 20 Pakete frei, dann 20 Pakete mit einem Stahlblech
  (ca. 30 × 50 cm) im realen Abstand (ca. 5 cm) dahinter, sonst identische Parameter.
  ΔRSSI = der Heizkörper-Effekt. < 2 dB ⇒ vernachlässigbar; > 6 dB ⇒ als Fade-Margin-
  Zuschlag ins Sizing-Modell aufnehmen.
- *Low-E-Falle umgekehrt:* einen frei montierten TRV nicht direkt an die Scheibe legen —
  Abstand > 30 cm zu Low-E-Glas halten, sonst kippt der Fehler ins Gegenteil (zu
  pessimistisch, > 20 dB Glasdämpfung).

== Gateway-Position absichern: Alternativ-Standort & Zweit-Gateway (schließt T4)

Der Standardaufbau misst *eine* Gateway-Position — ob sie optimal ist und was ein zweites
Gateway an *Diversity* bringt (dem Gewinn dadurch, dass zwei getrennte Empfänger dasselbe
Paket hören), bleibt sonst offen (Register T4). Zwei schlanke Zusätze schließen die Lücke,
wenn der Termin es zulässt:

- *Alternativ-Anker (kostenlos):* dieselben 2–3 Worst-Case-Punkte einmal mit dem Gateway an
  einem zweiten plausiblen Standort messen. Das ΔRSSI zeigt, wie stark die Position das
  Ergebnis trägt — schon das entzerrt die „1 vs. 2 GW"-Faustformel.
- *Zweit-Gateway-Kontingenz (Leihgerät):* liegt ein zweites Gateway vor, beide gleichzeitig
  betreiben und je Punkt das *bessere* der beiden RSSI werten. Die Differenz zum
  Ein-Gateway-Fall ist der direkt gemessene Diversity-Gewinn — die Zahl, die im Modell bisher
  nur als Literaturwert (+60 % Kapazität) steht.

#plain[Beides ist ein *A/B-Vergleich*: dieselben Punkte einmal mit Variante A (ein Gateway, Referenzstandort) und einmal mit Variante B (verschobenes bzw. zweites Gateway) direkt gegeneinander.]

== Geräte-Repräsentativität: Ziel-TRV gegen Test-TRV (schließt T8)

Der Test-Aktor ist evtl. nicht das später beschaffte Serienprodukt; schon 3–6 dB anderes
*Link-Budget* (die Pegel-Bilanz von Sender bis Empfänger) können die „1 vs. 2 GW"-Entscheidung
drehen (Register T8). Sobald das Zielgerät feststeht, an *einem* Punkt beide Modelle unmittelbar
nacheinander messen (gleiche Position, gleiches SF, je 20 Pakete). Das ΔRSSI/ΔPDR ist der
*Korrekturfaktor*, mit dem sich die Kalibrierung vom Test-TRV auf das Seriengerät übertragen lässt.

= Messpunkt-Plan

Mit drei TRVs deckt jede *Runde* drei Punkte gleichzeitig ab; das Gateway steht je Runde
fest. Die Punkt-Typen bilden die De-Confounding-Leiter:

#table(
  columns: (1.2fr, 1.6fr, auto, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x >= 2 { center } else { left },
  table.header(th("Punkt-Typ"), th("Isoliert"), th("Phase / SF"), th("N")),
  [P0 Baseline], [Setup-Korrektheit (Sichtlinie)], [Anfang+Ende, SF9], [20],
  [Vertikale Säule (≥3 Etagen, selbes Treppenhaus)], [Dämpfung dB/Etage (H1)], [Messphase 1, SF9], [20/Pkt],
  [Horizontaler Lauf (eine Etage, 0 Decken)], [Wand-/Distanz-Dämpfung], [Messphase 1, SF9], [20/Pkt],
  [Low-E-Paar (innen an der Scheibe vs. 3–5 m im Raum)], [Glas-Dämpfung (H3)], [Messphase 1, SF9], [20/Pkt],
  [Worst-Case (entfernteste Ecke, höchstes/tiefstes Geschoss)], [Funk-Reserve (H2, F7)], [Messphase 2, SF12], [20/Pkt],
  [Downlink-Loopback (an aktiven Punkten, v. a. Worst-Case)], [Downlink-Erreichbarkeit (H6, T1)], [Messphase 5, SF12 bestätigt], [10/Pkt],
  [A/B Ziel-TRV (1 Punkt, sobald Zielgerät bekannt)], [Geräte-Delta (T8)], [Messphase 1, SF9], [20/Modell],
  [A/B Gateway (Alternativ-/2. Standort, Kontingenz)], [Position & Diversity (T4)], [Worst-Case-Punkte, SF12], [20/Pkt],
  [Koexistenz-Scan (passiv, *kein* Walk)], [Fremd-LoRaWAN-Last EU868 (H5)], [Messphase 4, alle SF], [≥ 60 min, empf. 120 min],
)

= Messphase 3 — Antennen-Vergleich (H4)

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
  [High-Gain-Kollinear], [ca. 8 dBi], [mehr horizontale Reichweite, aber flache Keule → Etagen ober/unter schwächer],
  [Standard, nur *höher/freier* platziert], [3 dBi], [Höhe schlägt Gewinn (ca. 14 dB von 1,5→10 m) — die *kostenlose* Alternative],
)
#callout(color: warn)[
  *Zwei Physik-Fallen, die der Test sichtbar macht:* (1) Die EU868-Grenze von 16 dBm EIRP
  deckelt die *Sendeleistung* — beim Uplink (Gerät → Gateway) hilft mehr Antennengewinn nur
  am Empfang, nicht beim Senden. (2) *Kabelverlust* frisst Gewinn: 5 m RG58 ≈ −3,3 dB ≈ ein
  ganzes 3-dBi-Upgrade. Deshalb gehört die Variante „höher/freier platzieren" mit in den Test.
]

= Messphase 4 — Fremd-LoRaWAN: Koexistenz & Störung (H5)

LoRaWAN funkt im *lizenzfreien* EU868-Band. Niemand „besitzt" diese Frequenzen — jeder
darf sie nutzen. Unser Netz teilt sie also mit allem, was in Reichweite dieselbe Technik
betreibt (Heizungs-/Wasserzähler, städtische IoT-Sensorik, fremde Forschungsnetze). Diese
Phase beantwortet, *wie voll der Kanal schon ist* und *wie groß die Störgefahr* daraus für
unsere TRV-Uplinks ist — und liefert damit zugleich den Koexistenz-Befund für die
Kunden-Begehung.

== Forschungsfrage und Erwartung

Ist im EU868-Band am WHZ-Neubau ein fremdes LoRaWAN aktiv, und wie hoch ist dessen
*Kanal-Airtime-Anteil* (`CAF`) auf den Pflicht-Uplink-Kanälen 868,1 / 868,3 / 868,5 MHz —
der einzigen passiv messbaren Kenngröße für das zu erwartende Kollisionsrisiko?

*Erwartung:* Typische EU868-Umgebungen in Wohngebieten zeigen `CAF`-Werte von 0,01–2 %
(Kozlowski & Kurek, Sensors 2021). Ein einzelnes TRV bei SF12, 1 Frame/15 min erzeugt
ca. 0,14 % `CAF` je Kanal; ein fremdes Zählernetz mit 50 Geräten (SF9, 1 Frame/10 min)
ca. 0,5 % je Kanal — beides weit im unkritischen Bereich. Für einen Hochschulstandort ohne
bekannte dichte IoT-Infrastruktur erwarten wir `CAF` < 2 %. Die Messung bestätigt das
empirisch oder warnt rechtzeitig.

== Wie die Störung entsteht (Physik in Kürze)

#callout(color: accent)[
  - *Reines ALOHA, kein Listen-Before-Talk.* LoRaWAN-Geräte senden, sobald sie Daten haben,
    und halten nur die ETSI-Pflicht von 1 % Duty-Cycle je Subband ein (max. 36 s/h). Es gibt
    *keinen* koordinierten Zugriffsschutz zwischen unabhängigen Netzen — Kollisionen sind
    allein vom zeitlichen Zufall reguliert. Die drei Pflicht-Kanäle nutzt *jedes* LoRaWAN-Gerät;
    dort konzentriert sich der Interferenzdruck.
  - *Spreizfaktoren sind nur quasi-orthogonal.* Zwei Frames stören sich praktisch nur bei
    *gleichem Kanal und gleichem SF* mit überlappender Airtime. Der *Capture-Effekt* rettet
    den stärkeren, wenn er ca. 1–6 dB über dem schwächeren liegt (Semtech-Spec 6 dB,
    experimentell ~1 dB; Croce et al. 2018). Bei *unterschiedlichem* SF ist die Isolation
    groß (−8…−25 dB SIR) — aber nicht perfekt: ein nahes fremdes SF7-Signal kann einen
    SF8-Frame durchaus stören.
]

== Was wir messen

- *`CAF` je Kanal/SF* `[%/h]` — Hauptmetrik: belegter Airtime-Anteil fremder Frames,
  berechnet als `(Fremd-Frames/h × T_air_SF) / 3600`.
- *Fremd-Frames/h je Kanal* — Rohzählung (aus `CAF` und `T_air` rückrechenbar).
- *Geschätzte Kollisions-Wkt.* `P_Koll` — siehe Ampel unten.
- *Fremd-SF-Verteilung (SF7–SF12)* — zeigt, ob das Fremdnetz ADR-optimiert (SF7/8) oder
  schlecht konfiguriert (SF12-lastig) ist; SF12-Frames dominieren `CAF` überproportional.
- *RSSI fremder Frames* — Näherung für die Distanz des Fremd-Senders (relevant für den Capture-Effekt).
- *MType-Verteilung* (JoinRequest / DataUp) — JoinRequests zeigen aktives Onboarding im Nachbarnetz.
- *DevAddr-Klassifikation* — eigen vs. fremd (NetID-Heuristik, s. u.).

== Erfassung: das Gateway hört alles mit

#callout(title: "Der entscheidende Topic-Pfad", color: teal)[
  Das *Application*-Topic (`application/<id>/device/+/event/up`) trägt *nur* registrierte,
  gejointe Geräte mit gültigem MIC — der Network Server verwirft unbekannte DevAddr still.
  *Fremde Geräte erscheinen dort nie.* Das *Gateway*-Topic
  (`eu868/gateway/+/event/up`) dagegen trägt *jeden* empfangenen Frame — netz- und
  betreiberunabhängig, bevor der Server filtert.
]

Physikalische Basis: Der SX1302/1303-Concentrator des iFemtoCell Evolution ist ein
Multi-SF-Parallel-Demodulator (8 Kanäle, je SF5–SF12, plus ein LoRa-Std-Kanal). Es gibt
*keine* Netz-ID-Filterung auf PHY-Ebene; der Packet-Forwarder leitet per Default alle
Frames mit *bestandenem CRC* weiter (`forward_crc_valid`). CRC-Fehler (Kollisions-Indikator)
werden gesondert gezählt, nicht als reguläre Fremd-Frames.

#table(
  columns: (1fr, 1fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Ohne Schlüssel auslesbar"), th("NICHT auslesbar")),
  [MType (MHDR), DevAddr, FCnt, FCtrl, FPort; Frequenz/Kanal, SF/BW/CR; RSSI, SNR, Airtime, Frame-Länge, CRC-Status; bei JoinRequest DevEUI + JoinEUI + DevNonce (Klartext)],
  [FRMPayload-*Inhalt* (AES-128-verschlüsselt); MIC nicht verifizierbar (kein Replay-Nachweis). Wir zählen *Funkverkehr*, lesen keine Inhalte.],
)

*Eigen vs. fremd:* Unsere DevAddr/DevEUI sind in ChirpStack bekannt — alles außerhalb ist
fremd. Grobe NetID-Heuristik: TTN (DevAddr-Präfix `0x26…/0x27…`, NetID `0x000013`),
Helium (`0x78…/0x79…`, NetID `0x00003C`), privates Netz im `0x000000`-Block; für eine
verlässliche Zuordnung die aktuelle LoRa-Alliance-NetID-Tabelle heranziehen.

*Werkzeug:* Für die Erstdiagnose genügt die ChirpStack-UI → Gateway → Tab „LoRaWAN frames"
(zeigt auch fremde Geräte, DevEUI `0000000000000000`). Für eine *quantifizierte*
`CAF`-Stundenmessung wird `field_logger.py` vom Application- auf das Gateway-Topic
umgestellt und um einen kleinen `phyPayload`-Parser (MHDR/DevAddr) erweitert — die
Mosquitto-ACL erlaubt `testsubscriber` bereits `eu868/gateway/#`. Diese Logger-Erweiterung
ist eine eigene, schlanke Folge-Direktive (Build-Schritt), noch nicht umgesetzt.

== Ampel-Schwellen (quantifiziert)

Grundlage ist die konservative ALOHA-Abschätzung `P_Koll ≈ 1 − exp(−2 · CAF)` (gleicher
Kanal und SF, Poisson-Verkehr). Sie ist eine *obere Schranke*: der Capture-Effekt senkt den
tatsächlichen PDR-Verlust, wenn unser Signal am Gateway deutlich stärker ankommt als das fremde.

#figure(
  image("assets/test-koexistenz-ampel.svg", width: 100%),
  caption: [Links: die Ampel über dem Fremd-Airtime-Anteil `CAF` und die daraus geschätzte Kollisions-Wahrscheinlichkeit `P_Koll`. Rechts: warum es überhaupt kollidiert — geteilter Kanal ohne Listen-Before-Talk; unser Gateway empfängt dabei *alle* Frames, auch die fremden.],
)

#table(
  columns: (auto, 1fr, auto, 1.6fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x <= 2 { center } else { left },
  table.header(th("Ampel"), th("CAF je Kanal/SF"), th("P_Koll"), th("Maßnahme")),
  [#text(fill: good)[*Grün — unkritisch*]], [< 2 %], [< ca. 3,9 %], [Standardkanalplan genügt; keine Maßnahme],
  [#text(fill: warn)[*Gelb — beobachten*]], [2–10 %], [ca. 3,9–18 %], [Monitoring; optionale 867-MHz-Gruppe für den Datenbetrieb priorisieren; Capture-Reserve prüfen (eigenes vs. fremdes RSSI)],
  [#text(fill: bad)[*Rot — kritisch*]], [> 10 %], [> 18 %], [Zweit-Gateway als Diversity; SF-/ADR-Konfiguration prüfen (Geräte von SF12 wegoptimieren)],
)

#callout(color: warn)[
  *Grenzen der Schwellen — ehrlich benannt:* (1) Sie gelten für *co-SF*-Kollisionen;
  Inter-SF-Störung (fremdes Netz auf anderem SF, ca. −16 dB SIR) ist *nicht* voll erfasst —
  bei hoher Inter-SF-Last sind sie zu optimistisch. (2) *SF12-Frames* dominieren `CAF` (ca.
  30× länger als SF7): 5 fremde SF12-Geräte wirken stärker als 50 SF7-Geräte. (3) Die drei
  Pflicht-Kanäle lassen sich für den *Join* nicht meiden — Kanalplan-Optimierung wirkt nur
  im laufenden Datenbetrieb.
]

== Übergang in die Kunden-Begehung (RF-Site-Survey P1-07)

Diese H5-Messung *ist* der Koexistenz-Scan-Schritt der späteren Kunden-Begehung
(Prozessmodell P1-07). Sie validiert das Verfahren an unserem eigenen Gebäude und wird so
zur wiederverwendbaren Blaupause:

- *Vorab am Schreibtisch (P1-05):* TTN-Mapper und Helium-Karte des Zielgebiets prüfen —
  kostenloser Erst-Indikator, ob in der Umgebung schon Netze aktiv sind.
- *Vor Ort (P1-06/07):* `field_logger.py` im Koexistenz-Modus ≥ 60–120 min passiv mitlaufen
  lassen (kein Walk, nur Strom + LAN); parallel Wandtypen je Etage fotografieren.
- *Ins RF-Survey-Protokoll* wandert ein Feld „Band-Occupancy / Koexistenz-Befund": CSV-Auszug,
  Ampel-Bewertung („kein Fremdnetz" / „aktiv, geringe Last `CAF` X %" / „aktiv, hohe Last") und
  die abgeleitete Empfehlung (Standardplan / 867-MHz-Priorisierung / Zweit-Gateway).

*Wert für den Kunden:* Ein *vor* der Installation dokumentierter `CAF`-Wert trennt später
Gebäude-, Geräte- und Störungsursachen sauber, liefert ein messbares Argument für oder gegen
ein Zweit-Gateway und erlaubt realistische PDR-Zusagen (z. B. 96–99 % statt garantierter
100 %) — bei `CAF` < 2 % der Beweis der Unbedenklichkeit, darüber der Beleg für nötige Maßnahmen.

#callout(title: "Belege (H5)", color: teal)[
  ChirpStack-Doku, Frame-Logging (Gateway-Stream zeigt Nachbarnetz-Frames):
  #link("https://www.chirpstack.io/docs/chirpstack/features/frame-logging.html"). ALOHA/Duty-Cycle
  (TTN). SF-Orthogonalität & Capture: Croce et al., arXiv:1803.06534; Hoeller et al.,
  arXiv:1808.01761. Reale Kanalauslastung: Kozlowski & Kurek, MDPI Sensors 2021. ALOHA-Kapazität:
  Semtech TN1300.05; Adelantado et al., arXiv:1607.08011.
]

= Messphase 5 — Downlink-Erreichbarkeit: der Rückweg zum Aktor (H6)

Alle bisherigen Phasen messen den *Uplink* (Aktor → Gateway). Eine Heizungssteuerung lebt aber
vom *Downlink* (Gateway → Aktor): Sollwerte, Stellbefehle, Konfiguration. Uplink- und
Downlink-Pfad sind *nicht* symmetrisch — ein erreichbarer Uplink garantiert keinen ankommenden
Sollwert. Diese Phase schließt den in Register T1 benannten offenen Punkt und liefert eine
*Downlink-PDR-Karte* je Messpunkt.

== Warum der Rückweg gesondert zählt

LoRaWAN-Aktoren sind *Klasse-A*-Geräte: Ein Downlink kann sie nur in einem der zwei kurzen
Empfangsfenster erreichen, die das Gerät *nach jedem eigenen Uplink* öffnet — *RX1* (gleiche
Frequenz und SF wie der Uplink, 1 s danach) oder *RX2* (fest 869,525 MHz, SF12, 2 s danach).
Verpasst der Server beide Fenster, wartet der Befehl bis zum nächsten Uplink. Drei Effekte
machen den Downlink anfälliger als den Uplink:

- *Asymmetrische Pegelbilanz:* Der Aktor empfängt mit kleiner, oft metallnaher Antenne
  (Heizkörper) — der Empfang *am Aktor* ist meist schlechter als der am hochgelegenen Gateway.
- *RX2 ist der langsame Rückfall:* Fällt RX1 aus, landet alles auf RX2 — fest bei SF12 und auf
  *einem* geteilten Kanal (869,525 MHz). Dessen Subband (g3) hat zwar das großzügigere
  10-%-Duty-Cycle, doch die lange SF12-Airtime und der *eine* gemeinsame Kanal machen ihn zum
  Engpass — nicht das Budget (Register T2).
- *Gateway-Duty-Cycle:* Das Gateway *als Sender* teilt sich das Sendezeit-Budget je Subband —
  ca. 1 % auf den RX1-Kanälen (868,x), 10 % im RX2-Subband g3. Bei vielen Aktoren mit bestätigten
  Sollwerten wird es dennoch knapp (Register T2).

== Wie der Loopback misst

An denselben aktiven Punkten (Schwerpunkt Worst-Case) wird je Punkt ein *bestätigter* Downlink
ausgelöst und die Bestätigung gezählt:

+ In ChirpStack einen *confirmed Downlink* einreihen — entweder ein MAC-Kommando
  (`DevStatusReq`, antwortet mit Batterie/SNR) oder ein harmloses TRV-Konfig-Kommando auf einem
  Test-FPort.
+ Das Gerät quittiert mit gesetztem *ACK*-Bit (Acknowledgement, Empfangsbestätigung) im nächsten
  Uplink; ChirpStack meldet Zustellung bzw. Timeout je Versuch.
+ *Downlink-PDR* = quittierte ÷ gesendete Downlinks je Punkt (empfohlen N = 10 je Punkt, wegen
  der Soak-Zeit weniger als beim Uplink).
+ Notieren, ob die Zustellung über *RX1* oder *RX2* erfolgte (im Frame-Log erkennbar) — reiner
  RX2-Betrieb trotz gutem Uplink ist ein Frühwarnzeichen für knappes Downlink-Budget.

#table(
  columns: (auto, 1fr, 1.6fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 1 { center } else { left },
  table.header(th("Downlink-PDR (Worst-Case)"), th("Bewertung"), th("Konsequenz")),
  [≥ 95 %], [#text(fill: good)[*gut*]], [Klasse-A-Steuerung trägt; Standardplan genügt],
  [80–95 %], [#text(fill: warn)[*grenzwertig*]], [Sollwert-Wiederholung einplanen; RX2-Anteil prüfen],
  [< 80 %], [#text(fill: bad)[*kritisch*]], [Downlink limitiert die Steuerung — Gateway-Position / 2. GW (T4) oder Antenne (H4) nötig],
)

== Grenze: Kapazität bei vielen Aktoren gehört ins Labor

Der Feld-Loopback beweist die *Erreichbarkeit* mit drei Geräten — er zeigt *nicht* das
Downlink-Budget bei 35–120 Aktoren (Register T2/T3). Diese Kapazitätsfrage (Duty-Cycle-Sättigung,
SF12-Well) ist am realen Termin nicht erzeugbar und gehört in einen *Simulator-Lasttest* mit dem
`chirpstack-simulator` (35/120 Geräte, bestätigter Betrieb) — eine Schreibtisch-Ergänzung, die
denselben offenen Punkt vom Kapazitäts-Ende her schließt. Feld-Loopback und Simulator-Lasttest
sind im Register bewusst als *ein* Schritt gebündelt (Priorität 6).

#callout(title: "Werkzeug (Folge-Direktive)", color: teal)[
  Der Downlink-Loopback braucht das Einreihen bestätigter Downlinks (ChirpStack-API/UI) und das
  Auslesen von TX-Ack/ACK — dieselbe schlanke `field_logger.py`-Erweiterung wie für Messphase 4
  (Gateway-Topic), nur um einen Downlink-Zähler ergänzt. Für die Erstdiagnose genügt die
  ChirpStack-UI (Device → *Queue* zum Einreihen, *LoRaWAN frames* zum Ablesen von ACK und
  RX1/RX2). Noch nicht umgesetzt.
]

= Technischer Aufbau

*Hardware* — die Strom- und Compose-Grundlage steht bereit; der Stack lässt sich am
Gateway-Standort betreiben und frei im Gebäude positionieren:
- *Gateway:* Kerlink Wirnet iFemtoCell Evolution, EUI vom Geräte-Label; Standardantenne 3 dBi + eine High-Gain-Antenne für H4. Montage zentral, ≥ 2 m hoch (besser 3–4 m), bei Mehrgeschoss-Messung auf der mittleren Etage, Antenne horizontal (Hauptkeule nach oben/unten).
- *Mess-Instrument (tragend):* die drei vorhandenen LoRaWAN-TRVs — im 3D-Halter (echte Orientierung/Höhe), ADR aus, feste TX-Leistung 14 dBm, festes SF, Sendeintervall für den Test auf ca. 5 min gesetzt. Eingesetzt als *Fixpunkt-Soak in Runden* (s. Kapitel „Aufbau im Gelände"), nicht als Walk.
- *Optional schneller Screen:* ein dedizierter Testknoten (z. B. Dragino LHT52 ca. 21 €, Intervall 20–120 s) beschleunigt einen Walk über viele Punkte; die TRVs bleiben der realitätsnahe Soak.
- *Strom/Backhaul:* Netz am Standort (jetzt verfügbar) + LAN, oder der bewährte USB-C-RNDIS-Pfad aus ADR-0018 (Strom + Backhaul über ein Kabel).

*Software* — der vorhandene whz-lora-Stack:
- `docker compose up -d --wait` (ChirpStack v4, Gateway Bridge, Mosquitto, PostgreSQL, Redis).
- `scripts/field_logger.py` (MQTT-Subscribe → CSV je Frame, nach dem `smoke_test.py`-Muster). Für Messphase 4 vom Application- auf das Gateway-Topic `eu868/gateway/+/event/up` umgestellt; für Messphase 5 zusätzlich bestätigte Downlinks einreihen (ChirpStack-API/UI) und TX-Ack/ACK in die CSV zählen — dieselbe Folge-Direktive.
- Device-Profil mit *ADR = Disabled*; Gateway mit *`stats_interval` = 30*.

= ChirpStack startklar machen

+ *Vortag (Generalprobe am Schreibtisch):* `docker compose up -d --wait`, dann `py -3.12 scripts/smoke_test.py` — muss grün sein. Eliminiert die Klasse „stiller Stack" vor dem Termin.
+ *Reales Gateway registrieren* mit echter EUI vom Label und `stats_interval` = 30 (sonst meldet die UI fälschlich „offline" trotz ankommender Frames). Smoke-Test-Gateway und Real-Gateway sind zwei getrennte Einträge.
+ *Device-Profil „WHZ-Feldtest-EU868"* anlegen: Region EU868, feste DR (DR0 = SF12 / DR3 = SF9 je Phase). *ADR sicher aus:* ChirpStack v4 hat keinen einfachen „ADR = aus"-Schalter — entweder das Gerät sendet ADR = 0 (geräteseitig deaktivieren), oder im Profil einen No-Op-ADR-Algorithmus hinterlegen; danach im Frame-Log prüfen, dass der SF konstant bleibt. TRV-Sendeintervall per Downlink auf ca. 5 min setzen. Testknoten + TRVs per OTAA mit gedruckten Schlüsseln registrieren.
+ *Join bestätigen* (im selben Gebäude wie der Stack), bevor es losgeht — falscher AppKey loggt still „MIC invalid".
+ *`field_logger.py` vorbereiten:* `app_id` der Test-Application eintragen; Firewall-Regeln (UDP 1700 + ICMPv4) aktiv; Laptop-Standby aus. Für Messphase 4: prüfen, dass die Gateway-Bridge keine `[filters]` (NetID/JoinEUI) gesetzt hat — sonst werden Fremd-Frames unterdrückt.
+ *Vor Ort:* Gateway am fixen, zentralen Standort montieren (Antenne ≥ 2 m, senkrecht, ≥ 1 m von Metall/Aufzug/Low-E-Fassade); Position für die *gesamte* Kampagne einfrieren.

= Testparameter (Übersicht)

#table(
  columns: (1.4fr, 1fr, 1.6fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Parameter"), th("Wert"), th("Begründung")),
  [Aufbau], [1 Gateway + 3 TRVs], [frei platzierbar; Fixpunkt-Soak in Runden (3 Punkte/Runde)],
  [ADR], [*aus*], [nicht verhandelbar — sonst keine vergleichbaren Messwerte; in v4 kein simpler Schalter (s. Setup)],
  [SF Messphase 1 (Coverage)], [SF9 (DR3)], [Screen über viele Punkte, Airtime ca. 144 ms],
  [SF Messphase 2 (Reserve)], [SF12 (DR0)], [robustester Modus — misst die Reserve],
  [TX-Leistung], [14 dBm ERP], [EU868-Obergrenze],
  [TRV-Sendeintervall (Test)], [ca. 5 min (per Downlink)], [halbiert die Soak-Zeit ggü. Default 10 min; bei SF9/SF12 Duty-Cycle-konform],
  [Intervall dedizierter Knoten], [20 s (SF9) / ≥ 120 s (SF12)], [nur falls ein Walk-Knoten ergänzt wird; Duty-Cycle 1 %],
  [N je Punkt], [20 Pakete], [pragmatisches Mittel (PDR ca. ±13 PP bei N=20); N=10 grob, N≥50 präzise],
  [Downlink Messphase 5], [bestätigt, SF12 (RX1/RX2)], [misst Rückweg-Erreichbarkeit (H6); ACK-Quote = Downlink-PDR],
  [N Downlink je Punkt], [10 bestätigte], [weniger als Uplink-N wegen Soak-Zeit; genügt für die Ampel],
  [Soak-Dauer je Runde], [N × Intervall (ca. 100–200 min)], [gilt für alle 3 TRVs gleichzeitig; 5 Runden ≈ 8–17 h],
  [MQTT-Topic Messphase 4], [`eu868/gateway/+/event/up`], [enthält *alle* Frames inkl. Fremdnetz; Application-Topic trägt Fremdes nie],
  [Messdauer Koexistenz], [≥ 60 min, empf. 120 min], [Geräte mit 10–15-min-Intervall erscheinen sonst nicht; Schätzung braucht Stichprobe],
  [Gateway `stats_interval`], [30 s], [verhindert die Falsch-„offline"-Anzeige],
  [Messpunkte], [9–12 + 1 Passiv-Scan + Downlink an aktiven Punkten], [De-Confounding-Leiter, 3 TRVs × 3–4 Runden],
)

= Erfolgskriterien

- *Setup verifiziert:* Baseline P0 liefert RSSI −60…−80 dBm und PDR 100 % (sonst Setup- statt Funkproblem).
- *H1 erfüllt:* Dämpfung dB/Etage als Zahl aus einer vertikalen Säule über ≥ 3 Etagen.
- *H2 / F7 beantwortet:* am ungünstigsten Punkt bei SF12 ist PDR ≥ 80 % *und* RSSI über −112 dBm ⇒ ein Gateway genügt; sonst ist ein zweiter Standort dokumentiert (F8). Bei N = 20 trägt die PDR ca. ±13 PP Konfidenz — steht die 1-vs-2-GW-Entscheidung auf der Kippe, N an diesem Punkt erhöhen.
- *H3 erfüllt:* Low-E-Dämpfung als gebäudespezifischer LoRa-Messwert (ersetzt den 35–60-dB-Schätzwert).
- *H4 beantwortet:* ΔRSSI/ΔPDR High-Gain vs. Standard je Etagenlage — klare Aussage „lohnt sich / lohnt sich nicht".
- *H5 beantwortet:* `CAF` je Kanal/SF als Zahlenwert mit Ampel-Bewertung; DevAddr-Klassifikation (eigen/fremd) und SF-Verteilung des Fremdverkehrs; Ergebnis im RF-Survey-Feld „Band-Occupancy / Koexistenz-Befund".
- *H6 beantwortet:* Downlink-PDR je Punkt (bestätigte Downlinks, ACK-Quote); am Worst-Case ≥ 95 % ⇒ Klasse-A-Steuerung trägt, sonst RX2-Anteil und Downlink-Budget dokumentiert (schließt Register T1).
- *Aufbau realitätsnah:* TRVs im 3D-Halter gemessen; an 1–2 Punkten ΔRSSI des Heizkörper-Metalls (A/B mit Metallplatte) beziffert und — falls > 6 dB — als Fade-Margin-Zuschlag vermerkt.
- *Offene Punkte bedient:* sofern der Termin es zuließ — Alternativ-/Zweit-Gateway (T4) und A/B Ziel-TRV (T8) als Δ dokumentiert; andernfalls ausdrücklich als bewusst offen vermerkt.
- *Register abgestimmt:* je gemessenem Wert notiert, welchen offenen Punkt er schließt oder informiert (Tabelle „Abstimmung auf das Register"); die geschlossenen Punkte sind im Register abgehakt und die Quelle aktualisiert.
- *Reproduzierbar:* persistente CSV + Punktblatt + Grundriss-Foto in `docs/developer/analysis/`; je Szenario ein *Gateway-Anker* und je TRV-Punkt ein *Funkstrecken-Protokoll* (Distanz, Decken/Wände, LOS/NLOS) festgehalten.

= Stolperfallen

- *TRVs „abgehen" wollen* (Test-Killer): ca. 1 Uplink/10 min ⇒ ein Walk ist unmöglich. Lösung: die TRVs als *Fixpunkt-Soak in Runden* einsetzen (3 Punkte parallel), Sendeintervall auf ca. 5 min setzen und die Soak-Zeit (N × Intervall) einplanen; für schnelles Screenen einen dedizierten Knoten ergänzen.
- *ADR nicht wirklich aus* — häufigster Methodenfehler; macht jede RSSI/PDR-Messung wertlos. In ChirpStack v4 kein simpler Schalter: geräteseitig ADR = 0 oder No-Op-Algorithmus, und im Frame-Log prüfen, dass der SF über alle Punkte konstant bleibt.
- *Duty-Cycle-Falle bei SF12:* zu schnelles Senden wird gedrosselt, die Lücken sehen wie Funkverlust aus. Intervall aus der Airtime rechnen, im Bridge-Log Akzeptanz prüfen.
- *Empfindlichkeits-Referenz mischen:* −137 (generisch) vs. −140 (Kerlink). Eine Zahl pinnen (−140 dBm) und alle Schwellen konsistent daraus ableiten.
- *Bauzustand:* ein Rohbau (Low-E/Dampfsperre noch nicht final) *unterschätzt* die Dämpfung des fertigen Gebäudes — RF-relevante Schichten protokollieren und die Kalibrierung caveaten.
- *Geltungsbereich:* ein Gebäude/eine Gateway-Position kalibriert nur *Archetyp A* (Neubau, RF-hostile), nicht den Plattenbau/Stahlbeton-Fall — als *einen* empirischen Anker berichten.
- *Falsches Topic abonniert* (Koexistenz-Killer): auf `application/<id>/device/+/event/up` erscheinen Fremdgeräte nie. Topic auf `eu868/gateway/+/event/up` umstellen und im ersten Frame prüfen, ob `phyPayload` vorhanden ist.
- *Messzeit zu kurz:* fremde TRVs senden ca. 1 Frame/10–15 min — 10 min Beobachtung sind *kein* Beleg für „kein Fremdnetz". Mindestens 60 min; bei null Frames die Messdauer protokollieren.
- *Gateway-Bridge-Filter ungeprüft:* sind `[filters]` (NetID/JoinEUI) konfiguriert, werden Fremd-Frames unterdrückt. Vor Messphase 4 prüfen, dass die Filtersektion leer ist.
- *Fensterbank-Falle (fehlendes Heizkörper-Metall):* den TRV lose hinzulegen blendet die ca. 3–10 dB Metallnähe-Dämpfung aus ⇒ Ergebnis zu optimistisch. Lösung: 3D-Halter (echte Orientierung) + A/B-Metallcheck an 1–2 Punkten. *Aber:* > 30 cm Abstand zu Low-E-Glas halten, sonst kippt der Fehler ins Gegenteil (zu pessimistisch).
- *Funkstrecke nicht dokumentiert:* ohne Gateway-Anker und Pfad-Protokoll je Punkt (Distanz, Decken/Wände, LOS/NLOS) ist ein schlechter RSSI-Wert nicht zuzuordnen — Gebäude-, Geräte- oder Reichweiten-Ursache bleibt offen.
- *Downlink nur als „gesendet" werten* (Loopback-Killer): ein eingereihter Downlink ist nicht zugestellt. Nur *bestätigte* Downlinks mit ACK im Folge-Uplink zählen; Timeout = Fehlversuch. Reiner RX2-Betrieb (SF12, 869,525 MHz) trotz gutem Uplink ist ein Warnzeichen für knappes Budget.
- *Confirmed-Downlink-Sturm:* zu viele bestätigte Downlinks kurz hintereinander erschöpfen das Gateway-Sendezeit-Budget (ca. 1 % auf RX1-Kanälen, 10 % im RX2-Subband g3) — im Test wenige Frames je Punkt (N=10) einplanen; im Betrieb ist genau das die Kapazitätsgrenze T2.

#callout(color: teal)[
  *Was dieser Test auch nach der Abstimmung NICHT selbst abdeckt* — die *Kapazität* bei 35–120
  Aktoren und das Downlink-Budget unter Last (Register T2/T3 → `chirpstack-simulator`), *andere
  Archetypen* außer Neubau A (T5), das *Wachstum* der Fremd-LoRaWAN-Last über die Zeit (T7 →
  Dauer-Monitoring) sowie die tatsächliche *Energie-Einsparquote* (K1 → Pilot/Testbed, kein
  Funkmesswert). Diese Punkte stehen mit Schweregrad und ergänzender Methode im Register
  (`offene-punkte-register.pdf`) und im Begleitpapier *„Grenzen, Restrisiken & ergänzende
  Methoden"* (`test-concept-grenzen-risiken.pdf`). Neu *abgedeckt* gegenüber der Vorrevision:
  Downlink-Erreichbarkeit (Feld, T1) und — als Kontingenz — Diversity/Zweit-Gateway (T4).
]

#pagebreak()
#page(flipped: true)[
= Messblatt (zum Ausfüllen vor Ort)

Pro Messpunkt nur die Kontext-Angaben hier eintragen. *RSSI, SNR, SF, Frequenz, fCnt und PDR*
loggt `field_logger.py` je `pos_id` automatisch in die CSV
(Spalten: `timestamp_utc, dev_eui, pos_id, rssi_dbm, snr_db, sf, freq_hz, f_cnt, gw_eui`).
Punkt-Typ: `BASELINE` · `VERTIKALE_SAEULE` · `HORIZONTAL` · `LOW_E_INNEN` · `LOW_E_RAUM` · `WORST_CASE` · `ANTENNE_HIGH_GAIN` · `KOEXISTENZ_SCAN` · `DOWNLINK_LOOPBACK` · `AB_ZIEL_TRV` · `AB_GATEWAY`.
Montage: `HK` (am Heizkörper) · `3D` (3D-Halter) · `frei`. Pfad→GW: Anzahl Decken, Wände als Typ×n (`GK`/`KS`/`SB`/`LoE`/`WDVS`), `LOS`/`NLOS`.
Für `KOEXISTENZ_SCAN` zusätzlich notieren: Messdauer (min) · Fremd-Frames gesamt · stärkste fremde RSSI · erkannte NetID-Blöcke (TTN/Helium/privat/unbekannt) · Ampel-Ergebnis (Grün/Gelb/Rot).
Für `DOWNLINK_LOOPBACK` zusätzlich: gesendete/quittierte Downlinks · Downlink-PDR (%) · Zustellfenster (RX1/RX2). Für `AB_ZIEL_TRV` / `AB_GATEWAY`: gemessenes ΔRSSI/ΔPDR gegenüber der Referenz.
#v(5pt)
#block(fill: soft, inset: 7pt, radius: 3pt, width: 100%)[
  *Gateway-Anker (je Runde — vor den Messpunkten ausfüllen):*
  GW-EUI #h(1.2cm) · Standort/Etage #h(1.2cm) · Höhe #h(1cm) m · Antenne/Orientierung #h(1.2cm) · Abstand zu Metall/Low-E #h(1cm) · Baseline P0 ok #box(width: 8pt, height: 8pt, stroke: 0.5pt)
]
#v(5pt)
#table(
  columns: (auto, auto, auto, 1fr, 1fr, auto, auto, 1.5fr, auto, auto, 1.1fr),
  stroke: 0.5pt + rulec, inset: 5pt,
  table.header(th("POS_ID"), th("Runde"), th("Etage"), th("Raum / Lage"), th("Punkt-Typ"), th("SF"), th("Höhe m"), th("Pfad→GW (Decken·Wände·LOS)"), th("Montage"), th("Uhrzeit"), th("Bemerkung")),
  ..range(13).map(i => ([#v(12pt)], [], [], [], [], [], [], [], [], [], [])).flatten()
)
]
