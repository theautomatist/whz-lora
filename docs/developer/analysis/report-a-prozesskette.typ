#import "report-template.typ": *
#show: report.with(
  title: "Report A — Prozesskette & Lieferprozess",
  subtitle: "LoRaWAN-Heizungssteuerung als virtuelles Unternehmen (Make-Pfad) — verständliche Fassung",
  meta: "Projekt whz-lora · WHZ · 2026-06-13 · Vorkalkulation mit belegten Annahmen, keine Garantie · Referenzgebäude: Mittel-/Altbau, 120 Heizkörper, 6 Geschosse, 1.500 m², Gasheizung, vorhandenes Gateway",
)

#callout(title: "Worum geht es?", color: accent)[
  Wir wollen die Heizkörper eines Gebäudes einzeln und automatisch regeln, um Heizenergie
  zu sparen. Statt eines fertig gekauften Systems planen, installieren und betreiben wir es
  selbst — auf Basis einer Funktechnik namens *LoRaWAN*. Diese Studie beantwortet zwei
  Fragen: (A) *Was kostet die ganze Lieferkette wirklich?* und (B) *An welchen Stellschrauben
  hängt, ob sich das lohnt?* (Report B).
]

Die wichtigsten Fachbegriffe vorab in Alltagssprache:

#table(
  columns: (auto, 1fr), stroke: 0.5pt + rulec, inset: 6pt,
  table.header(th("Begriff"), th("In einfachen Worten")),
  [*LoRaWAN*], [Funktechnik für kleine Datenmengen über große Reichweite bei winzigem Stromverbrauch — ideal für batteriebetriebene Geräte im ganzen Gebäude. Anders als WLAN funken sie nur selten und in winzigen Paketen und schlafen sonst, um Batterie zu sparen.],
  [*Gateway*], [Die Funk-Basisstation. Empfängt die Signale aller Geräte und reicht sie an die Software weiter — wie ein WLAN-Router, aber für LoRaWAN.],
  [*Aktor* (Heizkörperthermostat)], [Das funkgesteuerte Ventil am Heizkörper, das selbsttätig auf- und zudreht. Ersetzt das Handrad.],
  [*LNS / ChirpStack*], [Die zentrale Software, die alle Geräte verwaltet und Funkpakete entschlüsselt — das „Gehirn" des Netzes. Läuft bereits, kostet also nichts extra.],
  [*F-0005*], [Unsere eigene Software, die jedes neue Gerät automatisch ins Netz aufnimmt. Im Einsatz, hat aber eine bekannte Lücke (siehe Schritt 5).],
  [*CAPEX*], [Einmalige Anschaffungskosten (Geräte, Montage, Planung).],
  [*OPEX*], [Laufende Betriebskosten pro Jahr (Wartung, Überwachung, Batterien).],
  [*Payback / Amortisation*], [Zeit, bis die eingesparten Heizkosten die Investition wieder einspielen. Kürzer = besser.],
)

= Überblick

Die Studie betrachtet die Lieferung der LoRaWAN-Heizungssteuerung so, als würde sie ein
kleiner Technikbetrieb erbringen — ein *virtuelles Unternehmen*. Dieser Betrieb plant,
installiert und betreibt das Netz auf offener LoRaWAN-Technik und nutzt dabei den schon
vorhandenen ChirpStack-Server samt der eigenen Einrichtungs-Software F-0005 wieder. Dieser
Blickwinkel ist wichtig, weil so die Kosten *realistisch* werden: nicht nur Gerät und
Montage, sondern die ganze Kette von der ersten Anfrage bis zum laufenden Betrieb.

#plain[Wir rechnen nicht nur, was die Ventile kosten, sondern alles, was nötig ist, damit
am Ende geheizt und gespart wird — Planung, Begehung, Einbau, Abnahme und Wartung inklusive.]

Das *Referenzgebäude* ist ein erfundenes, aber typisches Objekt, an dem alle Zahlen
durchgerechnet werden: ein Mittel-/Altbau mit 120 Heizkörpern auf 6 Geschossen, 1.500 m²,
Gasheizung und bereits installiertem Gateway. Daraus ergeben sich *Jahresnutzen ≈ 2.880 €*
(jährlich eingesparte Heizkosten) und *Kern-CAPEX = 13.200 €* (nur Gerät + Montage).

= Die Prozesskette

#figure(image("assets/process-flow.svg", width: 100%), caption: [Acht Schritte von der Anfrage bis zum Betrieb; Balkenbreite ∝ Kosten je Schritt.])

#callout(color: accent)[
  *Hinweis:* Die acht Schritte hier sind die *kostenrelevante Sicht*. Das vollständige
  Geschäftsprozessmodell des Betriebs — *45 Schritte, 7 Rollen/Swimlanes*, inkl. Beschaffung,
  Hersteller-Schlüsselliste, Wareneingang, Ein-/Auslagern, Kommissionierung, DOA/RMA und
  Abrechnung — steht als Swimlane in `process-model.md` / `process-swimlane.pdf`.
]

Die Lieferung läuft in acht Schritten ab. *T = Personentag* (ein Arbeitstag einer Person).

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

#callout(color: warn)[
  *Hinweis zu Schritt 4:* Die 9.040 € sind fast vollständig der *Geräte-Einkauf* (≈ 8.400 €
  Hardware für 120 Ventile), nicht Arbeitszeit — hier wird die gesamte Hardware bestellt.
]
#text(8pt, fill: muted)[⚙ = Kalkulationspunkt: Hier werden Auslegung (Sizing), Rückrechnung und der Vergleich „selbst bauen vs. fertig kaufen" angewandt.]

Kurz erklärt, was hinter den dichten Schritten steckt:

- *Schritt 2 — Funk-Voruntersuchung (Survey):* Vor Ort wird geprüft, ob das Funksignal
  überall ankommt. Nötig, weil *868-MHz-Funk* (das LoRaWAN-Band in Europa) durch
  Geschossdecken stark gedämpft wird. Den größten Anteil hat nicht die Wanddicke, sondern die
  *Bewehrungsmatte im Stahlbeton*: Das Stahlgitter wirkt wie ein Drahtkäfig (Faradaykäfig),
  der Funk abschirmt — eine durchgehend bewehrte Decke dämpft weit stärker als der Beton
  allein. Deshalb sind die durchlaufenden Decken eines 6-Geschossers der kritische Punkt.
- *Schritt 5 — Provisioning (Einrichtung):* Jedes Gerät muss dem Netzserver bekanntgemacht
  und mit Schlüsseln versehen werden. Bevorzugt per *OTAA* (Over-The-Air Activation): Das
  Gerät meldet sich beim Einschalten selbst an und leitet *frische Sitzungsschlüssel* ab —
  sicherer und wartungsärmer als *ABP* (feste, statische Schlüssel, bei Bedarf von Hand neu
  zu vergeben). Diese statische Schwäche ist die „ABP-vs-OTAA-Lücke" in F-0005 — sie einmal
  zu schließen ist eine einmalige Engineering-Aufgabe.
- *Schritt 6 — Commissioning:* Nach dem Schrauben wird jedes Ventil aktiviert und auf eine
  korrekte Funkverbindung geprüft.

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
  Der nackte Hardware-Blick (Kern-CAPEX, Payback 4,6 Jahre) ist optimistisch.
  Vollkostenbelastet *mit Prozesskette und laufendem Betrieb* liegt das Referenzgebäude bei
  *~10,3 Jahren* — genau auf der 10-Jahres-Grenze und damit fragil.
]
#plain[Schaut man nur auf die Ventile, ist das Geld nach 4,6 Jahren wieder drin. Rechnet man
ehrlich alles mit — Planung, Einbau, Wartung — dauert es etwa 10,3 Jahre. Das ist die Grenze,
ab der sich viele Betreiber fragen, ob es sich überhaupt noch lohnt.]

Der *hydraulische Abgleich* ist eine separate Maßnahme am Heizungssystem, *nicht* Teil der
LoRaWAN-Anlage. Dabei wird der Wasserdurchfluss durch alle Heizkörper so eingestellt, dass
jeder gleichmäßig warm wird — sonst überversorgt die Heizung die nahen und vernachlässigt die
fernen Heizkörper. Er kostet hier extra (9.000 €), verdoppelt aber die Einsparung (Report B).

= Kritischer Review — Nachbesserung je Schritt

Elf Auditoren haben jeden Schritt kritisch hinterfragt. Zwei Muster ziehen sich durch:
*Aufwand wird doppelt gezählt, obwohl das Kostenmodell ihn selbst als bereits bezahlt („sunk")
erklärt*, und es wird der *falsche Stundensatz* angesetzt — der Verkaufssatz (Preis für
Kunden) statt des reinen Kostensatzes (was die WHZ die Stunde wirklich kostet).

#plain[„Versunkene Kosten" (sunk costs) sind Dinge, die schon da und bezahlt sind — der
vorhandene Server, das vorhandene Gateway, die fertige Software. Wer sie erneut in die
Rechnung schreibt, macht das Projekt künstlich teuer.]

In der Effekt-Spalte steht „vorher → nachher"; „(WHZ ~0)" heißt: für die WHZ entstehen dabei
nahezu keine Kosten, weil es Eigenleistung ist.

#table(
  columns: (auto, 1.5fr, 1.6fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: (x, y) => if x == 3 { right } else { left },
  table.header(th("Schritt"), th("Kritischer Befund"), th("Empfehlung"), th("Effekt")),
  [1], [Ingenieur-Satz (80 €/h) für Checkliste; Daten bis 3× erfasst; kein Abbruch-Gate], [Auf PM-Satz, in Schritt 2 mergen, Qualify-out-Gate + Gateway-Flag], [320 → ~80 € (WHZ ~0)],
  [2], [Installateur-Tag leer (nichts zu montieren); Gateway platziert → nur 1-vs-2-Gateway-Frage], [Installateur-Tag streichen, Bring-up-Telemetrie nutzen, 0,5 T Ing.], [1.080 → ~560 €],
  [3], [#text(fill: bad)[Unter]bewertet: trägt alle 4 Kalkulationspunkte + bindendes Angebot, am Boden bepreist], [Auf ~480 € anheben; RF-Kalibrierung hierher; Zweit-Gateway-Kontingenz benennen], [−160 oder +160 €],
  [4], [70 €/Ventil ungehärtet; Gateway-0 verbirgt mögliches Zweit-Gateway; PM doppelt], [Bulk-Angebot (~−15 %), 2–3 % Ersatz-Ventile, PM kürzen], [9.040 → ~8.100 €],
  [5], [Widerspricht „F-0005 sunk"; wiederholbarer Software-Aufruf ~1–1,5 h, nicht 4 h], [In Schritt 6 mergen (~100 €); ABP-vs-OTAA-Lücke einmal fixen], [320 → ~100 €],
  [6], [Montage 4.800 € echt; Commissioning 640 € falsch (Class-A-Latenz, doppelt provisioniert)], [Skript-Commissioning ~120 €, Zwei-Wellen-Install, First-time-right-Reserve], [Commissioning −520 €],
  [7], [Bündelt 3 Jobs; „RF-Kalibrierung" ist interne Projektarbeit; kein Pass/Fail], [Entbündeln, RF-Kal. = 0 € Kundenscope, Pass/Fail gegen ChirpStack automatisieren], [320 → ~200 €],
  [8], [1.238/a = 43 % des Nutzens; Monitoring 960 € portfolio-fix auf 1 Gebäude; Hosting 50 € Phantom], [Hosting → 0; Monitoring ereignisgesteuert ~280 €; Batterie als geplante Welle], [1.238 → ~500 €/a],
)

Drei Befunde verdienen eine Übersetzung:

- *Class-A-Latenz (Schritt 6):* LoRaWAN-Geräte der Klasse A schlafen die meiste Zeit und
  „hören" nur kurz nach dem eigenen Senden auf Antworten. Man kann ihnen also nicht jederzeit
  einen Befehl schicken — bei einem 10-Minuten-Sendetakt vergehen bis zur Antwort *bis zu
  10 Minuten*. Das macht das Aktivieren langsam und erklärt, warum naives Commissioning zu
  teuer veranschlagt war.
- *Zweit-Gateway-Risiko (Schritte 2 & 4):* Bei 6 Geschossen mit durchlaufenden bewehrten
  Decken reicht ein einziges Gateway womöglich nicht durch alle Etagen. Ein verstecktes
  0-€-Versprechen wird so zur möglichen Zusatzposition.
- *Bring-up-Telemetrie (Schritt 2):* Beim Aufsetzen des Gateways fallen ohnehin Funk-Messdaten
  an (festgehalten in ADR-0018) — die kann man für die Voruntersuchung wiederverwenden, statt
  einen extra Installateur-Tag zu bezahlen.

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
  abbauen — durch Zusammenlegen von Schritt 1 in 2, Skript-Commissioning statt
  Hand-Provisionierung, Wiederverwendung der Gateway-Bring-up-Telemetrie und ereignisgesteuertes
  Monitoring. Die eigentliche Skalierungs-Aufgabe ist *einmalig*: die ABP-vs-OTAA-Lücke in
  F-0005 schließen und Provisionierung per CSV/Charge fahren. Der größte versteckte Posten
  bleibt das *Zweit-Gateway-Risiko* für 6 Geschosse — als explizite, vom Survey gesteuerte
  Kontingenz im Angebot zu führen, nicht als stille 0-€-Annahme.
]
#plain[Man kann denselben Service deutlich günstiger liefern, ohne etwas wegzulassen — vor
allem, indem man Routinearbeit automatisiert und nichts doppelt berechnet. Damit fällt der
Payback von ~10,3 auf ~7–8 Jahre.]
