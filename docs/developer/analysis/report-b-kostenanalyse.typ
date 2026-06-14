#import "report-template.typ": *
#show: report.with(
  title: "Report B — Kosten- & Sensitivitätsanalyse",
  subtitle: "Welche Stellschrauben haben wir — und wie groß ist ihr Einfluss? (verständliche Fassung)",
  meta: "Projekt whz-lora · WHZ · 2026-06-13 · Vorkalkulation mit belegten Annahmen, keine Garantie · Sensitivität am Referenzgebäude (Mittel-/Altbau, 120 Heizkörper), vollkostenbelastet, Basis 10,3 Jahre",
)

Die wiederkehrenden Begriffe dieses Reports in Alltagssprache:

#table(
  columns: (auto, 1fr), stroke: 0.5pt + rulec, inset: 6pt,
  table.header(th("Begriff"), th("In einfachen Worten")),
  [*Payback / Amortisation*], [Zeit, bis die jährliche Einsparung die Investition wieder hereinholt. 10.000 € bei 2.000 €/Jahr → 5 Jahre.],
  [*Einsparquote*], [Anteil der Heizenergie, den die Einzelraumregelung tatsächlich einspart.],
  [*Energieträger*], [Womit geheizt wird (Gas, Fernwärme). Bestimmt den Preis je Kilowattstunde — und damit, wie viel Euro eine gesparte kWh wert ist.],
  [*RSSI / SNR*], [Zwei Maße der Funkqualität: RSSI = Empfangsstärke (wie laut), SNR = Abstand zum Rauschen (wie klar). Wie beim Telefonat: RSSI = wie laut der andere spricht, SNR = wie ruhig der Raum ist.],
  [*Kostensatz vs. Verkaufssatz*], [Verkaufssatz (80 €/h) = Preis für Kunden; Kostensatz (45–65 €/h) = was eine Stunde die WHZ wirklich kostet. Fürs eigene Urteil zählt der Kostensatz.],
  [*Portfolio*], [Mehrere betreute Gebäude. Fixkosten (v. a. Überwachung) teilen sich auf alle — je mehr Gebäude, desto günstiger pro Gebäude.],
  [*Rebound*], [Bewohner setzen einen Teil der Einsparung in mehr Komfort um (etwas wärmer heizen). Ein Rebound-Abschlag zieht das vorsorglich ab.],
  [*Kontingenz*], [Reserveposten im Angebot: Geld, das nur fällig wird, wenn ein Risiko eintritt (hier: ein zweites Gateway).],
)

= Überblick

Das Modell rechnet *rückwärts*: Aus dem jährlichen Nutzen (eingesparte Heizkosten) ergibt
sich, wie teuer das System höchstens sein darf, damit es sich innerhalb des Zeithorizonts
amortisiert.

#plain[Statt zu fragen „Was kostet die Anlage?" fragt das Modell „Welche Kosten darf die
Anlage haben, damit sie sich rechnet?" — und vergleicht das mit den tatsächlichen Kosten.]

Der vollkostenbelastete Referenz-Payback liegt bei *~10,3 Jahren* — aber das ist ein
irreführender *Punktwert* (eine einzelne, scheinbar genaue Zahl). Die kritische Prüfung zeigt:
Die Amortisation ist in Wahrheit eine *Bandbreite von ~5,5 Jahren bis weit über 20 Jahre*,
getrieben vor allem von der Einsparquote, dann von Energieträger und Betriebskosten.

= Die Stellschrauben im Bild

#figure(image("assets/tornado.svg", width: 100%), caption: [Sensitivität des Payback je Stellschraube (Basis 10,3 J.). Grün = besser/kürzer, Rot = schlechter.])

#callout(title: "Lesart", color: accent)[
  Je länger der Balken, desto größer der Hebel. *Energieträger* (±13,5 J.) und *Ersparnisquote*
  (±8,2 J.) dominieren alles; *Hardware und Arbeit* bewegen den Payback nur um ~2 Jahre; das
  *Gateway* ist nahezu irrelevant — solange ein zweites nicht nötig wird (Stellschraube Nr. 5).
]
#plain[Ein „Tornado-Diagramm" reiht die Einflussgrößen nach Wucht — die längsten Balken oben.
Hier entscheiden nicht die Geräte, sondern wie viel Energie gespart wird und womit geheizt wird.]

= Ranking & Einfluss

#table(
  columns: (auto, 1.2fr, 1.5fr, 1.5fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("#"), th("Stellschraube"), th("Einfluss auf Payback"), th("Maßnahme / Hebel")),
  [1], [*Einsparquote*\ #text(8pt, fill: muted)[10 %, Altbau-Band 8–12 %]], [#text(fill: bad)[Dominant.] 10→5 % ⇒ ~83 J.\* (unwirtschaftlich); 10→15 % ⇒ ~5,5 J.], [Am Archetyp ankern, Rebound-Abschlag −20–30 %, *am Testbed kalibrieren*; als Band berichten],
  [2], [*Monitoring (OPEX)*\ #text(8pt, fill: muted)[960 €/a, Einzelgebäude]], [Größte *kontrollierbare* Größe. →280 €/a senkt ~10,3 → ~7,1 J.; im Portfolio ~6,5 J.], [Ereignisgesteuertes Alerting statt 12 Routine-Stunden; als Portfolio-Fixkosten verteilen],
  [3], [*Stundensatz*\ #text(8pt, fill: muted)[80 €/h Verkaufssatz]], [Struktureller Multiplikator über alle Stunden. 80→50 €/h ⇒ ~7–8 J.], [Urteil mit WHZ-*Kostensatz* (45–65 €/h) rechnen; 80 €/h nur als Angebots-Szenario],
  [4], [*Energieträger*\ #text(8pt, fill: muted)[Gas 0,12 €/kWh]], [Linearer Nutzen. Fernwärme 0,16 = +33 % ⇒ ~6,5 J.; mit Abgleich ~4,0 J.], [Realen Gebäude-Tarif nutzen — eine Heizkostenrechnung härtet das sofort],
  [5], [*Survey & Zweit-Gateway*\ #text(8pt, fill: muted)[1.080 € / 0 € GW]], [Fetteste Overhead-Zeile (−520 €) + *verstecktes Risiko*: 6 Geschosse über dem belegten Einzel-Gateway-Fall (4)], [Installateur-Tag streichen; Zweit-Gateway als explizite, survey-gesteuerte Kontingenz (+300–1.200 €)],
  [6], [*Hydraul. Abgleich*\ #text(8pt, fill: muted)[optional 9.000 €]], [Verdoppelt Ersparnis (10→~20 %) ⇒ ~5,7 J.; mit Fernwärme ~4,0 J.], [Als eigene Co-Maßnahme mit eigenem Payback; vorher Schieflage prüfen],
  [7], [*Aktor-Mengenpreis*\ #text(8pt, fill: muted)[70 €, 64 % des Kern-CAPEX]], [Weichste CAPEX-Zahl. −15 % ⇒ Kern-Payback 4,6 → ~4,1 J.; Vicki-Listenpreis hebt auf ~5,5 J.], [Echtes 120-Stück-Angebot (dnt *und* Vicki/MClimate); Artikelnummer festlegen],
  [8], [*Batterie-OPEX*\ #text(8pt, fill: muted)[228 €/a glatt]], [Moderat (→110 ⇒ ~9,5 J.), verbirgt aber eine lumpige ~1.600-€-Welle im Wechseljahr], [Als geplante 120-Ventil-Welle modellieren, in Wartungsbesuch bündeln],
)
#text(8pt, fill: muted)[\* ~83 J. = praktisch nie wirtschaftlich: Bei halbem Nutzen zehren die laufenden Kosten (≈ 1.238 €/a) fast den gesamten Restnutzen auf, der Netto-Nutzen geht gegen null. Kein Rechenfehler, sondern die Folge des fast aufgebrauchten Nenners. — Kleinste Schraube (nicht abgebildet): *Hosting 50 €/a* → 0 € (Phantom-Zeile; das Modell nennt den selbst gehosteten Server „~0 € marginal"). *dnt* und *Vicki* (MClimate) sind konkrete Thermostat-Produkte.]

== Warum die obersten Hebel so stark wirken

- *Einsparquote (Rang 1):* Sie bestimmt direkt den Jahresnutzen — und der steht im *Nenner*
  der Payback-Rechnung. Halbiert sich die Quote (10→5 %), halbiert sich der Nutzen, und der
  Payback springt nicht aufs Doppelte, sondern *explodiert auf ~83 Jahre*, weil die laufenden
  Kosten dann fast den ganzen Restnutzen auffressen. Deshalb muss diese Zahl *am eigenen
  Testbed gemessen* werden, nicht aus Herstellerprospekten. Der *Rebound-Abschlag* trägt dem
  Effekt Rechnung, dass Nutzer bei günstigerer Heizung dazu neigen, etwas wärmer zu heizen.
- *Energieträger (Rang 4):* Der Nutzen ist der eingesparte *Preis pro Kilowattstunde*.
  Teurere Wärme (Fernwärme 0,16 € statt Gas 0,12 €) bedeutet bei *gleicher gesparter Energie*
  mehr gesparten Euro. Dieser Hebel ist eine reine *Tarif-Eigenschaft des Gebäudes* (bei
  Fernwärme oft ein Monopolpreis) und durch bessere Technik gar nicht beeinflussbar — anders
  als Einsparquote und Monitoring, die wir selbst in der Hand haben.
- *Monitoring (Rang 2):* Die größte Kosten-Stellschraube, die *wir selbst steuern können*.
  Statt fest eingeplanter Routinestunden lässt man die Software nur dann Alarm schlagen, wenn
  wirklich etwas auffällt (ereignisgesteuert). Über mehrere Gebäude verteilt sinken die
  Fixkosten pro Gebäude zusätzlich.
- *RSSI/SNR (Hintergrund zum Gateway-Risiko):* Wichtig: LoRaWAN funktioniert noch *unterhalb
  des Rauschens* (ein negativer SNR ist normal). Ein zweites Gateway braucht es deshalb nicht
  schon bei „niedrigem SNR", sondern erst, wenn die *Funkreserve aufgebraucht* ist — wenn also
  auch der langsamste, robusteste Sendemodus (Spreizfaktor SF12) die Dämpfung der bewehrten
  Decken nicht mehr überwindet.

= Methodische Korrekturen aus dem Review

#callout(title: "Drei Korrekturen, die das Urteil verschieben", color: warn)[
  *1. Kein Punktwert — eine Bandbreite.* „10,3 Jahre" suggeriert eine Präzision, die es nicht
  gibt. Ehrlich ist *~5,5 J.* (Fernwärme, abgeglichen, amortisierter Overhead) *bis weit über
  20 J.* (Gas, 5 % Ersparnis, Einzelgebäude-OPEX). \
  *2. Kostensatz statt Verkaufssatz.* Das Make-/Buy-Urteil muss mit dem WHZ-Grenzkostensatz
  (45–65 €/h) gerechnet werden, nicht mit dem kommerziellen 80-€/h-Verkaufssatz. \
  *3. Versunkene Kosten nicht doppelt zählen.* F-0005, selbst gehosteter LNS und das vorhandene
  Gateway sind laut Modell „sunk" — in der Prozesskette aber teils erneut berechnet (Schritte 5, 6, 8).
]
#plain[Eine einzelne Jahreszahl täuscht Sicherheit vor. Rechnet man mit den echten
WHZ-Stundenkosten und zählt nichts doppelt, was schon bezahlt ist, fällt der Payback ehrlicher —
und gehört immer als Spanne genannt, nie als eine Zahl.]

= Top-Chancen (nach Einfluss)

+ *Keinen einzelnen Payback mehr berichten.* Die Einsparquote ist die dominante Schraube. Die angesetzten 10 % liegen für einen echten Altbau (Band 8–12 %) in der *Band-Mitte* und passen damit eher zu einem bereits teilsanierten Gebäude. Vor jedem „wirtschaftlich"-Urteil: am Archetyp ankern, Rebound-Abschlag, *am Testbed kalibrieren*.
+ *Den Overhead reparieren* — er schiebt den Payback über die 10-Jahres-Grenze. Ingenieurarbeit zum WHZ-Kostensatz; Erstinstallation (amortisiert) von der Wiederholung (Vorlage + F-0005) trennen.
+ *Die Monitoring-Zeile kürzen:* 960 €/a (1 Gebäude) → ereignisgesteuert ~280 €/a, als Portfolio-Fixkosten (~96–200 €/Gebäude bei 10). Senkt ~10,3 → ~7,1 J.; Phantom-Hosting (50 €) zugleich streichen.
+ *Das 6-Geschoss-Einzel-Gateway zur expliziten Kontingenz machen* — nicht als stille 0-€-Annahme. Ein Zweit-Gateway (~102–330 €) als auslösbare Angebots-Position; Unterabdeckung als Abnahme-Kriterium. Finanziell trivial (unter 2,5 % CAPEX), beseitigt das dominante Terminrisiko.
+ *Versunkene Kosten entdoppeln:* Schritt 1 in 2 mergen (−240 €), Schritt 5 als F-0005-Batch-Import (~100 €, −220 €), Hand-Provisionierung in Schritt 6 durch Skript ersetzen (−520 €). Zusammen mit dem reduzierten Survey ~1.500 € Overhead weg.

= Netto-Effekt: der Payback als Band

#table(
  columns: (1.8fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 1 { right } else { left },
  table.header(th("Szenario"), th("Amortisation")),
  [Gebucht (loaded+ops · Gas · 10 % · Einzelgebäude)], [~10,3 J.],
  [Bereinigt (Kostensatz + Monitoring ereignisgesteuert)], [~7–8 J.],
  [… mit Fernwärme (0,16 €/kWh)], [~6,5 J.],
  [… mit hydraulischem Abgleich (Fernwärme)], [*~4,0 J.*],
  [Pessimistisch (Gas · 5 % Ersparnis · Einzelgebäude)], [#text(fill: bad)[weit über 20 J.]],
)

#callout(title: "Fazit", color: good)[
  Nicht die Gerätehardware entscheidet, sondern *Einsparquote, Energieträger, Betriebskosten
  und Portfolio-Größe*. Vor jedem „wirtschaftlich"-Urteil: (1) Einsparquote am whz-lora-Testbed
  kalibrieren, (2) ein echtes 120-Stück-Bulk-Angebot einholen, (3) den realen Energietarif des
  Gebäudes einsetzen, (4) das Urteil zum WHZ-Kostensatz rechnen — und stets als *Bandbreite*
  berichten, nie als einzelne Zahl.
]
#plain[Ob sich die Anlage lohnt, hängt weniger an den Geräten als an vier Hebeln — wie viel
wirklich gespart wird, womit geheizt wird, wie schlank der Betrieb läuft und über wie viele
Gebäude man die Fixkosten verteilt. Erst diese vier am echten Gebäude messen, dann urteilen.]
