#import "report-template.typ": *
#show: report.with(
  title: "Offene Punkte & Unsicherheiten — konsolidiertes Register",
  subtitle: "Pro Punkt: Einordnung aus der Quelle, Bandbreite/Wirkung, erklärte Zahlen, Schweregrad und wodurch er sich schließt",
  meta: "Projekt whz-lora · WHZ · 2026-06-30 · Single Source für offene Punkte · verknüpft (dupliziert nicht) test-concept, grenzen-risiken, report-a/b, model, building-typology",
)

// Nur Kapitel (Ebene 1) nummerieren; die Einträge (Ebene 2) tragen ihre stabile ID im Titel.
#set heading(numbering: (..n) => if n.pos().len() == 1 { numbering("1.", ..n) })

// --- Bausteine für die einheitliche Eintrags-Darstellung ---
#let sev(l) = box(
  fill: if l == "hoch" { bad } else if l == "mittel" { warn } else { teal },
  inset: (x: 6pt, y: 2pt), radius: 3pt,
)[#text(fill: white, weight: "bold", size: 8pt)[#upper(l)]]

#let strip(level, info) = block(spacing: 6pt)[#sev(level) #h(6pt) #text(size: 8.5pt, fill: muted)[#info]]

#let band(..rows) = table(
  columns: (1fr, 1fr, 1.4fr), stroke: 0.5pt + rulec, inset: 6pt, align: top + left,
  table.header(th("Fall"), th("Kennwert"), th("Wirkung")),
  ..rows.pos()
)

#let why(body) = block(spacing: 8pt)[#text(weight: "bold", fill: ink)[Warum die Zahlen sich bewegen: ]#body]

#let closes(body) = block(
  width: 100%, fill: rgb("#e8f6ee"), stroke: (left: 3pt + good),
  inset: (x: 9pt, y: 7pt), radius: 3pt, spacing: 10pt,
)[#text(weight: "bold", fill: good)[→ Schließen durch: ]#body]

#callout(title: "Wozu dieses Register — und wie es zu lesen ist", color: accent)[
  Die offenen Punkte des Projekts lagen bisher verstreut. Dieses Register führt sie an *einem Ort*
  zusammen — und gibt jedem Punkt ein eigenes Unterkapitel mit immer gleichem Aufbau:
  *Einleitung* (was es ist und was die Quelle dazu sagt) → *Bandbreite/Wirkung* (einheitliche
  Tabelle) → *Erklärung der Zahlen* → *Schweregrad* (Badge oben) → *Schließen durch* (grüner
  Abschluss). Es ist ein *lebendes* Dokument und *dupliziert keine Details* — es verweist je Punkt
  auf die Quelle, die das Detail hält.
]

= Der Kernbefund in einem Bild

Die wichtigste offene Aussage des ganzen Projekts: Die Amortisation ist *keine Zahl, sondern ein
Band* — von rund *4 Jahren bis weit über 20* — und die beiden Faktoren, die das Band aufspannen
(*Einsparquote* und *Energieträger*), sind am realen Gebäude *noch nicht erhoben*.

#figure(
  image("assets/payback-band.svg", width: 100%),
  caption: [Dasselbe System ist je nach Annahme klar wirtschaftlich (~4 J.) oder nie (>20 J.). Hardware bewegt den Payback nur um ca. 2 Jahre — die großen Bänder kommen aus Einsparquote, Tarif und Betriebskosten (Quelle: report-b, Tornado/Netto-Effekt).],
)

#plain[Die größten Kosten-Unsicherheiten schließt man *nicht mit mehr Hardware*, sondern mit *Information und Entscheidungen* — einer Messung am Gebäude, einer Heizkostenrechnung, einem festgelegten Stundensatz, einem benannten Zielgebäude. Quelle-Kürzel unten: „Rn" = Ranking-Zeile in `report-b`, „§11" = `model.md` Open refinements, „RevA" = `report-a`-Review, „risiken A1…" = ID im Dossier `test-concept-grenzen-risiken`, „b-typ" = `building-typology.md`.]

= Register A — Kosten-Hebel (spannen das Payback-Band auf)

== K1 — Einsparquote (netto)
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R1 · `model.md` §11])

Der dominanteste Hebel überhaupt. Report B führt ihn auf Rang 1, weil die Einsparquote direkt den
Jahresnutzen bestimmt — und der steht im *Nenner* der Payback-Rechnung. Die Quelle nennt für einen
Altbau ein *brutto*-Band von 8–12 % aus konservativer Literatur; davon ist der *Rebound* (Nutzer
heizen etwas wärmer) mit 20–30 % abzuziehen. Für das WHZ-Gebäude ist die Quote *noch nicht gemessen*.

#band(
  [pessimistisch], [~5 % netto], [Payback *> 20 J.* — praktisch nie wirtschaftlich],
  [Referenz], [~7,5 % netto (10 % brutto)], [Payback ~10,3 J. (Grenzfall)],
  [gut], [~12–15 %], [Payback ~4–6 J. (klar wirtschaftlich)],
)

#why[Halbiert sich die Quote (10 → 5 %), halbiert sich nicht der Payback — er *explodiert* auf ~83 J., weil die laufenden Kosten dann fast den ganzen Restnutzen aufzehren und der Nenner gegen null geht.]

#closes[am WHZ-Testbed/Pilot *messen*, den Rebound rechnerisch einsetzen und das Ergebnis stets als Band berichten — nie aus Herstellerprospekten übernehmen.]

== K2 — Energieträger / Tarif
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R4 · `model.md` §10])

Ein reiner *Tarif-Hebel des Gebäudes*, durch bessere Technik gar nicht beeinflussbar. Die Quelle
belegt die Preise (Destatis/BDEW für Gas, vzbv/DIW für Fernwärme) und warnt: Fernwärme ist oft ein
*Monopolpreis* mit einer Faktor-2-Spanne.

#band(
  [Gas], [0,12 €/kWh], [Payback ~10,3 J.],
  [Fernwärme], [0,16 €/kWh (+33 %)], [Payback ~6,5 J.],
  [Fernwärme-Spanne], [0,08–0,20 €/kWh], [Payback ~5–13 J.],
)

#why[Der Nutzen ist *linear im Preis je kWh*: bei gleicher gesparter Energiemenge bringt teurere Wärme mehr gesparte Euro. Ein um 33 % höherer Tarif verkürzt den Payback um rund ein Drittel.]

#closes[die *reale Heizkostenrechnung* des Zielgebäudes einholen (härtet den Wert sofort) und das Monopol-Risiko der Fernwärme dokumentieren.]

== K3 — Monitoring / OPEX
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R2])

Die größte Kosten-Stellschraube, die *wir selbst steuern können*. Die Quelle rechnet sie bottom-up
und stellt zwei Betriebsmodelle gegenüber: feste Routinestunden vs. ereignisgesteuertes Alerting —
über ein Portfolio teilen sich die Fixkosten zusätzlich.

#band(
  [Routine (12 h/a, 1 Gebäude)], [960 €/a], [Payback ~10,3 J.],
  [ereignisgesteuert], [~280 €/a], [Payback ~7,1 J.],
  [Portfolio (10 Gebäude)], [~96–200 €/Gebäude], [Payback < 7 J.],
)

#why[OPEX steht — wie der Nutzen — *jährlich* in der Rechnung; jeder gesparte Betriebs-Euro wirkt über die gesamte Laufzeit. Routine-Stunden sind reine Fixkosten, die nur selten echtem Bedarf entsprechen.]

#closes[das Betriebsmodell *ereignisgesteuert* festlegen und die Fixkosten über ein Portfolio verteilen; die Phantom-Hosting-Zeile (50 €) zugleich streichen.]

== K4 — Stundensatz (Kosten- vs. Verkaufssatz)
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R3])

Ein *struktureller Multiplikator* über alle Arbeitsstunden. Die Quelle trennt sauber den
*Verkaufssatz* (80 €/h, der Kundenpreis) vom WHZ-*Grenzkostensatz* (45–65 €/h, was eine Stunde die
WHZ wirklich kostet). Fürs eigene Make-vs-Buy-Urteil zählt der Kostensatz.

#band(
  [Verkaufssatz], [80 €/h], [Referenz (zu teuer fürs Eigen-Urteil)],
  [WHZ-Kostensatz], [45–65 €/h], [Payback ~7–8 J. (−2…3 J.)],
)

#why[Der Satz multipliziert *jede* geplante Stunde (Begehung, Installation, Betrieb). Mit dem überhöhten Verkaufssatz wirkt der Make-Pfad künstlich teuer und das Urteil kippt fälschlich Richtung „unwirtschaftlich".]

#closes[den WHZ-Grenzkostensatz festlegen und das Urteil damit rechnen; den 80-€/h-Verkaufssatz nur im Angebots-Szenario verwenden.]

== K5 — Aktor-Bulk-Preis
#strip("mittel", [Kosten-Hebel · Quelle: `report-b` R7 · `model.md` §10])

Die *weichste CAPEX-Zahl* (der Aktor ist ca. 64 % des Kern-CAPEX). Die Quelle nutzt einen
Listenpreis (m2mgermany ~70 €) *ohne* Mengenrabatt; ein echtes 120-Stück-Angebot liegt nicht vor.

#band(
  [Bulk −15 %], [~60 €/Aktor], [Kern-Payback ~4,1 J.],
  [Punktwert], [70 €/Aktor], [Kern-Payback ~4,6 J.],
  [Listenpreis (Vicki)], [~82 €/Aktor], [Kern-Payback ~5,5 J.],
)

#why[Der Stückpreis steht im *Zähler* (CAPEX): ±15 % verschieben den Kern-Payback um etwa ein halbes bis ein Jahr — spürbar, aber nicht dominant wie Quote oder Tarif.]

#closes[ein echtes *120-Stück-Angebot* (dnt *und* Vicki/MClimate) einholen und die Artikelnummer fixieren, bevor fest kalkuliert wird.]

== K6 — Hydraulischer Abgleich (Co-Maßnahme)
#strip("mittel", [Kosten-Hebel · Quelle: `report-b` §6])

Eine *separate* Maßnahme, kein Teil des LoRaWAN-Systems. Die Quelle (co2online/Finanztip) zeigt:
ein Abgleich verdoppelt grob die Einsparquote, hat aber eigene Kosten und lohnt nur, wenn die
Anlage vorher hydraulisch schief war.

#band(
  [ohne Abgleich], [Ersparnis ~10 %], [Payback (Fernwärme) ~6,5 J.],
  [mit Abgleich], [Ersparnis ~20 % (+9.000 €)], [Payback (Fernwärme) ~4,0 J.],
)

#why[Der Abgleich hebt den *Nenner* (Jahresnutzen) stark; trotz der Zusatzkosten sinkt der Payback — aber nur bei vorher unausgeglichener Anlage, sonst verpufft der Effekt.]

#closes[als eigene Co-Maßnahme mit eigenem Payback rechnen; vorher die hydraulische Schieflage prüfen.]

== K7 — Batterie-OPEX
#strip("mittel", [Kosten-Hebel · Quelle: `report-b` R8 · `risiken` H2])

Im Modell als glatter Jahresdurchschnitt geführt, real eine *gebündelte Welle*. Die Quelle weist
zudem auf den Batterietyp hin: Alkaline verliert bei Kälte massiv Kapazität.

#band(
  [geglättet], [228 €/a], [Payback ~10 J. (verschleiert die Welle)],
  [reale Welle], [~1.600 € im Wechseljahr], [Liquiditäts-Spitze],
  [Lithium statt Alkaline], [+Stückkosten], [vermeidet ~50 % Kälteverlust],
)

#why[Ein Jahresdurchschnitt verdeckt die geballte Wechselwelle; Alkaline verliert bei 0 °C bis 50 % Kapazität → die Sendeleistung bricht im Winter ein, was ungeplante Vor-Ort-Einsätze auslöst.]

#closes[die Batterie als geplante 120-Ventil-*Welle* modellieren (in einen Wartungsbesuch gebündelt) und Lithium-Primärzellen einplanen.]

== K8 — Overhead-Doppelzählung (sunk costs)
#strip("mittel", [Kosten-Hebel · Quelle: `report-a`-Review])

Die Prozesskette zählt teils bereits *bezahlte* Posten erneut. Die Quelle (Report-A-Review zu den
Schritten 1/2/5/6) hält fest: die Provisioning-App, der selbst gehostete LNS und das vorhandene
Gateway sind „sunk" — sie dürfen nicht noch einmal in den Projektpreis.

#band(
  [gebucht (redundant)], [~3.640 € Overhead], [drückt Payback über 10 J.],
  [bereinigt], [~1.500–2.400 € Overhead], [~1.500 € Spielraum],
)

#why[Doppelt gezählte Einmal-/Sunk-Kosten erhöhen scheinbar den CAPEX und schieben den Payback künstlich nach hinten — ohne dass real ein Euro mehr ausgegeben würde.]

#closes[Schritte zusammenführen, F-0005-Batch-Import statt Hand-Provisionierung, Skript-Commissioning; Erstinstallation (amortisiert) von der Wiederholung trennen.]

== K9 — Kaufmännisches fehlt
#strip("mittel", [Kosten-Hebel · Quelle: `model.md` §11 · `report-b` Verfeinerungen])

Mehrere kaufmännische Posten sind im Modell noch nicht abgebildet. Die Quelle merkt an, dass *alle*
Preisquellen netto sind und Förderung wie Diskontierung fehlen.

#band(
  [USt-Flag], [fehlt], [brutto vs. netto unklar],
  [Förderung BEG/BAFA], [fehlt], [kann CAPEX deutlich senken],
  [diskontierter Payback (3 %)], [fehlt], [Urteil etwas länger],
)

#why[Förderung senkt den effektiven CAPEX (Zähler), Diskontierung erhöht den effektiven Payback leicht — beide verschieben die Wirtschaftlichkeitsgrenze und gehören in jedes verbindliche Angebot.]

#closes[im Modell ergänzen (USt, Marge/Risiko, Gewährleistung) und Förder- bzw. Netto-Szenarien rechnen.]

= Register B — Technik & Test-Grenzen (was der Feldtest nicht abdeckt)

== T1 — Downlink-Erreichbarkeit
#strip("hoch", [Technik · Quelle: `risiken` A1])

Der Feldtest misst nur *Uplinks*; eine Heizungssteuerung lebt aber von *Downlinks* (Sollwerte,
ADR-Kommandos). Die Quelle (Dossier A1) erklärt die *Link-Asymmetrie*: RX1 ist frequenzidentisch,
RX2 liegt auf 869,525 MHz/SF12 — beide werden im Test nicht aktiv geprüft.

#band(
  [Uplink], [gemessen (RSSI/PDR)], [belegt],
  [Downlink], [NICHT gemessen], [offen — Sollwert kommt evtl. nicht an],
)

#why[Uplink- und Downlink-Pfad sind nicht symmetrisch; ein erreichbarer Uplink garantiert keinen ankommenden Sollwert. Bleibt der Downlink aus, verharrt ADR auf hohem SF und die Airtime steigt.]

#closes[einen *Downlink-Loopback* in den Feldtest integrieren: confirmed Downlink je Punkt senden, ACK im Folge-Uplink loggen → Downlink-PDR-Karte.]

== T2 — Downlink-Duty-Cycle (Kapazität)
#strip("hoch", [Technik · Quelle: `risiken` A2])

Das Gateway *als Sender* unterliegt selbst dem Duty-Cycle — eine harte Obergrenze bei vielen
Aktoren. Die Quelle nennt die geprüften Budgets und den Befund, dass im aktuellen
Kerlink-KerOS-Pfad *gar keine* automatische Duty-Cycle-Überwachung läuft.

#band(
  [RX1 (je Subband)], [1 % = 36 s/h], [~25–34 Downlinks/h (SF12)],
  [RX2 (869,525 MHz)], [10 % = 360 s/h], [~225–360/h, geteilt über alle Geräte],
)

#why[Mit Anwendungs-Payload steigt die Time-on-Air je Frame und senkt die Zahl möglicher Downlinks/h; bei 35–120 Aktoren mit bestätigten Sollwerten wird das Budget knapp — und Überschreitungen werden still verworfen.]

#closes[eine Duty-Cycle-Last-Simulation fahren und eine explizite Downlink-Grenze ins Sizing-Modell aufnehmen.]

== T3 — Kapazität & SF12-Well (35–120 Aktoren)
#strip("hoch", [Technik · Quelle: `risiken` A3/A4])

Drei Geräte erzeugen keine Last; Kollisionen und der *SF12-Well-Effekt* zeigen sich erst bei
vielen. Die Quelle beschreibt die Rückkopplung im bestätigten Betrieb.

#band(
  [3 Geräte (Test)], [keine Last], [keine Kollisionen sichtbar],
  [35–120, confirmed], [hohe Last], [PDR-Kollaps < 10 % möglich],
)

#why[Fehlgeschlagene ACKs treiben den Spreizfaktor hoch → längere Airtime → mehr Kollisionen → noch mehr Fehlversuche: eine Rückkopplung bis zum Zusammenbruch, die mit drei Geräten strukturell nicht auftritt.]

#closes[einen `chirpstack-simulator`-Lasttest mit 35/120 Geräten fahren; ADR im Produktivbetrieb aktivieren und einen SF-Floor setzen.]

== T4 — Gateway-Position & Diversity
#strip("hoch", [Technik · Quelle: `risiken` B1/B2])

Der Test misst *eine* Gateway-Position; ob sie optimal ist und was ein zweites Gateway bringt,
bleibt offen. Die Quelle zitiert Messungen, wonach bei 53 % der Orte *nicht* der nächste Gateway
der beste Empfänger war.

#band(
  [eine GW-Position], [gemessen], [Sizing-Fehler bis Faktor 2],
  [Diversity (2 GW)], [mit 1 GW unmessbar], [+60 % Kapazität (Literatur)],
)

#why[Mit einem Gateway fehlt die Vergleichsbasis; die „1 vs. 2 GW"-Entscheidung bleibt eine Faustformel statt einer Messung — und kostet bei Fehlentscheidung Lücken oder unnötige CAPEX.]

#closes[einen Alternativ-Standort vergleichen und ein zweites Gateway für einen Termin leihen (A/B an den Worst-Case-Punkten).]

== T5 — Archetyp-Übertragung
#strip("hoch", [Technik · Quelle: `risiken` D1 · b-typ §4])

Der Test kalibriert nur den *Neubau (A)*; Plattenbau (D) und Altbau (C) sind nicht abgesichert. Die
Quelle (building-typology §4) markiert die 868-MHz-Dämpfung explizit als *extrapoliert*, nicht
gemessen.

#band(
  [Neubau A], [kalibriert], [belastbar],
  [Plattenbau D / Altbau C], [extrapoliert (RMSE 7–10 dB)], [GW-Dichte unsicher (±Faktor 2)],
)

#why[Pfadverlustmodelle streuen auch nach Kalibrierung um 7–10 dB; eine A-Kalibrierung überträgt sich nicht 1:1 auf RC-Beton — die Gateway-Zahl je Gebäude kann sich verdoppeln.]

#closes[je Archetyp mindestens eine Mess-Referenz beschaffen und im Sizing als Bandbreite mit Archetyp-Konfidenz ausweisen.]

== T6 — Bauzustand (WDVS / Low-E)
#strip("hoch", [Technik · Quelle: `risiken` E1/E2])

Wird im Rohbau gemessen, fehlen dämpfende Schichten → das Ergebnis ist *zu optimistisch*. Die
Quelle weist darauf hin, dass die WDVS-Dampfbremsfolie von innen unsichtbar ist.

#band(
  [Rohbau (Messung)], [geringere Dämpfung], [zu optimistisch],
  [Fertigbau], [+5–17 dB (Folie)], [mehr Gateways nötig],
)

#why[Metallisierte Folien und Low-E addieren eine Dämpfung, die im Rohbau noch fehlt; ohne Korrektur unterschätzt die Kalibrierung die Realität des fertigen Gebäudes.]

#closes[den Bauzustand vollständig protokollieren (Foto, Materialcode) und nach Fertigstellung eine Wiederholungsmessung ansetzen.]

== T7 — Fremdnetz-Wachstum (Koexistenz über die Zeit)
#strip("hoch", [Technik · Quelle: `risiken` G1])

Der CAF-Scan ist eine Momentaufnahme; die fremde LoRaWAN-Last *wächst*. Die Quelle nennt den
EU-Smart-Meter-Rollout (195 → 285 Mio. von 2024 bis 2029) als Treiber.

#band(
  [heute], [CAF < 2 %], [`P_Koll` unkritisch],
  [in ~3 Jahren], [CAF 5–10 %], [`P_Koll` 10–18 % (Gelb)],
)

#why[Steigt die Fremd-Airtime, steigt die Kollisionswahrscheinlichkeit *überproportional* (ALOHA) — ein heute grüner Standort kann in wenigen Jahren GW-Diversity oder SF-Optimierung als ungeplante Nachkosten erzwingen.]

#closes[Koexistenz als *Dauer-Monitoring* führen (statt Einmal-Scan) und eine SLA-Schwelle setzen (CAF > 5 % auf einem Pflichtkanal → Alert).]

== T8 — Geräte-Repräsentativität
#strip("hoch", [Technik · Quelle: `risiken` H1])

Der Test-TRV ist evtl. nicht das später beschaffte Serienprodukt. Die Quelle warnt, dass Antenne,
Firmware und ADR-Verhalten je Modell abweichen.

#band(
  [Test-TRV], [Referenz-Link-Budget], [—],
  [Serien-Aktor], [±3–6 dB], [„1 vs. 2 GW" kann kippen],
)

#why[Schon 3–6 dB anderes Link-Budget verschieben die Reichweite genug, um die Gateway-Anzahl-Entscheidung zu drehen — das Sizing stützt sich sonst auf das falsche Gerät.]

#closes[einen A/B-Test Ziel-TRV gegen Test-TRV am selben Punkt fahren und das Delta als Korrekturfaktor dokumentieren.]

== T9 — Schnappschuss, Saison & Statistik
#strip("mittel", [Technik · Quelle: `risiken` C1/C2/F1/F2])

Ein Termin, wenige Punkte — weder zeitlich noch räumlich repräsentativ. Die Quelle nennt bis
~10,6 dB Schwankung durch Belegung/HVAC und eine deutliche räumliche Unterabtastung.

#band(
  [Zeit], [1 Termin], [Saison/Belegung ±~10 dB],
  [Raum], [3–4 Punkte/Etage], [üblich 20–30; PDR-KI ±14 Pp],
)

#why[Wenige Punkte verfehlen den echten Worst-Case; ein einzelner Termin trifft nicht die Winter-Vollbelegung — beides macht die PDR-Erwartung zu optimistisch.]

#closes[einen Walk-Survey (≥ 20 Punkte/Hauptetage) ergänzen, einen Langzeit-Soak fahren und den Fade-Margin aus der Literatur (25,7 dB @ 99 % PDR) ansetzen.]

= Register C — Prozess & offene Entscheidungen

== E1 — Zielgebäude X / Y nicht benannt
#strip("hoch", [Entscheidung · Quelle: `model.md` §8 · scope §6])

Das Modell läuft mit generischen *Defaults*, weil kein reales Gebäude benannt ist. Die Quelle führt
„Target Buildings X / Y" ausdrücklich als *TBD* — eine offene PO-Entscheidung.

#band(
  [keine Gebäude benannt], [nur Defaults], [kein konkretes Urteil möglich],
  [X/Y benannt], [reale Parameter], [Modell instanziierbar],
)

#why[Ohne konkrete Fläche, Etagenzahl, Heizkörperzahl und Tarif bleibt jedes „wirtschaftlich ja/nein" hypothetisch — alle anderen Bänder hängen an diesen Eingaben.]

#closes[der PO benennt 1–2 reale WHZ-Gebäude zur Instanziierung des Modells.]

== E2 — Archetyp des Zielgebäudes
#strip("hoch", [Entscheidung · Quelle: b-typ §4 · `risiken` D1])

Neubau (A) oder Plattenbau (D)? Das bestimmt die Gateway-Dichte maßgeblich. Die Quelle
(building-typology) gibt die Faustregeln je Bauart.

#band(
  [Neubau A], [~1 GW / 2–3 Etagen], [moderate Dichte],
  [Plattenbau D], [15–25 dB/Decke], [potenziell doppelte GW-Zahl],
)

#why[RC-Beton dämpft Geschossdecken weit stärker als ein Neubau; die Wahl des Archetyps kann die Gateway-Zahl — und damit einen relevanten CAPEX-Block — verdoppeln.]

#closes[bei der Gebäude-Benennung den Archetyp festlegen und ggf. eine RF-Referenz für D beschaffen.]

== P1 — Installateur-Varianz
#strip("mittel", [Prozess · Quelle: `risiken` I1])

Der Test nutzt einen normierten 3D-Halter; im Rollout variieren Winkel und Metallabstand. Die
Quelle nennt 3–10 dB Kopplungsverlust bei unter 10 mm Metallabstand.

#band(
  [Test (normiert)], [definierte Montage], [niedrige Fail-Rate],
  [Rollout (variabel)], [streuende Montage], [+5–15 % First-Time-Fail],
)

#why[Variable Montage streut das Link-Budget; ein Teil der Aktoren startet unter der Empfangsschwelle, was die im Test gemessene Erfolgsquote im Feld nach unten zieht.]

#closes[eine Installations-Checkliste mit Foto-Pflicht (P4-03) und Stichproben-Commissioning nach Welle 1 (P4-04) einführen.]

== P2 — Provisionierungsfehler (Bulk)
#strip("mittel", [Prozess · Quelle: `risiken` I2 · P3-03])

120 Geräte per CSV-Import bergen eine Fehlerrate. Die Quelle hält fest, dass ChirpStack einen
MIC-Mismatch nur als „Device not found" loggt — Fehler fallen also spät auf.

#band(
  [3 Geräte (Test)], [trivial prüfbar], [—],
  [120 (Rollout)], [1–5 % Fehlerrate], [5–10 % offline möglich],
)

#why[Bei Massen-Import schlagen Tippfehler und Dubletten in den Schlüsseln *still* durch und zeigen sich erst beim Abnahme-Gate — dann ist Nacharbeit in belegten Räumen nötig.]

#closes[einen Charge-Abgleich Ware↔CSV (P2-05) und einen Import-Format-/Dublettencheck (P3-03) erzwingen.]

== P3 — Zugang zu (Mieter-)Räumen
#strip("mittel", [Prozess · Quelle: `risiken` I3 · P7-04])

Im leeren Neubau trivial, im Betrieb ein Engpass. Die Quelle verweist auf Fragenkatalog E10
(Zugangsbedingungen).

#band(
  [Test (leer)], [kein Zugangsaufwand], [—],
  [Betrieb (bewohnt)], [Terminkoordination], [Batteriewellen 2–3× länger],
)

#why[Zugang zu Nutzerräumen verlängert Wartungswellen erheblich und treibt die OPEX, die das Modell aktuell zu niedrig ansetzt.]

#closes[Fragenkatalog E10 verbindlich erheben und die reale Zugangsquote aus dem Piloten in die OPEX zurückführen (P7-08).]

== P4 — Survey-Tag & Zweit-Gateway-Kontingenz
#strip("mittel", [Prozess · Quelle: `report-a`-Review · `risiken` B1])

Ein stiller Kostenposten, der real auslösen kann. Die Quelle (Report-A-Review) sieht einen evtl.
leeren Installateur-Tag und ein Zweit-Gateway, das bisher als 0-€-Annahme geführt wird.

#band(
  [Zweit-Gateway], [0 € (stille Annahme)], [300–1.200 €, survey-getriggert],
  [Installateur-Tag], [1.080 € gebucht], [evtl. −520 € (streichbar)],
)

#why[Eine verschwiegene Kontingenz täuscht einen zu günstigen Payback vor; umgekehrt steckt im pauschal gebuchten Survey-Tag Einsparpotenzial, wenn die Funkprüfung schlanker geht.]

#closes[ein Survey-Gate (P1-07) mit Downlink-Loopback einführen und die Zweit-Gateway-Kontingenz explizit als auslösbare Angebotsposition ausweisen.]

== P5 — Markt: LoRaWAN-TRV-Verfügbarkeit
#strip("mittel", [Prozess · Quelle: preliminary-research RQ4 · ADR-0020])

Hält der LoRaWAN-native TRV-Markt die angenommenen Bulk-Preise? Die Quelle (RQ4) lässt das offen;
ADR-0020 legt fest, dass nur LoRaWAN-native Aktoren in den Make-Pfad zählen.

#band(
  [Massenmarkt], [~70 €/Aktor hält], [CAPEX-Annahme stabil],
  [Nische (2–3 Hersteller)], [Preis-/Liefer-Risiko], [CAPEX kann steigen],
)

#why[Ein dünner Markt ohne Wettbewerb kann Mengenrabatte ausbleiben lassen und die CAPEX-Annahme nach oben ziehen — direkt gekoppelt an K5.]

#closes[die Beschaffungs-Research RQ4 vertiefen und mindestens zwei Hersteller konkret anfragen.]

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
  Kostenbänder* — sie sollten vor jedem „wirtschaftlich ja/nein"-Urteil erledigt sein. Schritte 6–8
  sind die *messtechnischen* Lücken (Downlink, Kapazität, Diversity). Erst danach ist das
  Sizing-Modell verbindlich statt vorläufig.
]

#callout(title: "Pflege & Quellen", color: warn)[
  Dieses Register *dupliziert keine Details* — es verweist je Punkt auf die Quelle, die sie hält:
  Kosten/Sensitivität → `report-b-kostenanalyse`; Prozess-/Overhead → `report-a-prozesskette`;
  Modell-Annahmen → `model.md` §10/§11; Technik-Restrisiken → `test-concept-grenzen-risiken`;
  Gebäude-/RF-Lücken → `building-typology.md` §4; offene PO-Entscheidungen → `scope-and-requirements`
  §6/§8 und `model.md` §8. Wird ein Punkt geschlossen (gemessen/entschieden), hier abhaken und die
  Quelle aktualisieren.
]
