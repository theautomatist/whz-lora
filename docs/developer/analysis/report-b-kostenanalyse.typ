#import "report-template.typ": *
#show: report.with(
  title: "Report B — Kosten- & Sensitivitätsanalyse",
  subtitle: "Welche Stellschrauben haben wir — und wie groß ist ihr Einfluss?",
  meta: "Projekt whz-lora · WHZ · 2026-06-13 · Vorkalkulation mit belegten Annahmen, keine Garantie · Sensitivität am Referenzgebäude (Mittel/Altbau, 120 Heizkörper), vollkostenbelastet, Basis 10,3 Jahre",
)

= Überblick

Das Modell rechnet *rückwärts*: aus dem Jahresnutzen folgt die maximal zulässige
Systemkosten für Amortisation. Der vollkostenbelastete Referenz-Payback liegt bei
*~10,3 Jahren* — aber das ist ein irreführender *Punktwert*. Die kritische Prüfung zeigt:
die Amortisation ist eine *Bandbreite von ~5,5 bis >>20 Jahren*, getrieben primär von der
Einsparquote, sekundär von Energieträger und Betriebskosten. Dieser Report schlüsselt die
Stellschrauben nach ihrem Einfluss auf.

= Die Stellschrauben im Bild

#figure(
  image("assets/tornado.svg", width: 100%),
  caption: [Sensitivität des Payback je Stellschraube (Basis 10,3 J.). Grün = besser/kürzer, Rot = schlechter.],
)

#callout(title: "Lesart", color: accent)[
  Je länger der Balken, desto größer der Hebel. *Energieträger* (±13,5 J.) und *Ersparnisquote*
  (±8,2 J.) dominieren alles; *Hardware und Arbeit* bewegen den Payback nur um ~2 Jahre;
  das *Gateway* ist nahezu irrelevant — solange ein zweites nicht nötig wird (siehe Rang 5).
]

= Ranking & Einfluss

#table(
  columns: (auto, 1.2fr, 1.5fr, 1.5fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("#"), th("Stellschraube"), th("Einfluss auf Payback"), th("Maßnahme / Hebel")),
  [1], [*Einsparquote*\ #text(8pt, fill: muted)[10 %, Spanne 5–12 %]], [#text(fill: bad)[Dominant.] 10→5 % ⇒ ~83 J. (unwirtschaftlich); 10→15 % ⇒ ~5,5 J.], [Auf Band-Mitte ~8–9 % ankern, Rebound-Abschlag −20–30 %, *am Testbed kalibrieren*; als Band berichten],
  [2], [*Monitoring (OPEX)*\ #text(8pt, fill: muted)[960 €/a, Einzelgebäude]], [Größte *kontrollierbare* Größe. →280 €/a senkt ~10,3 → ~7,1 J.; im Portfolio ~6,5 J.], [Event-getriebenes ChirpStack-Alerting statt 12 Routine-Stunden; als Portfolio-Fixkosten verteilen],
  [3], [*Stundensatz Ingenieur*\ #text(8pt, fill: muted)[80 €/h Verkaufssatz]], [Struktureller Multiplikator über alle Stunden. 80→50 €/h ⇒ ~7–8 J.], [Urteil mit WHZ-*Kostensatz* (45–65 €/h) rechnen; 80 €/h nur als Angebots-Szenario],
  [4], [*Energieträger*\ #text(8pt, fill: muted)[Gas 0,12 €/kWh]], [Linearer Nutzen. Fernwärme 0,16 = +33 % ⇒ ~6,5 J.; mit Abgleich ~4,0 J.], [Realen Gebäude-Tarif nutzen — eine Heizkostenrechnung härtet das sofort],
  [5], [*Survey & Zweit-Gateway*\ #text(8pt, fill: muted)[1.080 € / 0 € GW]], [Fetteste Overhead-Zeile (−520 €) + *verstecktes Risiko*: 6 Geschosse über dem belegten Einzel-Gateway-Fall (4)], [Installateur-Tag streichen; Zweit-Gateway als explizite, survey-gesteuerte Kontingenz (+300–1.200 €) führen],
  [6], [*Hydraul. Abgleich*\ #text(8pt, fill: muted)[optional 9.000 €]], [Verdoppelt Ersparnis (10→~20 %) ⇒ ~5,7 J.; mit Fernwärme ~4,0 J.], [Als eigene Co-Maßnahme mit eigenem Payback; vorher prüfen, ob Schieflage existiert],
  [7], [*Aktor-Mengenpreis*\ #text(8pt, fill: muted)[70 €, 64 % des Kern-CAPEX]], [Weichste CAPEX-Zahl. −15 % ⇒ Kern-Payback 4,6 → ~4,1 J.; Vicki-Retail hebt auf ~5,5 J.], [Echtes 120-Stück-Angebot (dnt *und* Vicki/MClimate); SKU festnageln],
  [8], [*Batterie-OPEX*\ #text(8pt, fill: muted)[228 €/a glatt]], [Moderat (→110 ⇒ ~9,5 J.), verbirgt aber eine lumpige ~1.600-€-Welle im Wechseljahr], [Als geplante 120-Ventil-Welle modellieren, in Wartungsbesuch bündeln],
)
#text(8pt, fill: muted)[Kleinste Schraube (nicht abgebildet): *Hosting 50 €/a* → 0 € (Phantom-Zeile; widerspricht model.md §5 „selbst gehostet, ~0 marginal").]

= Methodische Korrekturen aus dem Review

#callout(title: "Drei Korrekturen, die das Urteil verschieben", color: warn)[
  *1. Kein Punktwert — eine Bandbreite.* „10,3 Jahre" suggeriert Präzision, die es nicht gibt.
  Ehrlich ist *~5,5 J.* (Fernwärme, abgeglichen, amortisierter Overhead) *bis >>20 J.* (Gas,
  5 % Ersparnis, Einzelgebäude-OPEX). \
  *2. Kostensatz statt Verkaufssatz.* Das Make/Buy-Urteil muss mit dem WHZ-Grenzkostensatz
  (45–65 €/h) gerechnet werden, nicht mit dem kommerziellen 80-€/h-Verkaufssatz — sonst
  verteuert man die eigene Wirtschaftlichkeit mit einem Preis für zahlende Kunden. \
  *3. Versunkene Kosten nicht doppelt zählen.* F-0005-Provisionierung, selbst gehosteter LNS
  und das vorhandene Gateway sind laut Modell „sunk" — werden in der Prozesskette aber teils
  erneut berechnet (Schritte 5, 6, 8).
]

= Top-Chancen (nach Einfluss)

+ *Keinen einzelnen Payback mehr berichten.* Die Einsparquote ist die dominante Schraube und 10 % ist das obere Drittel der modelleigenen 5–12 %-Altbau-Bandbreite — als „konservativ" deklariert. Auf ~8–9 % ankern, Rebound-Abschlag, *am Testbed kalibrieren* vor jedem „wirtschaftlich"-Urteil.
+ *Den Overhead reparieren* — er ist die Schwankungsgröße, die den Payback über die 10-Jahres-Grenze schiebt. Ingenieurarbeit zum WHZ-Kostensatz; Erstinstallation (amortisiert) von Wiederholung (Template + F-0005) trennen.
+ *Die Monitoring-Zeile kürzen:* 960 €/a (1 Gebäude) → event-getrieben ~280 €/a, als Portfolio-Fixkosten (~96–200 €/Gebäude bei 10). Senkt ~10,3 → ~7,1 J.; Phantom-Hosting (50 €) zugleich streichen.
+ *Das 6-Geschoss-Einzel-Gateway zur expliziten Kontingenz machen* — nicht als stille 0-€-Annahme. Ein Zweit-Gateway (~102–330 €) als auslösbare Angebots-Position; Unterabdeckung als Abnahme-Gate. Finanziell trivial (unter 2,5 % CAPEX), beseitigt das dominante Terminrisiko.
+ *Versunkene Kosten entdoppeln:* Schritt 1 in 2 mergen (−240 €), Schritt 5 als F-0005-Batch-Import (~100 €, −220 €), Hand-Provisionierung in Schritt 6 durch Skript ersetzen (−520 €). Zusammen mit dem reduzierten Survey ~1.500 € Overhead weg.

= Netto-Effekt: der Payback als Band

#table(
  columns: (1.8fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 1 { right } else { left },
  table.header(th("Szenario"), th("Amortisation")),
  [Gebucht (loaded+ops · Gas · 10 % · Einzelgebäude)], [~10,3 J.],
  [Bereinigt (Kostensatz + Monitoring event-getrieben)], [~7–8 J.],
  [… mit Fernwärme (0,16 €/kWh)], [~6,5 J.],
  [… mit hydraulischem Abgleich (Fernwärme)], [*~4,0 J.*],
  [Pessimistisch (Gas · 5 % Ersparnis · Einzelgebäude)], [#text(fill: bad)[>>20 J.]],
)

#callout(title: "Fazit", color: good)[
  Nicht die Gerätehardware entscheidet, sondern *Einsparquote, Energieträger, Betriebskosten
  und Portfolio-Größe*. Vor jedem „wirtschaftlich"-Urteil: (1) Einsparquote am whz-lora-Testbed
  kalibrieren, (2) ein echtes 120-Stück-Bulk-Angebot einholen, (3) den realen Energietarif des
  Gebäudes einsetzen, (4) das Urteil zum WHZ-Kostensatz rechnen — und stets als *Bandbreite*
  berichten, nie als einzelne Zahl.
]
