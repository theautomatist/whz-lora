#import "report-template.typ": *
#show: report.with(
  title: "Grenzen, Restrisiken & ergänzende Methoden",
  subtitle: "Was der Einzel-Gateway-Feldtest NICHT abdeckt — und wie man echte Planungsfähigkeit gewinnt",
  meta: "Projekt whz-lora · WHZ · 2026-06-28 · Planungsdokument für Team & Leitung · Begleitpapier zum Testkonzept (test-concept.pdf)",
)

#callout(title: "Worum es geht", color: accent)[
  Der geplante Feldtest (1 Gateway, 3 TRVs, Fixpunkt-Soak) ist ein *präziser Schnappschuss
  der Uplink-Abdeckung an einer Gateway-Position* — und damit eine wertvolle Kalibrierungs-Basis.
  Er ist aber *kein Kapazitäts-, Downlink-, Diversity- oder Langzeittest*. Genau diese Lücken sind
  planungsentscheidend: Eine Heizungssteuerung lebt von *Downlinks* (Sollwerte), muss bei *35–120
  Aktoren* funktionieren und über *Jahre* stabil bleiben. Dieses Dokument benennt ehrlich, welche
  Risiken der Test *nicht* schließt, und welche ergänzenden Methoden — allen voran die *kalibrierte
  Simulation* — sie schließen.
]

= Scope-Grenze: was der Feldtest leistet — und was nicht

Der Feldtest beantwortet zuverlässig „*kommt das Uplink-Signal hier an?*" und liefert
gebäudespezifische Anker für die Kalibrierung (dB/Etage, Low-E-Dämpfung) am Archetyp A
(WHZ-Neubau) sowie eine passive Koexistenz-Momentaufnahme. Er beantwortet *nicht*
„*funktioniert die Steuerung eines ganzen Gebäudes über zehn Jahre?*". Die Übertragung der
Punkt-Messwerte auf ein Sizing-Modell für ganze Gebäude ist die eigentliche Restrisiko-Zone.

#table(
  columns: (1fr, 1fr),
  stroke: 0.5pt + rulec, inset: 7pt, align: top + left,
  table.header(th("Der Feldtest liefert"), th("Der Feldtest kann konstruktionsbedingt NICHT liefern")),
  [
    - Uplink-Empfangsqualität (RSSI/SNR/PDR) gerätenah
    - Kalibrier-Anker H1 (dB/Etage), H3 (Low-E) am Neubau
    - Fremd-LoRaWAN-Koexistenz (passiv, Momentaufnahme)
    - eine Gateway-Position, ein Zeitpunkt
  ],
  [
    - *Downlink*-Erreichbarkeit & Class-A-Latenz (misst nur Uplinks)
    - *Kapazität/Skalierung* für 35–120 Aktoren (Kollisionen, SF12-Well, Duty-Cycle)
    - *Diversity*-Gewinn eines 2. Gateways (mit 1 GW unmessbar)
    - *räumliche Varianz* über den Grundriss (3–4 statt 20–30 Punkte/Etage)
    - *zeitliche/saisonale* Stabilität (bis ca. 10,6 dB Schwankung)
  ],
)

#plain[Schweregrad im Register: *#text(fill: bad)[hoch]* = vor Inbetriebnahme eines Gebäudes quantitativ zu klären · *#text(fill: warn)[mittel]* = mit dokumentierter Reserve/Annahme überbrückbar · *niedrig* = beobachten/Prozess. Alle dB-/Prozent-/Frame-Bandbreiten sind, wo nicht im Feldtest gemessen, *Schätzungen* aus Literatur und Modell.]

= Risiko-Register

== A · Downlink & Kapazität (Skalierung)

Die schwersten und am häufigsten übersehenen Lücken: Eine Heizungssteuerung braucht Downlinks,
und drei Geräte zeigen kein Lastverhalten.

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*A1 · Downlink-Erreichbarkeit nicht nachgewiesen* \ #text(size: 8pt, fill: muted)[Feldtest misst nur Uplinks; Downlinks (RX1 frequenzidentisch / RX2 869,525 MHz, SF12) werden nicht gemessen — Uplink-PDR belegt keine Downlink-PDR.]],
  [Sollwerte, ADR-Kommandos, Join-Accepts kommen nicht an; ADR verharrt auf hohem SF → Airtime steigt.], [#text(fill: bad)[*hoch*]],
  [*Downlink-Loopback-Test* als Pflichtergänzung: confirmed Downlink je Punkt, ACK im Folge-Uplink loggen → Downlink-PDR-Karte.],

  [*A2 · Gateway-Downlink-Duty-Cycle als harte Kapazitätsgrenze* \ #text(size: 8pt, fill: muted)[3 Geräte lasten das GW-Budget nie aus; kritisch erst ab ca. 20+ Aktoren mit bestätigten/häufigen Downlinks.]],
  [RX1: je Subband L und M getrennt 1 % = 36 s/h; SF12 mit 4–12 B ca. *25–34 Downlinks/h je Subband*. RX2 (10 %, 360 s/h): ca. 363 ACK/h, mit Payload nur *225–275/h*, geteilt über alle Geräte. ChirpStack erzwingt *kein* Limit.], [#text(fill: bad)[*hoch*]],
  [Duty-Cycle-Last-Simulation (Downlink-Burst). *Achtung:* im aktuellen Kerlink-KerOS→UDP→Gateway-Bridge-Pfad ist `concentratord` *nicht im Pfad* → *keinerlei* automatische Duty-Cycle-Überwachung. Downlink-Grenze ins Sizing-Modell aufnehmen.],

  [*A3 · SF12-Well-Instabilität* \ #text(size: 8pt, fill: muted)[Bestätigte Uplinks können unter realer Last in SF12 kollabieren; mit 3 Geräten (ADR aus) strukturell nicht reproduzierbar.]],
  [Bei ca. 100 confirmed Uplinks unter Last PDR-Kollaps < 10 % möglich → Gebäude nicht mehr regelbar.], [#text(fill: bad)[*hoch*]],
  [ADR im *Produktivbetrieb* aktivieren (anders als im Test); Simulator-Lasttest 35/120 Geräte; ChirpStack-ADR mit Min-SF-Floor (z. B. SF7).],

  [*A4 · Uplink-Kollisionslast bei 35–120 Aktoren* \ #text(size: 8pt, fill: muted)[3 Geräte erzeugen kaum Kollisionen; statistisch relevant erst ab ca. 20+ auf gleichem SF/Kanal.]],
  [SF7/10 min: Airtime ca. 0,14 % (unkritisch); SF12 ohne ADR: ca. 3,3 % (nähert sich kritisch; ALOHA `P_success ≈ e^(-2·G)`).], [#text(fill: warn)[*mittel*]],
  [Simulator-Lasttest (35 & 120 Geräte, SF7/ADR-ein und SF12/ADR-aus); Airtime-Budget als Nebenbedingung der Gateway-Anzahl.],

  [*A5 · Class-A-Downlink-Latenz* \ #text(size: 8pt, fill: muted)[Kommandos warten in der Queue bis zum nächsten Aktor-Uplink; Feldtest erhebt keine Latenz-Statistik.]],
  [Bei 10-min-Intervall max. 10 min Verzug (für Heizung tolerierbar, therm. Zeitkonstante ca. 60 min); bei 30 min/verpassten Uplinks sinkt die Regelgüte.], [#text(fill: warn)[*mittel*]],
  [Uplink-Intervall ≤ 10 min; prädiktive/zeitgesteuerte Sollwertkurve statt Echtzeit-Regelung; Queue- vs. ACK-Timestamp messen.],
)

== B · Sizing / Gateway-Planung

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*B1 · Gateway-Positions-Bias* \ #text(size: 8pt, fill: muted)[Abdeckung nur von einer vorab gewählten GW-Position; mit 1 GW nur eine Position je Szenario messbar.]],
  [Sizing nimmt den getesteten Standort als Referenz. Laut Literatur war bei 53 % der Messorte *nicht* der nächste GW der beste → nicht standortunabhängig.], [#text(fill: bad)[*hoch*]],
  [Alternativ-GW-Standort (z. B. Etage 2 Mitte vs. Etage 3 Ecke) mit identischen Punkten vergleichen; Begehung (P1-06) muss ≥ 2 Positionen screenen.],

  [*B2 · Diversity-Gewinn eines 2. Gateways bleibt Annahme* \ #text(size: 8pt, fill: muted)[„1 vs. 2 GW" aus Faustformel, nicht Messung; mit 1 GW strukturell unmessbar.]],
  [1-GW-Empfehlung kann Lücken haben; 2-GW teurer als nötig. Literatur: +60 % Kapazität, First-Try-PDR 99,95 % (Multi-GW) vs. 95,7 % (Single).], [#text(fill: warn)[*mittel*]],
  [Zweites Gateway für einen Termin leihen (Dragino LPS8N ca. 80–100 €); an Worst-Case-Punkten aus H2 direkt vergleichen.],
)

== C · Statistik & Messmethodik

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*C1 · Räumliche Unterabtastung* \ #text(size: 8pt, fill: muted)[9–12 Punkte (ca. 3–4/Etage); üblich sind 20–30/Etage. N=20 → 95-%-Wilson-KI ca. ±14 Pp; bei 20/20 untere Grenze ca. 84 %.]],
  [Kein Bild der räumlichen Varianz; anomale Räume (Metallregale, Schächte) unerfasst; Grundriss-Worst-Case kann 5–10 dB unter dem gemessenen liegen.], [#text(fill: warn)[*mittel*]],
  [Walk-Survey mit Schnell-Knoten (Dragino LHT52, 20-s-Intervall) ≥ 20 Punkte/Hauptetage; im Sizing Unsicherheitsband ±10 dB für ungemessene Positionen.],

  [*C2 · Momentaufnahme ≠ Betrieb über Zeit* \ #text(size: 8pt, fill: muted)[Test auf halben/ganzen Tag ausgelegt; Belegung+HVAC bis 10,6 dB (arXiv 2505.06375); Shadowing-σ bis 18,4 dB (arXiv 2510.04346).]],
  [PDR gilt nur für Messbedingungen; Winterbetrieb 3–10 dB abweichend; Fade-Margin 25,7 dB (99 % PDR) setzt 12-Monats-Statistik voraus.], [#text(fill: warn)[*mittel*]],
  [Messzeitpunkt/Belegung protokollieren; Fade-Margin aus Literatur (25,7 dB @ 99 % PDR) auf Worst-Case addieren statt Messwert als Betriebsgrenze; optional Langzeit-Soak (24–72 h).],

  [*C3 · Reproduzierbarkeit / Confounder* \ #text(size: 8pt, fill: muted)[Manuelle Platzierung; Body-Shadowing 2–5 dB (IEEE 7275497); Reproduzierbarkeits-σ indoor ca. 3 dB.]],
  [Punkt-zu-Punkt-Streuung bis 3–5 dB unabhängig vom Kanal; ein „schlechter" Moment kippt PDR 100 → 90 %.], [*niedrig*],
  [Messer verlässt 5-m-Bereich; Baseline-Doppelmessung (P0 Anfang/Ende) als Drift-Detektor; an ≥ 2 Punkten Wiederholungsrunde → Reproduzierbarkeits-Schätzer.],
)

== D · Modellgüte / Kalibrierung

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*D1 · Übertragung auf andere Archetypen ungesichert* \ #text(size: 8pt, fill: muted)[Test kalibriert nur den Neubau (Archetyp A); Pfadverlustmodelle 7–10 dB RMSE selbst nach Kalibrierung, ohne Messung eher 10–15 dB.]],
  [GW-Dichte-Empfehlungen können um *Faktor 2* danebenliegen — zu wenig GW = Lücken, zu viele = unnötige CAPEX.], [#text(fill: bad)[*hoch*]],
  [Je Archetyp ≥ 1 Mess-Referenz (eigener Test ODER peer-reviewed Literatur ähnlichen Gebäudes); im Sizing als Bandbreite mit Archetyp-Konfidenz ausweisen.],
)

== E · Bauzustand

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*E1 · Bauzustand zum Messzeitpunkt* \ #text(size: 8pt, fill: muted)[WDVS-Dampfbremsfolie/Estrich evtl. noch nicht eingebaut; Folie (Schätzwert 60–85 dB Schirmung) von innen unsichtbar; kein Before/After-Design.]],
  [Sizing unterschätzt Fade-Margin/GW-Anzahl im Fertigbau; Archetyp-A-Kalibrierung zu optimistisch.], [#text(fill: bad)[*hoch*]],
  [Bauzustand vor der Messung voll dokumentieren (Foto, Materialcode); Caveat im Bericht; wenn möglich Wiederholung nach Fertigstellung; WDVS-Worst-Case als obere Bandbreite (+5–17 dB).],

  [*E2 · Low-E: Verglasung fertig, perimetrische Metalldichtung offen* \ #text(size: 8pt, fill: muted)[Stift-Spiegeltest erkennt das Glas, nicht aber Stahlblenden/Rollladenkästen.]],
  [H3-Wert kann im Fertigbau um 3–10 dB abweichen; Sizing falsch kalibriert.], [#text(fill: warn)[*mittel*]],
  [Fensterrahmenbauart + Rollladenkasten (Stahlblende ja/nein) protokollieren; Messwert als Bandbreite, wenn Einbausituation unklar.],
)

== F · Umwelt / Belegung

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*F1 · Momentaufnahme der Umgebung* \ #text(size: 8pt, fill: muted)[Belegung/Türen/Möbel/Feuchte fix; arXiv 2505.06375 (6 Mon., 1,3 Mio. Punkte): bis 10,58 dB RSSI-Verschiebung.]],
  [RSSI 3–10 dB zu gut (leeres Gebäude) oder zufällig schlechter; Fade-Margin/PDR-Erwartung zu optimistisch.], [#text(fill: bad)[*hoch*]],
  [N ≥ 20/Punkt glättet Kurzzeit-Effekte; Belegungszustand im Messblatt; Fade-Margin mit 5–10 dB Streuband aus Literatur statt Punktwert.],

  [*F2 · Saisonale Effekte* \ #text(size: 8pt, fill: muted)[Laub (Outdoor-Link), Raumfeuchte im Heizbetrieb; arXiv 2510.04346 (12 Mon.): Temperatur/Feuchte korrelieren mit Shadow-Fading.]],
  [Winter-/Sommer-Drift 2–5 dB — für enges Fade-Margin-Budget signifikant.], [#text(fill: warn)[*mittel*]],
  [Messtag/Jahreszeit als Caveat; Fade-Margin nicht unter 20 dB; CAF-Monitoring (7+ Tage) auch außerhalb der Heizsaison wiederholen.],
)

== G · RF-Koexistenz & zeitliche Dynamik

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*G1 · Strukturelles Wachstum der Fremdnetz-Last* \ #text(size: 8pt, fill: muted)[60–120-min-Scan = Momentwert; Smart-Meter-Rollout EU: 195 (2024) → 285 Mio. (2029), viele LoRaWAN EU868.]],
  [CAF in 3 J. auf 5–10 % erhöht `P_Koll` auf 10–18 % (Gelb) → erzwingt GW-Diversity/SF-Optimierung als ungeplante Nachkosten.], [#text(fill: bad)[*hoch*]],
  [CAF als *Dauer*-Monitoring (`field_logger.py` Koexistenz-Modus), nicht Einmal-Survey; SLA-Schwelle: CAF > 5 % auf Pflichtkanal → Alert; Sizing mit 3–5 % Band-Occupancy-Reserve.],

  [*G2 · Tagesganglinie des CAF* \ #text(size: 8pt, fill: muted)[Scan zu festem Fenster; Zähler senden oft nachts, Forschungssensoren tags.]],
  [CAF-Ampel „Grün" obwohl Nacht-CAF „Gelb" → PDR-Zusagen zu optimistisch.], [#text(fill: warn)[*mittel*]],
  [Mindest-Scan 120 min; für finale Bewertung 24-h-Durchlauf; Uhrzeit/Wochentag im Bericht.],

  [*G3 · Fremd-LoRaWAN-Interferenz (H5)* \ #text(size: 8pt, fill: muted)[Feldtest erhebt H5 nur passiv; gibt noch keine quantitative Aussage.]],
  [CAF > 5 % auf Standardkanälen → höhere Kollisionsrate; dichtes Netz auf 869,525 MHz belastet RX2-Budget zusätzlich.], [*niedrig*],
  [H5-Messung auswerten; bei CAF > 2 % Kanalplan auf weniger belegte Kanäle; ggf. Zweit-GW zur Redundanz.],
)

== H · Geräte-Repräsentativität

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*H1 · Test-TRV ≠ final beschaffter Aktor* \ #text(size: 8pt, fill: muted)[Antenne/Firmware/ADR können abweichen; Serienprodukt evtl. anderer Typ.]],
  [Sizing stützt sich auf das Link-Budget des Test-TRV; Serienteil ggf. 3–6 dB anders → GW-Dichte-Entscheidung (F7) kann kippen.], [#text(fill: bad)[*hoch*]],
  [Final-Aktor früh festlegen / Muster besorgen; A/B-Test (je 20 Pakete Test- vs. Ziel-TRV am selben Punkt); Delta als Korrekturfaktor.],

  [*H2 · Batteriealterung & Kälte* \ #text(size: 8pt, fill: muted)[Frisch-Batterie-Messung; Alkaline bei 0 °C bis 50 % Kapazitätsverlust; TX sinkt mit Batterietiefstand.]],
  [Winter Jahr 3–5: TX bis 3 dB unter Messwert → PDR unter Schwelle; ungeplante Batteriewellen.], [#text(fill: warn)[*mittel*]],
  [Batterie-Fade-Margin 3 dB als Alterspuffer ins Sizing; Akku-Restwert-Alert (P7-01); Lithium-Primärzellen statt Alkaline.],
)

== I · Prozess / Mensch

#table(
  columns: (1.7fr, 1.15fr, auto, 1.5fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Risiko / warum offen"), th("Auswirkung"), th("Schwere"), th("Maßnahme")),
  [*I1 · Montagevarianz durch Installateur* \ #text(size: 8pt, fill: muted)[Feldtest nutzt normierten 3D-Halter; im Rollout variable Winkel/Metallabstand (Kopplungsverlust 3–10 dB bei < 10 mm).]],
  [Rollout 5–15 % höhere First-Time-Fail-Rate; PDR-Verteilung breiter; SLA gefährdet.], [#text(fill: warn)[*mittel*]],
  [Installations-Checkliste (P4-03) mit Foto-Pflicht; Stichproben-Commissioning nach Welle 1 (P4-04): DevEUI-Scan + Join + RSSI vor Abnahme.],

  [*I2 · Provisionierungsfehler* \ #text(size: 8pt, fill: muted)[Bulk-Import von 120 Geräten realistisch 1–5 % Fehlerrate; ChirpStack loggt MIC-Mismatch nur als „Device not found".]],
  [5–10 % der Aktoren bleiben offline; Abnahme-Gate (P4-07) scheitert; Nacharbeit in Mieterräumen.], [#text(fill: warn)[*mittel*]],
  [DevEUI-Charge-Abgleich Ware vs. CSV (P2-05); Format-/Dubletten-Check beim Import (P3-03); Stichproben-Join bei Wareneingang (P2-04).],

  [*I3 · Zugang zu Mieterräumen* \ #text(size: 8pt, fill: muted)[WHZ-Neubau bei Messung frei zugänglich; Feldtest misst keine Zugangszeiten/Verweigerung.]],
  [Batteriewellen 2–3× länger; OPEX zu optimistisch; SLA-Reaktionszeiten verfehlt.], [#text(fill: warn)[*mittel*]],
  [Fragenkatalog E10 (Zugang) bei Begehung verbindlich; Pilot: reale Zugangsquote/Aufwand in OPEX rückführen (P7-08).],

  [*I4 · Spätere bauliche Änderungen* \ #text(size: 8pt, fill: muted)[Trennwände/Durchbrüche/Fassade ändern Pfadverlust dauerhaft; kein Monitoring adressiert bauliche Drift.]],
  [Einzelne Aktoren verlieren Konnektivität ohne Geräte-/Netzfehler; schwer diagnostizierbar.], [*niedrig*],
  [Asset-Register (P6-02) führt Datum der letzten RF-Verifikation; jährlicher Review (P7-08): RSSI/PDR-Trend, bei Drift > 5 dB Alarm + Ursachentrennung.],
)

= Ergänzende Methoden

Der *Haupthebel ist die kalibrierte Simulation*: Sie multipliziert die Reichweite weniger
echter Messwerte. Wichtige, in der Verifikation geschärfte Einschränkung — sie ist auf der
*Netzwerk-/MAC-Schicht* belastbar (PDR, ADR-Konvergenz, Kollisionen, Duty-Cycle), auf der
*HF-Indoor-Abdeckung* aber strukturell begrenzt (RMSE 7–8 dB).

#figure(
  image("assets/risiken-methodenstack.svg", width: 100%),
  caption: [Vier Stufen mit steigender Planungssicherheit. Jede Stufe schließt bestimmte Risiken (Nummern aus dem Register); die kalibrierte Simulation ist der Haupthebel, ihre HF-Grenze ist als Warnung markiert.],
)

#table(
  columns: (1.1fr, 1.7fr, auto, 1.6fr),
  stroke: 0.5pt + rulec, inset: 5.5pt, align: top + left,
  table.header(th("Methode"), th("Was sie liefert / schließt (Risiko)"), th("Aufwand"), th("Voraussetzung / Eigen-Grenze")),
  [#text(fill: accent)[*★ Kalibrierte Simulation*] (ns-3 `signetlabdei/lorawan`, FLoRa/OMNeT++; Indoor-RadioPlanner)],
  [Netzwerk-/MAC-Schicht *zuverlässig*: PDR, ADR-Konvergenz, Kollisionen, Duty-Cycle für 35–120 Aktoren, 2–3 GW, SF-Verteilung, Archetyp-Variation — ohne neue Kampagnen. *Schließt:* A2, A3, A4, B2, D1.], [mittel],
  [ns-3/FLoRa + Python; Kalibriereingaben H1/H3. *Grenze:* „wenige Messwerte" genügen *nicht* für Indoor-HF-Abdeckung (Box-Modell, RMSE 7–8 dB) → HF-seitig Fade-Margin *≥ 15 dB*.],

  [Downlink-Loopback-Test], [RX1/RX2-Empfangsrate je Punkt (confirmed Downlink → ACK). *Schließt:* A1.], [niedrig], [ChirpStack-API + `field_logger.py` (vorhanden). Testet Abdeckung, nicht Kapazität.],

  [Duty-Cycle-Last-Simulation], [Praktische Downlink/h-Obergrenze dieses GW. *Schließt:* A2.], [mittel], [Burst-Skript via ChirpStack-REST; `concentratord` *nicht* im Kerlink-Pfad → kein DC-Enforcement.],

  [Simulator-Lasttest (`chirpstack-simulator`, `docker-compose.test.yml`)], [35–120 simulierte Geräte: Kollisionsrate, PDR-Degradation, SF12-Well-Onset. *Schließt:* A3, A4.], [mittel], [Image bereits vorbereitet. Keine echte Funkstrecke → Grenze konservativ.],

  [Multi-Gateway-/Diversity-Test (2. portables GW)], [Empirischer Diversity-Gewinn (1 vs. 2 GW). *Schließt:* B1, B2.], [mittel], [2. Gateway (Leihe / Dragino LPS8N ca. 80–100 €); ≥ 2 Personen; gilt je Standort-Kombi.],

  [Schnell-Knoten-Walk-Survey (Dragino LHT52 / RAK10701-Plus, 20-s-Intervall)], [Coverage-Heatmap: Punkt in 3–7 min; Kalibrierbasis für die Simulation. *Schließt:* C1.], [niedrig], [Endknoten (ca. 21–200 €); mit TRV-Soak kombinieren (keine Montagerealität).],

  [Reproduzierbarkeits-Doppelmessung], [Systematischer Fehlerterm (RSSI-Differenz zweier Runden). *Schließt:* C3.], [niedrig], [Zweite Runde, identisches Punktblatt. Nur Kurzzeit-Varianz.],

  [Langzeit-/Wiederholungsmessung (saisonal; Mehrwochen-Soak)], [Temporaleffekt (bis 10,58 dB); statische vs. variable Dämpfung. *Schließt:* C2, F1, F2.], [hoch], [Permanente GW-Installation, `field_logger.py` 24/7. Nicht für Erstplanung.],

  [Koexistenz-Monitoring ≥ 7 Tage], [Tages-/Wochenganglinie des CAF. *Schließt:* G1, G2, G3.], [niedrig], [`field_logger.py` Koexistenz-Modus dauerhaft. 7 Tage erfassen keine Saison.],

  [SDR/Spektrumanalyzer (RTL-SDR, HackRF)], [Vollbild 863–870 MHz inkl. Nicht-LoRa (M-Bus, EnOcean…). *Schließt:* G3 (Nicht-LoRa).], [niedrig], [RTL-SDR ca. 30 € + SDR++. Relativer Pegel, kein kalibriertes Absolutspektrum.],

  [TTN-Mapper + Helium (Desk-Pre-Check)], [Vorab-Übersicht öffentlicher Netze. *Schließt:* G3 (Triage, P1-05).], [niedrig], [Browser. Nur öffentliche Netze → ersetzt CAF-Messung nicht.],

  [Material-/Dämpfungscharakterisierung (kalib. TX/RX + Bauplan)], [Gebäudespezifische dB-Werte (Decke, Low-E, WDVS). *Schließt:* D1, E1, E2.], [mittel], [Kalib. TX/RX (oder HackRF+RTL-SDR); Bauplan-Zugang (WHZ-GM); beidseitiger Bauteilzugang.],

  [A/B-Gerätetest (Test- vs. Ziel-TRV)], [ΔRSSI + reales ADR-Verhalten je Firmware. *Schließt:* H1.], [niedrig], [Muster der Ziel-Generation vor Begehung; ChirpStack Frame-Log.],

  [Prozess-FMEA aus Pilot-Rollout], [Fehlerquote je Schritt (EUI, Metallnähe, Join). *Schließt:* I1–I4.], [niedrig], [Pilot 10–20 Aktoren mit Fehlerliste (P4-03..P4-07). Installateur-spezifisch.],
)

= Priorisierte Roadmap

Quick Wins zuerst, dann der Haupthebel, dann Langzeit. Aufwand: *niedrig* = Stunden–1 Tag /
vorhandene Mittel · *mittel* = wenige Tage / Leihgerät · *hoch* = Wochen–Monate / Daueraufbau.

#table(
  columns: (auto, 1.8fr, 1.5fr, auto),
  stroke: 0.5pt + rulec, inset: 6pt, align: top + left,
  table.header(th("#"), th("Schritt"), th("Warum (Risiken)"), th("Aufwand")),
  [1], [*TTN-Mapper/Helium Desk-Check* — öffentliche Netze um den Standort prüfen (P1-05)], [billigster Vorab-Filter; setzt Erwartung für H5/CAF (G3)], [niedrig],
  [2], [*Downlink-Loopback in den Feldtest integrieren* — `field_logger.py` um confirmed Downlink + ACK-Logging erweitern → Downlink-PDR-Karte], [schließt das gravierendste offene Risiko *mit vorhandener Hardware* (A1)], [niedrig],
  [3], [*Walk-Survey-Schnellknoten* (Dragino LHT52, 20 s) auf ≥ 20 Punkten/Etage → Coverage-Heatmap], [behebt räumliche Unterabtastung (C1) + liefert Kalibrierbasis für die Simulation], [niedrig],
  [4], [*Zweites Gateway leihen* + A/B-Positions-/Diversity-Test an identischen Punkten], [einzige empirische Antwort auf B1 (hoch) & B2; klärt F7 „1 vs. 2 GW"], [mittel],
  [5], [*A/B-Gerätetest + Bauzustands-Protokoll* — Muster der Ziel-TRV; Wandtypen fotografieren/codieren], [schließt H1 (hoch) und E1/E2 *bevor* kalibriert wird], [niedrig–mittel],
  [6], [#text(fill: accent)[*★ Kalibrierte Simulation aufsetzen*] — ns-3/FLoRa mit H1/H3 + Heatmap kalibrieren; Vollausbau, 2–3 GW, Kapazität rechnen], [Multiplikator für A2/A3/A4/B2/D1. *HF nur mit Fade-Margin ≥ 15 dB*], [mittel],
  [7], [*Simulator- & Duty-Cycle-Lasttest* — `chirpstack-simulator` 35/120 confirmed; Downlink-Burst bis Budget-Erschöpfung], [quantifiziert SF12-Well (A3), Uplink-Kollision (A4), Downlink-Grenze (A2)], [mittel],
  [8], [*Pilot-Rollout + Langzeit-/Koexistenz-Monitoring* — 10–20 Aktoren, Prozess-FMEA; CAF 4 × 1 Woche; 24/7-Soak], [schließt zeitliche Dynamik (C2, F1, F2, G1, G2) + Prozess (I1–I4); validiert das Sizing im Betrieb], [hoch],
)

#callout(color: teal)[
  *Lesehilfe:* Schritte 1–5 sind Quick Wins (niedriger Aufwand, decken mehrere *#text(fill: bad)[hoch]*-Risiken). Schritt 6 ist der zentrale Multiplikator. Schritte 7–8 sichern Kapazität und Langzeit ab und gehören in spätere Direktiven / den Piloten. Die roten (hoch-)Felder liegen fast vollständig in *Downlink/Kapazität (A)* und *Modellübertragung (D/E/H)* — genau dort setzen die Schritte 2, 4, 5, 6 und 7 an.
]

#callout(color: warn)[
  *Hinweis zu den Zahlen:* dB-, Prozent- und Frame/h-Werte sind, wo nicht direkt im Feldtest
  gemessen, als *Schätzungen* aus Literatur und Sizing-Modell zu lesen. Die Duty-Cycle-Zahlen
  (Subband-getrennte 1-%-Töpfe, RX2 360 s/h, ToA-abhängige Frame/h-Grenzen) und der Befund, dass
  im aktuellen Kerlink-Deployment-Pfad *keine* automatische Duty-Cycle-Überwachung aktiv ist,
  sind die in der Verifikation geprüften/korrigierten Fassungen.
]
