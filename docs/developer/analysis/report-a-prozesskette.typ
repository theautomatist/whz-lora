#import "report-template.typ": *
#show: report.with(
  title: "Report A — Prozesskette & Lieferprozess",
  subtitle: "LoRaWAN-Heizungssteuerung als virtuelles Unternehmen (Make-Pfad)",
  meta: "Projekt whz-lora · WHZ · 2026-06-13 · Vorkalkulation mit belegten Annahmen, keine Garantie · Referenzgebäude: Mittel/Altbau, 120 Heizkörper, 6 Geschosse, 1.500 m², Gas, vorhandenes Gateway",
)

= Überblick

Die Studie bildet die Lieferung einer LoRaWAN-Heizungssteuerung als *virtuelles
Unternehmen* ab: einen kleinen technischen Betrieb, der auf offenem LoRaWAN plant,
installiert und betreibt und dabei den vorhandenen ChirpStack-Stack samt der
Provisioning-App (F-0005) wiederverwendet. So werden die Kosten realistisch — nicht
nur Gerät und Montage, sondern die ganze Prozesskette von der Anfrage bis zum Betrieb.

Das *Referenzgebäude* (ein fiktives, aber typisches Objekt) ist ein Mittel/Altbau mit
120 Heizkörpern auf 6 Geschossen, 1.500 m², Gasheizung, vorhandenem Gateway. Jahresnutzen
≈ 2.880 €, Kern-CAPEX (Gerät + Montage) = 13.200 €.

= Die Prozesskette

#figure(
  image("assets/process-flow.svg", width: 100%),
  caption: [Acht Schritte von der Anfrage bis zum Betrieb; Balkenbreite ∝ Kosten je Schritt.],
)

#table(
  columns: (auto, 1.4fr, 1.3fr, auto, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x >= 3 { right } else { left },
  table.header(th("#"), th("Schritt"), th("Rolle"), th("Zeit"), th("Kosten")),
  [1], [Erstkontakt & Bedarfsklärung], [Projektleitung], [0,5 T], [320 €],
  [2], [Begehung & Funk-Voruntersuchung], [Ing. + Installateur], [1 T], [1.080 €],
  [3], [#text(fill: warn)[⚙] Auslegung & Angebot], [Ingenieur (Planung)], [0,5 T], [320 €],
  [4], [Auftrag & Beschaffung], [Projektleitung], [1 T], [9.040 €],
  [5], [LNS- & Provisioning-Vorbereitung], [Ingenieur (Betrieb)], [0,5 T], [320 €],
  [6], [Installation & Inbetriebnahme], [Installateur + Ing.], [1–2 T], [5.440 €],
  [7], [#text(fill: warn)[⚙] Abnahme & Soll-Ist], [Ingenieur + Kunde], [0,5 T], [320 €],
  [8], [Betrieb, Monitoring & Wartung], [Ingenieur (Betrieb)], [laufend], [1.238 €/a],
)
#text(8pt, fill: muted)[⚙ = Kalkulationspunkt (Sizing, Rückrechnung, Make-vs-Buy werden hier angewandt).]

= Kostenfluss & Summen

#table(
  columns: (1fr, auto, 1.4fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 1 { right } else { left },
  table.header(th("Block"), th("€"), th("Anmerkung")),
  [Kernkosten (Gerät + Montage)], [13.200], [120 × 110 € — das, was der Rechner zeigt],
  [Prozess-Overhead], [3.640], [Planung, Begehung, PM, Abnahme — sonst unsichtbar],
  [*Vollkosten-CAPEX*], [*16.840*], [realistische „virtuelles Unternehmen"-Sicht],
  [OPEX (laufend)], [1.238/a], [Batterie 228 + Monitoring 960 + Hosting 50],
  [optional: Hydraulischer Abgleich], [9.000], [120 × 75 € — separater Fachbetrieb],
)

#callout(title: "Befund", color: warn)[
  Der nackte Hardware-Blick (Kern-CAPEX, Payback 4,6 J.) ist optimistisch.
  Vollkostenbelastet *mit Prozesskette und laufendem Betrieb* liegt das Referenzgebäude
  bei *~10,3 Jahren* — genau auf der 10-Jahres-Grenze und fragil.
]

= Kritischer Review — Nachbesserung je Schritt

Elf Auditoren haben jeden Schritt und jede Kostenposition kritisch hinterfragt. Kernmuster:
*Doppelzählungen von Aufwand, den das Modell selbst als „sunk" deklariert*, und der
*falsche Stundensatz* (Verkaufs- statt Kostensatz).

#table(
  columns: (auto, 1.5fr, 1.6fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 3 { right } else { left },
  table.header(th("Schritt"), th("Kritischer Befund"), th("Empfehlung"), th("Effekt")),
  [1], [Ingenieur-Satz (80 €/h) für Checkliste; Daten bis 3× erfasst; kein Abbruch-Gate], [Auf PM-Satz, in Schritt 2 mergen, Qualify-out-Gate + Gateway-Flag], [320 → ~80 € (WHZ ~0)],
  [2], [Installateur-Tag leer (nichts zu montieren); Gateway platziert → nur 1-vs-2-Gateway-Frage], [Installateur-Tag streichen, Bring-up-Telemetrie (ADR-0018) nutzen, 0,5 T Ing.], [1.080 → ~560 €],
  [3], [#text(fill: bad)[Unter]bewertet: trägt alle 4 Kalkulationspunkte + bindendes Angebot, am Boden bepreist], [Auf ~480 € anheben; RF-Kalibrierung hierher; Zweit-Gateway-Kontingenz benennen], [−160 oder +160 €],
  [4], [70 €/Ventil ungehärtet; Gateway-0 verbirgt mögliches Zweit-Gateway; PM doppelt], [Bulk-Angebot (~−15 %), 2–3 % Ersatz-Ventile, PM kürzen], [9.040 → ~8.100 €],
  [5], [Widerspricht §5 (F-0005 „sunk"); idempotentes gRPC ~1–1,5 h, nicht 4 h], [In Schritt 6 mergen (~100 €); ABP-vs-OTAA-Lücke einmal fixen], [320 → ~100 €],
  [6], [Montage 4.800 € echt; Commissioning 640 € falsch (Class-A-Latenz, doppelt provisioniert)], [Skript-Commissioning ~120 €, Zwei-Wellen-Install, First-time-right-Reserve], [Commissioning −520 €],
  [7], [Bündelt 3 Jobs; „RF-Kalibrierung" ist interne Phase-4-Arbeit; kein Pass/Fail], [Entbündeln, RF-Kal. = 0 € Kundenscope, Pass/Fail gegen ChirpStack automatisieren], [320 → ~200 €],
  [8], [1.238/a = 43 % des Nutzens; Monitoring 960 € portfolio-fix auf 1 Gebäude; Hosting 50 € Phantom], [Hosting → 0; Monitoring event-getrieben ~280 €; Batterie als geplante Welle], [1.238 → ~500 €/a],
)

= Netto-Effekt: die schlanke Prozesskette

#table(
  columns: (1.4fr, auto, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x >= 1 { right } else { left },
  table.header(th("Block"), th("gebucht"), th("bereinigt")),
  [Prozess-Overhead], [3.640 €], [~1.500–2.400 €],
  [OPEX / Jahr], [1.238 €], [~500 € (Einzel) · ~300–380 € (Portfolio)],
  [loaded+ops Amortisation], [~10,3 J.], [*~7–8 J.* (Kostensatz + Monitoring)],
)

#callout(title: "Fazit", color: good)[
  Ohne einen einzigen Liefergegenstand zu verlieren, lassen sich *~1.500 € Prozess-Overhead*
  abbauen — durch Mergen von Schritt 1 in 2, Skript-Commissioning statt Hand-Provisionierung,
  Wiederverwendung der Gateway-Bring-up-Telemetrie und event-getriebenes Monitoring. Die
  eigentliche Skalierungs-Aufgabe ist *einmalig*: die ABP-vs-OTAA-Lücke in F-0005 schließen und
  Provisionierung per CSV/Charge fahren. Der größte versteckte Posten bleibt das *Zweit-Gateway-Risiko*
  für 6 Geschosse — als explizite, survey-gesteuerte Kontingenz im Angebot zu führen, nicht als
  stille 0-€-Annahme.
]
