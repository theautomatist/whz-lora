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
  Abschluss). Fachbegriffe und Abkürzungen werden bei der ersten Verwendung im Text erklärt. Es ist
  ein *lebendes* Dokument und *dupliziert keine Details* — es verweist je Punkt auf die Quelle, die
  das Detail hält.
]

= Der Kernbefund in einem Bild

Die wichtigste offene Aussage des ganzen Projekts: Die *Amortisation* (die Zeit, bis die jährliche
Einsparung die Investition wieder hereinholt; englisch *Payback* — Investition geteilt durch
Jahresnutzen) ist *keine Zahl, sondern ein Band* — von rund *4 Jahren bis weit über 20* — und die
beiden Faktoren, die das Band aufspannen (*Einsparquote* und *Energieträger*), sind am realen
Gebäude *noch nicht erhoben*.

#figure(
  image("assets/payback-band.svg", width: 100%),
  caption: [Dasselbe System ist je nach Annahme klar wirtschaftlich (~4 J.) oder nie (>20 J.). Hardware bewegt die Amortisation nur um ca. 2 Jahre — die großen Bänder kommen aus Einsparquote, Tarif und Betriebskosten (Quelle: das Tornado-Diagramm in `report-b` — eine Sensitivitäts-Darstellung, die zeigt, wie stark jede Annahme auf das Ergebnis durchschlägt, und die Stellschrauben nach ihrer Wucht sortiert).],
)

Die wiederkehrenden Begriffe, bevor sie im Register auftauchen: *LoRaWAN* ist ein Funkstandard für
reichweitenstarke, stromsparende Geräte mit kleinen Datenmengen. Ein *Gateway* ist die
Funk-Basisstation, die alle Geräte empfängt; ein *Aktor* (englisch *TRV*, thermostatic radiator
valve) ist das LoRaWAN-Heizkörperthermostat, das ein Ventil regelt. Ein *Uplink* ist Funk vom Aktor
zum Gateway, ein *Downlink* umgekehrt. Die *Einsparquote* ist der Anteil der Heizenergie, den die
Funk-Einzelraumregelung tatsächlich spart; der *Energieträger* (Gas oder Fernwärme) bestimmt den
Preis je Kilowattstunde (kWh) und damit, wie viel Euro eine gesparte kWh wert ist.

#plain[Die größten Kosten-Unsicherheiten schließt man *nicht mit mehr Hardware*, sondern mit *Information und Entscheidungen* — einer Messung am Gebäude, einer Heizkostenrechnung, einem festgelegten Stundensatz, einem benannten Zielgebäude. Quelle-Kürzel unten: „Rn" = Ranking-Zeile in `report-b`, „§11" = `model.md` Open refinements, „RevA" = `report-a`-Review, „risiken A1…" = ID im Dossier `test-concept-grenzen-risiken`, „b-typ" = `building-typology.md`, „scope" = `scope-and-requirements`.]

= Register A — Kosten-Hebel (spannen das Payback-Band auf)

== K1 — Einsparquote (netto)
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R1 · `model.md` §11])

Der dominanteste Hebel überhaupt. Report B führt ihn auf Rang 1, weil die Einsparquote direkt den
Jahresnutzen bestimmt — und der steht im *Nenner* der Amortisations-Rechnung (Investition ÷
Jahresnutzen). Die Quelle nennt für einen Altbau ein *Brutto*-Band von 8–12 % aus konservativer
Literatur. *Brutto* ist die rohe Messung; davon ist der *Rebound* abzuziehen (dass Nutzer einen Teil
der Einsparung in mehr Wärme/Komfort umsetzen, typisch 20–30 %), was die belastbare *Netto*-Quote
ergibt. Für das WHZ-Gebäude ist sie *noch nicht gemessen*.

#band(
  [pessimistisch], [~5 % netto], [Amortisation *> 20 J.* — praktisch nie wirtschaftlich],
  [Referenz], [~7,5 % netto (10 % brutto)], [Amortisation ~10,3 J. (Grenzfall)],
  [gut], [~12–15 %], [Amortisation ~4–6 J. (klar wirtschaftlich)],
)

#why[Halbiert sich die Quote (10 → 5 %), halbiert sich nicht die Amortisationszeit — sie *explodiert* auf ~83 J., weil die laufenden Kosten dann fast den ganzen Restnutzen aufzehren und der Nenner gegen null geht.]

#closes[am WHZ-Testbed/Pilot *messen*, den Rebound rechnerisch einsetzen und das Ergebnis stets als Band berichten — nie aus Herstellerprospekten übernehmen.]

== K2 — Energieträger / Tarif
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R4 · `model.md` §10])

Ein reiner *Tarif-Hebel des Gebäudes*, durch bessere Technik gar nicht beeinflussbar. Maßgeblich ist
der *Arbeitspreis* (der Preis je verbrauchter Kilowattstunde, ohne den fixen Grundpreis). Die Quelle
belegt ihn (Destatis/BDEW für Gas, vzbv/DIW für Fernwärme) und warnt: Fernwärme ist oft ein
*Monopolpreis* — der lokale Anbieter ist konkurrenzlos — mit einer Faktor-2-Spanne.

#band(
  [Gas], [0,12 €/kWh], [Amortisation ~10,3 J.],
  [Fernwärme], [0,16 €/kWh (+33 %)], [Amortisation ~6,5 J.],
  [Fernwärme-Spanne], [0,08–0,20 €/kWh], [Amortisation ~5–13 J.],
)

#why[Der Nutzen ist *linear im Preis je kWh*: bei gleicher gesparter Energiemenge bringt teurere Wärme mehr gesparte Euro. Ein um 33 % höherer Tarif verkürzt die Amortisation um rund ein Drittel.]

#closes[die *reale Heizkostenrechnung* des Zielgebäudes einholen (härtet den Wert sofort) und das Monopol-Risiko der Fernwärme dokumentieren.]

== K3 — Monitoring / OPEX
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R2])

Die größte Kosten-Stellschraube, die *wir selbst steuern können*. *OPEX* (laufende Betriebskosten,
englisch operational expenditure) umfasst hier vor allem die Überwachung. Die Quelle rechnet sie
bottom-up (von Einzelposten aufwärts) und stellt zwei Betriebsmodelle gegenüber: feste
Routinestunden vs. ereignisgesteuertes Alerting (die Software meldet sich nur, wenn wirklich etwas
auffällt). Über ein *Portfolio* — mehrere betreute Gebäude — teilen sich die Fixkosten zusätzlich.

#band(
  [Routine (12 h/a, 1 Gebäude)], [960 €/a], [Amortisation ~10,3 J.],
  [ereignisgesteuert], [~280 €/a], [Amortisation ~7,1 J.],
  [Portfolio (10 Gebäude)], [~96–200 €/Gebäude], [Amortisation < 7 J.],
)

#why[OPEX steht — wie der Nutzen — *jährlich* in der Rechnung; jeder gesparte Betriebs-Euro wirkt über die gesamte Laufzeit. Routine-Stunden sind reine Fixkosten, die nur selten echtem Bedarf entsprechen.]

#closes[das Betriebsmodell *ereignisgesteuert* festlegen und die Fixkosten über ein Portfolio verteilen; die Phantom-Hosting-Zeile (50 €) zugleich streichen.]

== K4 — Stundensatz (Kosten- vs. Verkaufssatz)
#strip("hoch", [Kosten-Hebel · Quelle: `report-b` R3])

Ein *struktureller Multiplikator* über alle Arbeitsstunden. Die Quelle trennt sauber den
*Verkaufssatz* (80 €/h, der Preis, den ein Kunde zahlt) vom *Grenzkostensatz* (45–65 €/h, was eine
zusätzliche Arbeitsstunde die WHZ tatsächlich kostet). Für das eigene *Make-vs-Buy*-Urteil (Eigenbau
des Netzes gegen Kauf einer kommerziellen Fertiglösung) zählt der Kostensatz.

#band(
  [Verkaufssatz], [80 €/h], [Referenz (zu teuer fürs Eigen-Urteil)],
  [WHZ-Kostensatz], [45–65 €/h], [Amortisation ~7–8 J. (−2…3 J.)],
)

#why[Der Satz multipliziert *jede* geplante Stunde (Begehung, Installation, Betrieb). Mit dem überhöhten Verkaufssatz wirkt der Make-Pfad künstlich teuer und das Urteil kippt fälschlich Richtung „unwirtschaftlich".]

#closes[den WHZ-Grenzkostensatz festlegen und das Urteil damit rechnen; den 80-€/h-Verkaufssatz nur im Angebots-Szenario verwenden.]

== K5 — Aktor-Bulk-Preis
#strip("mittel", [Kosten-Hebel · Quelle: `report-b` R7 · `model.md` §10])

Die *weichste CAPEX-Zahl*. *CAPEX* (die einmaligen Investitionskosten, englisch capital expenditure)
besteht zu ca. 64 % aus den Aktoren — der Stückpreis schlägt also stark durch. Die Quelle nutzt
einen Listenpreis (m2mgermany, ~70 €) *ohne* Mengenrabatt; ein echtes *Bulk*-Angebot (Großmenge,
hier 120 Stück) liegt nicht vor.

#band(
  [Bulk −15 %], [~60 €/Aktor], [Kern-Amortisation ~4,1 J.],
  [Punktwert], [70 €/Aktor], [Kern-Amortisation ~4,6 J.],
  [Listenpreis (Vicki)], [~82 €/Aktor], [Kern-Amortisation ~5,5 J.],
)

#why[Der Stückpreis steht im *Zähler* (CAPEX): ±15 % verschieben die Kern-Amortisation um etwa ein halbes bis ein Jahr — spürbar, aber nicht dominant wie Quote oder Tarif. („dnt" und „Vicki" von MClimate sind konkrete Thermostat-Produkte.)]

#closes[ein echtes *120-Stück-Angebot* (dnt *und* Vicki/MClimate) einholen und die Artikelnummer fixieren, bevor fest kalkuliert wird.]

== K6 — Hydraulischer Abgleich (Co-Maßnahme)
#strip("mittel", [Kosten-Hebel · Quelle: `report-b` §6])

Eine *Co-Maßnahme* — eine begleitende, separate Maßnahme, die kein Teil des LoRaWAN-Systems ist. Der
*hydraulische Abgleich* stellt die Heizungsanlage so ein, dass das warme Wasser gleichmäßig auf alle
Heizkörper verteilt wird. Die Quelle (co2online/Finanztip) zeigt: er verdoppelt grob die
Einsparquote, hat aber eigene Kosten und lohnt nur, wenn die Anlage vorher *schief* (ungleich
verteilt) war.

#band(
  [ohne Abgleich], [Ersparnis ~10 %], [Amortisation (Fernwärme) ~6,5 J.],
  [mit Abgleich], [Ersparnis ~20 % (+9.000 €)], [Amortisation (Fernwärme) ~4,0 J.],
)

#why[Der Abgleich hebt den *Nenner* (Jahresnutzen) stark; trotz der Zusatzkosten sinkt die Amortisation — aber nur bei vorher unausgeglichener Anlage, sonst verpufft der Effekt.]

#closes[als eigene Co-Maßnahme mit eigener Wirtschaftlichkeit rechnen; vorher die hydraulische Schieflage prüfen.]

== K7 — Batterie-OPEX
#strip("mittel", [Kosten-Hebel · Quelle: `report-b` R8 · `risiken` H2])

Im Modell als glatter Jahresdurchschnitt geführt, real eine *gebündelte Welle* (alle Batterien etwa
gleichzeitig fällig). Die Quelle weist zudem auf den Batterietyp hin: Alkaline-Zellen verlieren bei
Kälte massiv Kapazität, Lithium-Primärzellen kaum.

#band(
  [geglättet], [228 €/a], [Amortisation ~10 J. (verschleiert die Welle)],
  [reale Welle], [~1.600 € im Wechseljahr], [Liquiditäts-Spitze],
  [Lithium statt Alkaline], [+Stückkosten], [vermeidet ~50 % Kälteverlust],
)

#why[Ein Jahresdurchschnitt verdeckt die geballte Wechselwelle; Alkaline verliert bei 0 °C bis 50 % Kapazität → die Sendeleistung bricht im Winter ein, was ungeplante Vor-Ort-Einsätze auslöst.]

#closes[die Batterie als geplante 120-Ventil-*Welle* modellieren (in einen Wartungsbesuch gebündelt) und Lithium-Primärzellen einplanen.]

== K8 — Overhead-Doppelzählung (versunkene Kosten)
#strip("mittel", [Kosten-Hebel · Quelle: `report-a`-Review])

Die Prozesskette zählt teils bereits *bezahlte* Posten erneut. *Versunkene Kosten* (englisch sunk
costs) sind Ausgaben, die schon getätigt sind und in keine neue Kalkulation gehören. Die Quelle
(Report-A-Review zu den Schritten 1/2/5/6) hält fest: die Provisioning-App *F-0005* (die bereits
gebaute Anwendung des Projekts zum Einbuchen der Geräte), der selbst gehostete Netzwerkserver und das
vorhandene Gateway sind versunken.

#band(
  [gebucht (redundant)], [~3.640 € Overhead], [drückt Amortisation über 10 J.],
  [bereinigt], [~1.500–2.400 € Overhead], [~1.500 € Spielraum],
)

#why[Doppelt gezählte Einmal-/versunkene Kosten erhöhen scheinbar den CAPEX und schieben die Amortisation künstlich nach hinten — ohne dass real ein Euro mehr ausgegeben würde.]

#closes[Schritte zusammenführen, F-0005-Stapelimport statt Hand-Provisionierung, skriptgesteuerte Inbetriebnahme; Erstinstallation (einmalig) von der Wiederholung trennen.]

== K9 — Kaufmännisches fehlt
#strip("mittel", [Kosten-Hebel · Quelle: `model.md` §11 · `report-b` Verfeinerungen])

Mehrere kaufmännische Posten sind im Modell noch nicht abgebildet. Die Quelle merkt an, dass *alle*
Preisquellen netto sind (ohne Umsatzsteuer) und Förderung wie Diskontierung fehlen.

#band(
  [USt (Umsatzsteuer)], [Flag fehlt], [brutto vs. netto unklar],
  [Förderung BEG/BAFA], [fehlt], [kann CAPEX deutlich senken],
  [diskontierte Amortisation (3 %)], [fehlt], [Urteil etwas länger],
)

#why[Förderung senkt den effektiven CAPEX (Zähler), Diskontierung — die Abwertung künftiger Euro auf heutigen Wert — erhöht die effektive Amortisationszeit leicht; beide verschieben die Wirtschaftlichkeitsgrenze. *BEG/BAFA* sind staatliche Zuschüsse: die Bundesförderung für effiziente Gebäude bzw. Programme des Bundesamts für Wirtschaft und Ausfuhrkontrolle.]

#closes[im Modell ergänzen (Umsatzsteuer, Marge/Risiko, Gewährleistung) und Förder- bzw. Netto-Szenarien rechnen.]

= Register B — Technik & Test-Grenzen (was der Feldtest nicht abdeckt)

== T1 — Downlink-Erreichbarkeit
#strip("hoch", [Technik · Quelle: `risiken` A1])

Der Feldtest misst nur *Uplinks* — am Gateway also die Empfangsstärke *RSSI*, den
Signal-Rausch-Abstand *SNR* und die Paket-Zustellrate *PDR* (Packet Delivery Ratio, Anteil
angekommener Pakete). Eine Heizungssteuerung lebt aber von *Downlinks* (Sollwerte, Stellbefehle). Die
Quelle (Dossier A1) erklärt die *Link-Asymmetrie*: ein Downlink wird in einem der zwei kurzen
Empfangsfenster geliefert, die ein Gerät nach jedem Uplink öffnet — *RX1* (gleiche Frequenz wie der
Uplink) oder *RX2* (fest 869,525 MHz, langsamster Modus). Beide werden im Test nicht aktiv geprüft.

#band(
  [Uplink], [gemessen (RSSI/PDR)], [belegt],
  [Downlink], [NICHT gemessen], [offen — Sollwert kommt evtl. nicht an],
)

#why[Uplink- und Downlink-Pfad sind nicht symmetrisch; ein erreichbarer Uplink garantiert keinen ankommenden Sollwert. Bleibt der Downlink aus, kann das Netz die Datenrate nicht mehr nachregeln und die Sendezeit steigt.]

#closes[einen *Downlink-Loopback* in den Feldtest integrieren — einen Gegentest, bei dem das Gateway einen bestätigten Downlink sendet und das Gerät ihn per *ACK* (Acknowledgement, Empfangsbestätigung) im nächsten Uplink quittiert → so entsteht eine Downlink-PDR-Karte je Messpunkt.]

== T2 — Downlink-Duty-Cycle (Kapazität)
#strip("hoch", [Technik · Quelle: `risiken` A2])

Das Gateway *als Sender* unterliegt selbst dem *Duty-Cycle* — dem gesetzlich erlaubten Anteil der
Zeit, den ein Funkgerät im Band aktiv senden darf (im EU868-Band z. B. 1 % = 36 Sekunden pro
Stunde). Das ist eine harte Obergrenze für Downlinks bei vielen Aktoren. Die Quelle nennt die
geprüften Budgets je Frequenz-*Subband* (Frequenzgruppe) und den Befund, dass im aktuellen
Kerlink-Pfad *gar keine* automatische Duty-Cycle-Überwachung läuft.

#band(
  [RX1 (je Subband)], [1 % = 36 s/h], [~25–34 Downlinks/h bei SF12],
  [RX2 (869,525 MHz)], [10 % = 360 s/h], [~225–360/h, geteilt über alle Geräte],
)

#why[Maßgeblich ist die *Sendedauer* eines Pakets (Airtime bzw. Time-on-Air): im langsamsten Modus *SF12* (Spreizfaktor 12 — der Spreizfaktor ist das Maß für Funk-Robustheit: höher = mehr Reichweite, aber längere Sendezeit; ausführlich in T3) dauert ein Frame fast eine Sekunde. Mit Nutzdaten steigt sie weiter und senkt die Zahl möglicher Downlinks/h; bei 35–120 Aktoren mit bestätigten Sollwerten wird das Budget knapp — Überschreitungen werden still verworfen.]

#closes[eine Last-Simulation für Downlinks fahren und eine explizite Downlink-Grenze ins Sizing-Modell (das Auslegungsmodell für die Gateway-Anzahl) aufnehmen.]

== T3 — Kapazität & SF12-Well (35–120 Aktoren)
#strip("hoch", [Technik · Quelle: `risiken` A3/A4])

Drei Geräte erzeugen keine Last; Kollisionen zeigen sich erst bei vielen. Hier wirkt der
*Spreizfaktor* (englisch Spreading Factor, SF): er steuert, wie stark ein Funksignal „gespreizt"
wird — ein höherer SF (bis SF12) bringt mehr Reichweite, kostet aber deutlich mehr Sendezeit. Der
*SF12-Well* ist ein Teufelskreis im bestätigten Betrieb: bleiben Bestätigungen aus, hebt das Netz den
SF immer weiter an, bis fast alle Pakete kollidieren.

#band(
  [3 Geräte (Test)], [keine Last], [keine Kollisionen sichtbar],
  [35–120, bestätigt], [hohe Last], [PDR-Kollaps < 10 % möglich],
)

#why[Fehlgeschlagene Bestätigungen treiben den Spreizfaktor hoch → längere Sendezeit → mehr Kollisionen → noch mehr Fehlversuche: eine Rückkopplung bis zum Zusammenbruch, die mit drei Geräten strukturell nicht auftritt.]

#closes[einen Lasttest mit dem `chirpstack-simulator` (dem mitgelieferten Last-Simulationswerkzeug) mit 35/120 Geräten fahren; im Produktivbetrieb die automatische Datenraten-Anpassung *ADR* (Adaptive Data Rate — das Netz stellt den Spreizfaktor je Gerät selbst ein) aktivieren und eine untere SF-Grenze setzen.]

== T4 — Gateway-Position & Diversity
#strip("hoch", [Technik · Quelle: `risiken` B1/B2])

Der Test misst *eine* Gateway-Position (kurz GW); ob sie optimal ist und was ein zweites Gateway
bringt, bleibt offen. *Diversity* meint den Gewinn dadurch, dass zwei räumlich getrennte Empfänger
dasselbe Paket hören — fällt einer aus, fängt der andere. Die Quelle zitiert Messungen, wonach bei
53 % der Orte *nicht* der nächstgelegene GW der beste Empfänger war.

#band(
  [eine GW-Position], [gemessen], [Sizing-Fehler bis Faktor 2],
  [Diversity (2 GW)], [mit 1 GW unmessbar], [+60 % Kapazität (Literatur)],
)

#why[Mit einem Gateway fehlt die Vergleichsbasis; die „1 vs. 2 GW"-Entscheidung bleibt eine Faustformel statt einer Messung — und kostet bei Fehlentscheidung Funklöcher oder unnötige Investition.]

#closes[einen Alternativ-Standort vergleichen und ein zweites Gateway für einen Termin leihen — als *A/B-Vergleich*: dieselben Punkte einmal mit Variante A (ein Gateway) und einmal mit Variante B (zwei Gateways) direkt gegeneinander messen.]

== T5 — Archetyp-Übertragung
#strip("hoch", [Technik · Quelle: `risiken` D1 · b-typ §4])

Der Test kalibriert nur den *Neubau* (im Modell „Archetyp A" — eine repräsentative Gebäudeklasse);
Plattenbau (D) und Altbau (C) sind nicht abgesichert. Die Funkdämpfung wird in *dB* gemessen
(Dezibel, ein logarithmisches Maß: rund 10 dB bedeuten Faktor 10 in der Leistung, 3 dB etwa
Verdopplung/Halbierung). Die Quelle markiert die 868-MHz-Dämpfungswerte ausdrücklich als
*extrapoliert* (aus anderen Frequenzen hochgerechnet), nicht gemessen.

#band(
  [Neubau A], [kalibriert], [belastbar],
  [Plattenbau D / Altbau C], [extrapoliert (RMSE 7–10 dB)], [GW-Dichte unsicher (±Faktor 2)],
)

#why[Pfadverlust-Modelle streuen auch nach Kalibrierung um 7–10 dB (RMSE = Root Mean Square Error, die typische Abweichung zwischen Vorhersage und Messung). Eine A-Kalibrierung überträgt sich nicht 1:1 auf RC-Beton (Stahlbeton, englisch reinforced concrete) — die Gateway-Zahl je Gebäude kann sich verdoppeln.]

#closes[je Archetyp mindestens eine Mess-Referenz beschaffen und im Sizing als Bandbreite mit Archetyp-Konfidenz ausweisen.]

== T6 — Bauzustand (WDVS / Low-E)
#strip("hoch", [Technik · Quelle: `risiken` E1/E2])

Wird im Rohbau gemessen, fehlen dämpfende Schichten → das Ergebnis ist *zu optimistisch*. Kritisch
sind das *WDVS* (Wärmedämm-Verbundsystem — die gedämmte Außenfassade) mit metallisierter
Dampfbremsfolie und das *Low-E-Glas* (metallbedampftes Energiespar-Fensterglas, das Funk stark
abschirmt). Die Quelle weist darauf hin, dass die Folie von innen unsichtbar ist.

#band(
  [Rohbau (Messung)], [geringere Dämpfung], [zu optimistisch],
  [Fertigbau], [+5–17 dB (Folie)], [mehr Gateways nötig],
)

#why[Metallisierte Folien und Low-E-Glas addieren eine Dämpfung, die im Rohbau noch fehlt; ohne Korrektur unterschätzt die Kalibrierung die Realität des fertigen Gebäudes.]

#closes[den Bauzustand vollständig protokollieren (Foto, Materialcode) und nach Fertigstellung eine Wiederholungsmessung ansetzen.]

== T7 — Fremdnetz-Wachstum (Koexistenz über die Zeit)
#strip("hoch", [Technik · Quelle: `risiken` G1])

LoRaWAN funkt im *lizenzfreien* Band, das alle teilen — die *Koexistenz* mit fremden Netzen ist
also Teil des Betriebs. Der bisherige Scan ist eine Momentaufnahme; die fremde Last *wächst*. Als
Maß dient die *CAF* (Channel Airtime Fraction — der Anteil der Sendezeit auf einem Kanal, der bereits
von fremden Netzen belegt ist). Die Quelle nennt den EU-Smart-Meter-Rollout (195 → 285 Mio. von 2024
bis 2029) als Treiber. Aus der CAF folgt die *Kollisionswahrscheinlichkeit* `P_Koll` — wie oft ein
eigenes Paket mit einem fremden zusammenstößt.

#band(
  [heute], [CAF < 2 %], [Kollisionsrisiko unkritisch],
  [in ~3 Jahren], [CAF 5–10 %], [`P_Koll` 10–18 % (Bereich „beobachten")],
)

#why[Steigt die fremde Sendezeit, steigt die Kollisionswahrscheinlichkeit `P_Koll` *überproportional*: Geräte senden ohne Koordination (das ALOHA-Prinzip), sodass schon mäßige Mehrlast viele Zusammenstöße erzeugt. Ein heute grüner Standort kann in wenigen Jahren ein zweites Gateway oder eine SF-Optimierung als ungeplante Nachkosten erzwingen.]

#closes[Koexistenz als *Dauer-Monitoring* führen (statt Einmal-Scan) und eine Alarmschwelle in der Dienstgüte-Vereinbarung (*SLA*, Service-Level-Agreement) setzen — z. B. CAF > 5 % auf einem Pflichtkanal.]

== T8 — Geräte-Repräsentativität
#strip("hoch", [Technik · Quelle: `risiken` H1])

Der Test-Aktor (TRV) ist evtl. nicht das später beschaffte Serienprodukt. Die Quelle warnt, dass
Antenne, Firmware und Datenraten-Verhalten je Modell abweichen — und damit das *Link-Budget* (die
gesamte Pegel-Bilanz von Sender bis Empfänger, in dB).

#band(
  [Test-TRV], [Referenz-Link-Budget], [—],
  [Serien-Aktor], [±3–6 dB], [„1 vs. 2 GW" kann kippen],
)

#why[Schon 3–6 dB anderes Link-Budget verschieben die Reichweite genug, um die Gateway-Anzahl-Entscheidung zu drehen — das Sizing stützt sich sonst auf das falsche Gerät.]

#closes[einen A/B-Test Ziel-TRV gegen Test-TRV am selben Punkt fahren und das Delta (die Differenz) als Korrekturfaktor dokumentieren.]

== T9 — Schnappschuss, Saison & Statistik
#strip("mittel", [Technik · Quelle: `risiken` C1/C2/F1/F2])

Ein Termin, wenige Punkte — weder zeitlich noch räumlich repräsentativ. Die Quelle nennt bis
~10,6 dB Schwankung durch Belegung und *HVAC* (Heizungs-, Lüftungs- und Klimatechnik) und eine
deutliche räumliche Unterabtastung (zu wenige Messpunkte je Fläche).

#band(
  [Zeit], [1 Termin], [Saison/Belegung ±~10 dB],
  [Raum], [3–4 Punkte/Etage], [üblich 20–30; PDR-Vertrauensband ±14 Pp],
)

#why[Wenige Punkte verfehlen den echten ungünstigsten Ort; ein einzelner Termin trifft nicht die Winter-Vollbelegung — beides macht die PDR-Erwartung zu optimistisch. (Pp = Prozentpunkte.)]

#closes[einen *Walk-Survey* (eine Mess-Begehung mit einem schnell sendenden Knoten über viele Punkte, ≥ 20 je Hauptetage) ergänzen, eine Dauermessung (*Soak*) an festen Punkten fahren und einen *Fade-Margin* ansetzen — eine Funk-Reserve, also einen Pegel-Puffer über dem gerade noch funktionierenden Minimum (Literatur: 25,7 dB für 99 % PDR).]

= Register C — Prozess & offene Entscheidungen

== E1 — Zielgebäude X / Y nicht benannt
#strip("hoch", [Entscheidung · Quelle: `model.md` §8 · scope §6])

Das Modell läuft mit generischen *Defaults* (Standard-Annahmen), weil kein reales Gebäude benannt
ist. Die Quelle führt „Target Buildings X / Y" ausdrücklich als *TBD* (to be defined — noch
festzulegen) — eine offene Entscheidung des *PO* (Product Owner, der auftraggebenden und
entscheidenden Rolle).

#band(
  [keine Gebäude benannt], [nur Defaults], [kein konkretes Urteil möglich],
  [X/Y benannt], [reale Parameter], [Modell instanziierbar],
)

#why[Ohne konkrete Fläche, Etagenzahl, Heizkörperzahl und Tarif bleibt jedes „wirtschaftlich ja/nein" hypothetisch — alle anderen Bänder hängen an diesen Eingaben.]

#closes[der PO benennt 1–2 reale WHZ-Gebäude zur Instanziierung des Modells.]

== E2 — Archetyp des Zielgebäudes
#strip("hoch", [Entscheidung · Quelle: b-typ §4 · `risiken` D1])

Neubau (A) oder Plattenbau (D)? Das bestimmt die *GW-Dichte* (wie viele Gateways je Etage/Fläche
nötig sind) maßgeblich. Die Quelle (building-typology) gibt die Faustregeln je Bauart.

#band(
  [Neubau A], [~1 GW / 2–3 Etagen], [moderate Dichte],
  [Plattenbau D], [15–25 dB/Decke], [potenziell doppelte GW-Zahl],
)

#why[RC-Beton dämpft Geschossdecken weit stärker als ein Neubau; die Wahl des Archetyps kann die Gateway-Zahl — und damit einen relevanten CAPEX-Block — verdoppeln.]

#closes[bei der Gebäude-Benennung den Archetyp festlegen und ggf. eine Funk-Referenz für D beschaffen.]

== P1 — Installateur-Varianz
#strip("mittel", [Prozess · Quelle: `risiken` I1])

Der Test nutzt einen normierten 3D-gedruckten Halter; im *Rollout* (dem flächigen Ausbau) variieren
Winkel und Metallabstand je Installateur. Die Quelle nennt 3–10 dB Kopplungsverlust, wenn die Antenne
näher als 10 mm an Metall sitzt.

#band(
  [Test (normiert)], [definierte Montage], [niedrige Fehlerquote],
  [Rollout (variabel)], [streuende Montage], [+5–15 % Erstmontage-Fehler],
)

#why[Variable Montage streut das Link-Budget; ein Teil der Aktoren startet unter der Empfangsschwelle, was die im Test gemessene Erfolgsquote im Feld nach unten zieht.]

#closes[eine Installations-Checkliste mit Foto-Pflicht (Prozess-Schritt P4-03) und eine Stichproben-Inbetriebnahme nach der ersten Welle (P4-04) einführen.]

== P2 — Provisionierungsfehler (Großmenge)
#strip("mittel", [Prozess · Quelle: `risiken` I2 · P3-03])

Die *Provisionierung* — das Anlegen und Einbuchen der Geräte ins Netz samt ihrer Schlüssel — birgt
bei 120 Geräten per Tabellenimport eine Fehlerquote. Die Quelle hält fest, dass der Netzwerkserver
einen fehlerhaften Sicherheits-Code (*MIC*, Message Integrity Code — die kryptografische Prüfsumme
jedes Pakets) nur als „Gerät nicht gefunden" meldet — Fehler fallen also spät auf.

#band(
  [3 Geräte (Test)], [trivial prüfbar], [—],
  [120 (Rollout)], [1–5 % Fehlerquote], [5–10 % offline möglich],
)

#why[Bei Massenimport schlagen Tippfehler und Dubletten in den Geräteschlüsseln *still* durch und zeigen sich erst bei der Abnahme — dann ist Nacharbeit in belegten Räumen nötig.]

#closes[einen Abgleich der gelieferten Ware gegen die Schlüsselliste (P2-05) und einen Format- und Dublettencheck beim Import (P3-03) erzwingen.]

== P3 — Zugang zu (Mieter-)Räumen
#strip("mittel", [Prozess · Quelle: `risiken` I3 · P7-04])

Im leeren Neubau trivial, im Betrieb ein Engpass. Die Quelle verweist auf den Fragenkatalog-Punkt
E10 (Zugangsbedingungen).

#band(
  [Test (leer)], [kein Zugangsaufwand], [—],
  [Betrieb (bewohnt)], [Terminkoordination], [Batteriewellen 2–3× länger],
)

#why[Zugang zu Nutzerräumen verlängert Wartungswellen erheblich und treibt die OPEX, die das Modell aktuell zu niedrig ansetzt.]

#closes[Fragenkatalog E10 verbindlich erheben und die reale Zugangsquote aus dem Piloten in die OPEX zurückführen (P7-08).]

== P4 — Survey-Tag & Zweit-Gateway-Kontingenz
#strip("mittel", [Prozess · Quelle: `report-a`-Review · `risiken` B1])

Ein stiller Kostenposten, der real auslösen kann. Eine *Kontingenz* ist eine Reserveposition im
Angebot — Geld, das nur fällig wird, wenn ein Risiko eintritt. Die Quelle (Report-A-Review) sieht
einen evtl. leeren Installateur-Tag bei der Funk-Voruntersuchung (*Survey*) und ein Zweit-Gateway,
das bisher als 0-€-Annahme geführt wird.

#band(
  [Zweit-Gateway], [0 € (stille Annahme)], [300–1.200 €, vom Survey ausgelöst],
  [Installateur-Tag], [1.080 € gebucht], [evtl. −520 € (streichbar)],
)

#why[Eine verschwiegene Kontingenz täuscht eine zu günstige Amortisation vor; umgekehrt steckt im pauschal gebuchten Survey-Tag Einsparpotenzial, wenn die Funkprüfung schlanker geht.]

#closes[ein Survey-Gate (Prozess-Schritt P1-07) mit Downlink-Loopback einführen und die Zweit-Gateway-Kontingenz explizit als auslösbare Angebotsposition ausweisen.]

== P5 — Markt: LoRaWAN-Aktor-Verfügbarkeit
#strip("mittel", [Prozess · Quelle: preliminary-research RQ4 · ADR-0020])

Hält der LoRaWAN-native Aktor-Markt die angenommenen Großmengen-Preise? „LoRaWAN-native" heißt: das
Gerät spricht direkt LoRaWAN, ohne Zusatz-Brücke. Die Quelle (Recherchefrage RQ4) lässt das offen;
die dokumentierte Architekturentscheidung ADR-0020 (Architecture Decision Record — ein festgehaltener
Architektur-Beschluss, nicht die Datenraten-Anpassung ADR aus T3) legt fest, dass nur solche Aktoren
in den Make-Pfad zählen.

#band(
  [Massenmarkt], [~70 €/Aktor hält], [CAPEX-Annahme stabil],
  [Nische (2–3 Hersteller)], [Preis-/Liefer-Risiko], [CAPEX kann steigen],
)

#why[Ein dünner Markt ohne Wettbewerb kann Mengenrabatte ausbleiben lassen und die CAPEX-Annahme nach oben ziehen — direkt gekoppelt an K5.]

#closes[die Beschaffungs-Recherche RQ4 vertiefen und mindestens zwei Hersteller konkret anfragen.]

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
  Gebäude-/Funk-Lücken → `building-typology.md` §4; offene PO-Entscheidungen → `scope-and-requirements`
  §6/§8 und `model.md` §8. Wird ein Punkt geschlossen (gemessen/entschieden), hier abhaken und die
  Quelle aktualisieren.
]
