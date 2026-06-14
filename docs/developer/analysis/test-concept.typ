#import "report-template.typ": *
#show: report.with(
  title: "Testkonzept — LoRaWAN-Funkabdeckung & -Stabilität",
  subtitle: "Mini-Messkampagne im WHZ-Neubau · Kalibrierung des Sizing-Modells (Phase 4)",
  meta: "Projekt whz-lora · WHZ · 2026-06-14 · 1 Kerlink-Gateway + dedizierter Testknoten + wenige TRV-Aktoren · ADR aus, feste SF · ~halber bis ganzer Tag",
)

= Ziel
#callout(title: "Worum es geht", color: accent)[Drei Modell-Zahlen aus model.md §7 am realen WHZ-Neubau (Archetyp A, RF-hostile: Low-E-Glas + metallbeschichtete Dämmung) empirisch kalibrieren — mit genau einem Kerlink-Gateway, einem dedizierten Testknoten und den wenigen vorhandenen TRV-Aktoren, in einem halben bis ganzen Tag vor Ort. Die drei load-bearing Zahlen: (1) Dämpfung pro Geschoss in dB (bestätigt oder korrigiert die sekundär belegte \~10-dB/Etage-Annahme und die Dichte-Regel 'A: \~1 GW pro 2-3 Etagen'); (2) gebäudespezifische Fade-Margin / Funkreserve am ungünstigsten Heizkörper bei SF12 (= Antwort auf Fragenkatalog F7, Entscheidung 1-vs-2-Gateways, F8); (3) gemessene Low-E-Glas-Dämpfung in dB (der einzige als 'low confidence, non-LoRa' markierte Modellparameter — der wissenschaftlich wertvollste Einzelwert der Kampagne). Alles, was keine dieser drei Zahlen oder die Gateway-Anzahl-Entscheidung bewegt, wird weggelassen (KISS).]

= Aufbau (Hardware & Software)
HARDWARE — Gateway: Kerlink Wirnet iFemtoCell Evolution, reale EUI 7076FF00… (Geräte-Label), 3-dBi-Stab-Standardantenne senkrecht. SF12-Empfindlichkeit fest auf -140 dBm angesetzt (Datenblatt, EINE Referenz für alle Schwellen — nicht mit der generischen SX1302-Zahl -137 dBm mischen). Strom + Backhaul über den EINEN bewährten Pfad aus ADR-0018: USB-C-RNDIS an einen netzgespeisten Windows-Laptop, der den vorhandenen Docker-Stack fährt; das USB-C-Datenkabel liefert Strom UND Backhaul über ein Kabel. KEIN ungetesteter LTE-/Powerbank-/öffentliche-IP-Pfad drei Wochen vor dem Termin. Steckdose am Gateway-Standort eine Woche vorher mit der Gebäudeleitung abklären; Verlängerung + Steckdosenleiste mitnehmen, ersatzweise 20.000-mAh-Powerbank für den Laptop. Messknoten (load-bearing): EIN dedizierter, konfigurierbarer Testknoten — Dragino LHT52 (\~21 €, in der Bring-up-Doku genannt) oder ein RAK/RP2040-Board — ADR AUS im Device-Profil, feste TX-Power 14 dBm, festes SF, Sendeintervall 30-60 s bzw. duty-cycle-konform (siehe test\_matrix). Die wenigen TRV-Aktoren (MClimate Vicki / Milesight WT101, \~10-min-Uplink, ADR-gelockt) NUR als unbeaufsichtigter Soak-Monitor an 2-3 festen Worst-Case-Punkten, NIE als Walk-Survey-Instrument. SOFTWARE — vorhandener whz-lora-Stack (ChirpStack v4, Gateway Bridge UDP, Mosquitto, PostgreSQL, Redis) per \`docker compose up -d --wait\`. scripts/smoke\_test.py als Vorab-Verifikation. Ein neues, \~60-zeiliges scripts/field\_logger.py, abgeleitet vom MQTT-Muster in smoke\_test.py (paho-mqtt CallbackAPIVersion.VERSION2, on\_subscribe-Gate, .env-Credentials MQTT\_TEST\_USERNAME/PASSWORD), das \`application/\<app\_id\>/device/+/event/up\` subskribiert und je Frame eine CSV-Zeile anhängt. Zwei Windows-Firewall-Regeln (UDP 1700 + ICMPv4, -Profile Any) aus ADR-0018 als Enabled bestätigt. Grundriss als PDF/Foto vorab beschafft, Messpunkte nummeriert. ZUGANG — Gebäudezugang, Schlüssel, ggf. PPE (Helm/Warnweste bei laufender Baustelle) und Sicherheitsunterweisung eine Woche vorher klären — der häufigste Grund für Testabbruch.

= ChirpStack startklar machen
+ VORTAG (Schreibtisch-Generalprobe, \~1-2 h): \`docker compose up -d --wait\` ausführen, dann \`py -3.12 scripts/smoke\_test.py\` — muss grün sein (gRPC, MQTT, UDP-Bridge, MQTT-Auth bestätigt). Dies eliminiert die Klasse 'stiller Stack' vor dem Feldtermin.
+ Reales Kerlink-Gateway in ChirpStack registrieren — mit der TATSÄCHLICHEN EUI vom Geräte-Label (7076FF00…) und stats\_interval=30 (muss exakt dem lorafwd-Default entsprechen, sonst meldet die UI fälschlich 'offline' trotz ankommender Frames). Schnellster Weg: gRPC-Einzeiler aus der Bring-up-Doku (Option B). WICHTIG: Smoke-Test-Gateway (EUI aabbccdd…) und Real-Gateway sind ZWEI getrennte Einträge; das Real-GW legt der Smoke-Test NICHT an.
+ Device-Profil 'WHZ-Feldtest-EU868' anlegen: Region EU868, LoRaWAN 1.0.x, ADR-Algorithmus auf 'Disabled' (ADR AUS — die einzige nicht-verhandelbare Einstellung; ohne sie regelt ChirpStack den SF selbst und jede RSSI/PDR-Messung ist unvergleichbar und F7 nie gemessen). DR fixieren (DR0=SF12 bzw. DR3=SF9 je Phase). Testknoten per OTAA mit gedruckten Keys (DevEUI/AppEUI/AppKey) in derselben Application registrieren; TRV-Aktoren ebenso.
+ Join bestätigen — am Schreibtisch im selben Gebäude wie der Stack: Testknoten und TRVs müssen im Event-Log 'join' und 'Last seen' zeigen, BEVOR der Feldtermin startet. Falscher AppKey loggt still 'MIC invalid' — das hier abfangen, nicht erst im Neubau.
+ Firewall prüfen: \`Get-NetFirewallRule -DisplayName 'whz-lora\*' | Select DisplayName, Enabled\` → beide Regeln Enabled True. Laptop-Energieoptionen auf 'Nie' (Standby) für Netzbetrieb; Docker Desktop läuft.
+ app\_id der Test-Application aus der UI oder per gRPC (wie in smoke\_test.py) auflösen und in field\_logger.py eintragen — mit Platzhalter subskribiert man das falsche Topic und empfängt nichts.
+ VOR ORT: Gateway am fixen Standort montieren (zentral, Treppenhaus-/Flurmitte des Mittelgeschosses, Antennenhöhe ≥2 m, ≥1 m Abstand zu Metallschränken/Aufzugsschacht/Klimakanal, NICHT hinter Low-E-Fassade). Position für die GESAMTE Kampagne einfrieren (eingefrorene Geometrie = Reproduzierbarkeit).
+ field\_logger.py starten (schreibt persistente CSV — NICHT den flüchtigen UI-Frame-Log als Primärquelle nutzen, der geht beim Seiten-Refresh verloren). Zweites Terminal: \`docker compose logs chirpstack-gateway-bridge -f\` offen lassen, um ankommende Stats-Frames (alle 30 s) und 'publishing event event=up' live zu sehen — die einzige schnelle Vor-Ort-Kontrolle, ob das Gateway sendet.
+ Referenzpunkt (Baseline) zuerst messen: Testknoten in Sichtlinie 5-10 m vom Gateway, gleiche Etage. Erwartung RSSI -60…-80 dBm, PDR 100 %. Beweist, dass Setup/Knoten/TX-Power funktionieren, BEVOR man irgendeinem 'schlechten' Messwert traut. Diesen Punkt am Ende jeder Session wiederholen (Drift-Check).

= Test-Matrix
Zwei Phasen an EINEM Tag, \~6-8 Punkte gesamt, ein Testknoten, ADR AUS. Die Punktwahl ist KEINE Raumkartierung, sondern eine De-Confounding-Leiter, die jeden der drei Modell-Werte isoliert.

PHASE 1 — Coverage-Screen bei festem SF9 (DR3), Vormittag. Intervall 20 s (SF9 ToA \~144 ms; 1%-Duty-Cycle-Minimum 14,4 s, +40 % Puffer = 20 s). N = 20 Pakete/Punkt → \~7 min reine Messzeit/Punkt + \~10 min Wegezeit. Punkte:

• P0 Baseline: LOS 5-10 m, gleiche Etage (Setup-Sanity, zuerst + zuletzt).

• Vertikale Säule (isoliert die dB/Etage): je 1 Punkt im DESELBEN Treppenhaus-Fußabdruck pro Etage über ≥3 Etagen — ΔRSSI/Etage = reine Geschossdämpfung, da horizontale Distanz und Wandzahl konstant gehalten.

• Horizontaler Lauf (isoliert dB/Wand + Distanz): 1-2 Punkte auf EINER Etage (0 Decken) Richtung entferntester Raumwinkel.

• Low-E-Paar (isoliert die Glas-Dämpfung): P\_innen = Knoten an der Innenseite der Low-E-Scheibe; P\_raum = \~3-5 m raumeinwärts, gleiche Etage, gleiches SF, GW fix. ΔRSSI(P\_innen − P\_raum) ist die gemessene Low-E-Dämpfung.

PHASE 2 — Worst-Case-Reserve bei festem SF12 (DR0), Mittag/Nachmittag. NUR an den 2-3 ungünstigsten Punkten aus Phase 1 (entfernteste Ecke höchstes/tiefstes Geschoss). Intervall ≥120 s/Kanal (SF12 ToA \~1,15 s; 1%-Duty-Cycle = 1 Paket/\~2 min/Kanal) ODER Mehrkanal-Rotation (8 Kanäle) für \~30 s effektiv. N = 20 Pakete/Punkt. VOR dem Vertrauen in PDR im Gateway-Bridge-Log prüfen, dass Frames akzeptiert und NICHT duty-cycle-gewarnt werden — sonst werden Protokollpausen als Funkverlust fehlinterpretiert.

SF-STRATEGIE: EIN festes SF pro Phase (SF9 Walk, SF12 Worst-Case). Wenn SF7 an einem Punkt PDR ≥95 % liefert, sind \~14 dB Reserve gegenüber SF12 da → Punkt sicher abgedeckt ohne SF12-Test. KEIN voller Sweep SF7/8/9/10/11/12, KEIN zweiter ADR-AN-Durchlauf (beides liefert keinen Modell-Input).

UNBEAUFSICHTIGT (parallel/über Nacht, ohne Personalbindung): TRV-Aktoren an 2-3 festen Worst-Case-Punkten ablegen — ihr realer \~10-min-Takt liefert einen Langzeit-PDR-Plausibilitätscheck unter echten Betriebsbedingungen.

WIEDERHOLUNG: einmalige Hauptmessung; eine Wiederholung 1 Woche später NUR, falls ein kritischer Punkt im Graubereich PDR 70-85 % landet.

= Metriken
#table(
  columns: (auto, 1fr, 1fr, 0.9fr), stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Metrik"), th("Was"), th("Wie erfasst"), th("Schwelle / Erwartung")),
  [RSSI\_median], [Empfangssignalstärke (dBm) am Messpunkt, Median über N Pakete — die Kerngröße für die Pfadverlust-Kalibrierung und alle Schwellen.], [rxInfo\[0\].rssi aus jedem Uplink-JSON, von field\_logger.py je Punkt in CSV; Median aus N≈20 Werten gebildet (Einzelwert wertlos: indoor σ 7-8 dB).], [Worst-Case-Punkt bei SF12: RSSI\_median \> -112 dBm (= -140 dBm Kerlink-Empfindlichkeit + \~28 dB; bzw. konservativ -114 dBm) ⇒ ausreichende Reserve, ein Gateway genügt wahrscheinlich. Deutlich darunter (\< -130 dBm) ⇒ kritisch, zweites Gateway prüfen (F8).],
  [SNR\_median], [Signal-Rausch-Abstand (dB), Median über N Pakete; zeigt Nähe zur Demodulationsgrenze und unterscheidet Pegel- von Interferenzlimitierung.], [rxInfo\[0\].snr je Uplink in CSV. Frames, deren SNR exakt auf dem -20-dB-Raster sitzen (SF12-Demod-Floor des SX1302), als 'gesättigt / Marge unbekannt' kennzeichnen und aus Margen-Aussagen ausschließen.], [SF12: SNR\_median \> -10 dB komfortabel; -15…-20 dB Grenzzone; gesättigt bei -20 dB = Link am Limit, wahre Marge unbekannt.],
  [delta\_dB\_pro\_Etage], [Gemessene Geschossdämpfung in dB/Etage — der erste der drei Modell-Werte; bestätigt oder korrigiert die sekundär belegte \~10-dB/Etage-Annahme aus model.md §7 und die Dichte-Regel Archetyp A.], [Aus der vertikalen Säule (gleicher Treppenhaus-Fußabdruck): (RSSI\_median\[Referenzetage\] − RSSI\_median\[N Etagen entfernt\]) / N. Horizontale Distanz und Wandzahl konstant gehalten, damit der Geschoss-Anteil isoliert ist.], [Erwartungswert 8-12 dB/Etage (Literatur \~10 dB). Liefert keine Pass/Fail-Grenze, sondern den Kalibrierwert für model.md §7. Abweichung \>±3 dB von 10 dB im Bericht hervorheben.],
  [delta\_dB\_Low\_E], [Gemessene Low-E-Glas-Dämpfung in dB — der zweite Modell-Wert und der einzige bisher als 'low confidence, non-LoRa' (35-60 dB) markierte Parameter; höchster wissenschaftlicher Mehrwert der Kampagne.], [RSSI\_median(Knoten an Innenseite Low-E-Scheibe) − RSSI\_median(Knoten \~3-5 m raumeinwärts), gleiches SF, Gateway fix. Das eine Delta ersetzt die größte Modell-Unsicherheit.], [Kein Pass/Fail; Messwert mit Streuung berichten. Im Rohbau evtl. unterschätzt, falls Verglasung/Dampfsperre noch nicht final verbaut — Bauzustand protokollieren und Kalibrierung entsprechend caveaten.],
  [PDR], [Packet Delivery Rate (%) je Punkt — der dritte, betriebsentscheidende Wert; beantwortet F7 (reicht SF12?) und die Go/No-Go-Entscheidung 1-vs-2-Gateways.], [PDR = empfangene Frames / gesendete Frames. Gesendet = fCnt-Differenz (Ende − Start) am Knoten. Empfangen = Anzahl CSV-Zeilen gleicher devEUI im Zeitfenster. NUR Unconfirmed Uplinks (Confirmed zählt Retransmits). Join-/Rejoin-Events mitloggen und als fCnt-Reset-Marker ausschließen (sonst Scheinverlust 100 %).], [PDR ≥ 80 % am Worst-Case-Punkt bei SF12 ⇒ 'reicht' (Heizungssteuerung, träge Regelstrecke, \~10-min-Takt). \< 50 % ⇒ Abdeckungslücke, zweites Gateway erforderlich (F8). Screening-Go/No-Go — keine Konfidenzintervalle nötig.],
)

= Ablauf (Schritt für Schritt)
+ 1. Vortag: Generalprobe am Schreibtisch — smoke\_test.py grün, Real-Gateway mit echter EUI + stats\_interval=30 registriert, Device-Profil ADR=Disabled, Testknoten + TRVs joinen, Firewall Enabled, app\_id in field\_logger.py eingetragen. Hard Go/No-Go: ohne grünen Stack + bestätigten Join NICHT zum Gebäude fahren.
+ 2. Vor Ort: Gateway am fixen, zentralen Standort montieren (Antenne ≥2 m, senkrecht, weg von Metall/Low-E-Fassade) und für die gesamte Kampagne einfrieren. Laptop per USB-C-RNDIS verbinden, an Steckdose/Powerbank. field\_logger.py starten, Gateway-Bridge-Log in zweitem Terminal mitlaufen lassen.
+ 3. Baseline P0 messen: Knoten LOS 5-10 m, SF9, 20 Pakete. Erwartung RSSI -60…-80 dBm, PDR 100 %. Stimmt das nicht ⇒ Setup-Fehler beheben, bevor weitergemessen wird.
+ 4. Phase 1 (SF9, 20 s, N=20) — vertikale Säule abgehen: je 1 Punkt im selben Treppenhaus-Fußabdruck pro Etage über ≥3 Etagen. Pro Punkt: Marker-Uplink mit Punkt-ID-Byte senden, pos\_id in field\_logger.py setzen, 20 Pakete abwarten, Punktblatt ausfüllen (Etage, Raum, h-Distanz grob, Wandzahl, Türzustand alle geschlossen, Foto).
+ 5. Phase 1 fortsetzen — horizontaler Lauf auf EINER Etage (0 Decken) Richtung entferntester Raumwinkel: 1-2 Punkte, gleiche Erfassung. Damit ist der Wand-/Distanz-Anteil vom Geschoss-Anteil getrennt.
+ 6. Phase 1 abschließen — Low-E-Paar messen: P\_innen direkt an der Innenseite der Low-E-Scheibe, dann P\_raum \~3-5 m raumeinwärts, gleiches SF, je 20 Pakete. Dies ist der höchstwertige Datenpunkt — bewusst und sorgfältig erfassen, nicht zwischen Korridorpunkten verlieren.
+ 7. Baseline P0 wiederholen (Drift-Check). Kurze Pause; field\_logger.py weiterlaufen lassen.
+ 8. Phase 2 (SF12, Intervall ≥120 s/Kanal bzw. Kanalrotation, N=20) — NUR die 2-3 ungünstigsten Punkte aus Phase 1. VOR dem Vertrauen in PDR im Gateway-Bridge-Log prüfen: Frames akzeptiert, keine Duty-Cycle-Warnung. RSSI\_median, SNR\_median (Sättigung markieren), PDR je Punkt erfassen.
+ 9. Unbeaufsichtigt: TRV-Aktoren an 2-3 festen Worst-Case-Punkten ablegen (über Mittag/Nacht) für einen Langzeit-PDR-Plausibilitätscheck im realen \~10-min-Takt.
+ 10. Vor Verlassen: CSV sichern (in docs/developer/analysis/ ablegen), Grundriss-Foto mit eingezeichneten Punkten dazu. Gateway-Position und Bauzustand (Low-E verbaut? metallbedampfte Dampfsperre sichtbar?) notieren.
+ 11. Auswertung (Folgetag, \~2 h): aus CSV je Punkt RSSI\_median/SNR\_median/PDR; delta\_dB\_pro\_Etage aus der vertikalen Säule; delta\_dB\_Low\_E aus dem Paar. Drei Modell-Werte mit Streuung + Bauzustand-Caveat berichten; Go/No-Go (1 vs 2 Gateways) gegen die Pass-Kriterien stellen; ADR im Device-Profil wieder auf Default zurücksetzen.

= Erfolgskriterien
- Setup verifiziert: Baseline-Punkt P0 liefert RSSI -60…-80 dBm und PDR 100 % — sonst sind alle 'schlechten' Messwerte nicht vertrauenswürdig (Setup- statt Funkproblem).
- ADR im Device-Profil bestätigt 'Disabled' und SF fest — ohne dies ist keine RSSI/PDR vergleichbar und F7 nie gemessen (die nicht-verhandelbare Bedingung).
- delta\_dB\_pro\_Etage als Zahl aus einer vertikalen Säule über ≥3 Etagen geliefert — bestätigt oder korrigiert die \~10-dB/Etage-Annahme und die Dichte-Regel Archetyp A in model.md §7.
- delta\_dB\_Low\_E als Zahl aus dem Innen-vs-Raum-Paar geliefert — der bisher ungemessene Modellparameter ist durch einen WHZ-spezifischen LoRa-Messwert ersetzt.
- F7 beantwortet: am ungünstigsten Heizkörper-nahen Punkt bei SF12 ist PDR ≥ 80 % UND RSSI\_median \> -112 dBm ⇒ ein Gateway genügt; andernfalls ist ein zweiter Gateway-Standort dokumentiert (F8).
- Reproduzierbarkeit gesichert: persistente CSV (timestamp\_utc, dev\_eui, pos\_id, rssi\_dbm, snr\_db, sf, freq\_hz, f\_cnt, gw\_eui) + Punktblatt + Grundriss-Foto in docs/developer/analysis/ abgelegt; Gateway-Position eingefroren und protokolliert.
- Duty-Cycle-Disziplin nachgewiesen: Gateway-Bridge-Log zeigt akzeptierte Frames ohne Duty-Cycle-Warnung — PDR ist nicht durch Protokoll-Drosselung verfälscht.

= Stolperfallen
- TEST-KILLER: TRVs als Survey-Instrument. \~1 Uplink/10 min, ADR-gelockt, kein fCnt-Zugriff ⇒ 20 Pakete dauern \>3 h/Punkt und gute Punkte regeln sich auf SF7 herunter (F7 nie gemessen). Lösung: dedizierter Testknoten (30-60 s, ADR AUS, festes SF) für den Walk; TRVs nur als unbeaufsichtigter Soak. 'Knoten dabei + ADR disabled + Join bestätigt' ist Hard-Go/No-Go vor der Abfahrt.
- ADR vergessen zu deaktivieren — der häufigste Methodenfehler. ChirpStack regelt den SF selbst, Messung spiegelt Netz- statt Kanalverhalten, Modell-Kalibrierung unmöglich. ADR=Disabled + festes SF im Device-Profil VOR dem Test setzen, danach zurücksetzen.
- Duty-Cycle-Falle bei SF12: ToA \~1,15 s ⇒ 1%-Limit = 1 Paket/\~2 min/Kanal. Zu schnelles Senden wird gedrosselt/abgelehnt, die Lücken sehen wie Funkverlust aus und verfälschen genau die Fade-Margin-Zahl. Intervall aus ToA berechnen (≥120 s/Kanal oder 8-Kanal-Rotation) und im Bridge-Log Akzeptanz prüfen.
- Inkonsistente Empfindlichkeits-Referenz: -137 (generisch SX1302) vs -140/-141 (Kerlink-Datenblatt) ergibt eine 3-4-dB-Mehrdeutigkeit in der Pass/Fail-Regel. EINE Zahl für DIESES Gateway pinnen (-140 dBm) und alle Schwellen konsistent daraus ableiten. Die 25,7-dB-Fade-Margin ist hier eine HYPOTHESE, die der Test neu misst, kein Konstante.
- Backhaul/Strom im leeren Neubau: keine 230-V-Steckdose, kein LAN. Den bewährten ADR-0018-Pfad verbatim nutzen (Gateway per USB-C-RNDIS an netzgespeisten Laptop = Strom + Backhaul über ein Kabel). KEINEN neuen LTE-/öffentliche-IP-Pfad drei Wochen vorher aufsetzen. Steckdose eine Woche vorher mit Gebäudeleitung sichern.
- Flüchtiger UI-Frame-Log: verschwindet beim Seiten-Refresh, Frames tragen kein Raum-Label. Primärquelle ist die persistente CSV von field\_logger.py; je Punkt Marker-Uplink + pos\_id live setzen, sonst sind die Daten nicht auf Räume joinbar.
- Worst-Case-Punkt konfundiert N Etagen + Distanz + Wände + Türen gleichzeitig ⇒ keine Rückrechnung auf dB/Etage. Erst die De-Confounding-Leiter (vertikale Säule + horizontaler Lauf), dann der kombinierte Worst-Case. Sonst entsteht ein Coverage-Urteil statt der dB-Koeffizienten.
- fehlende absolute Referenz: ohne LOS-Baseline ist absolutes RSSI für die Pfadverlust-Fit bedeutungslos (unbekannter Gateway-Chain-Offset, unverifizierte Knoten-EIRP). Baseline-Punkt zuerst UND zuletzt jeder Session messen.
- Bauzustand verfälscht Kalibrierung: ein Rohbau (Low-E-Glas / metallbedampfte Dampfsperre noch nicht final) UNTERschätzt die Dämpfung des fertigen Gebäudes. Welche RF-relevanten Schichten bereits verbaut sind protokollieren und die Kalibrierung caveaten.
- Geltungsbereich nicht überdehnen: ein Gebäude/eine Gateway-Position kalibriert NUR Archetyp A (hostile, Low-E), nicht D (RC institutional, der wahrscheinliche WHZ-Fall). Als EIN empirischer Anker berichten; D bleibt ungemessen. Eine einzige GW-Positionsvariation (Treppenhaus Mitte vs Rand) gibt nebenbei einen billigen Check der Dichte-Regel.
- Türzustand/Personen unkontrolliert: offene vs geschlossene Stahl-Brandschutztür = 10-15 dB, Personenverkehr 3-5 dB Body-Shadowing. Türen standardisiert geschlossen halten, Tageszeit-Block fixieren, Personen protokollieren — sonst streuen Messwerte über den echten Effekt hinaus.
- WEGGELASSEN als Over-Engineering (bewusst NICHT im Verfahren): σ(SNR)\<3 dB / σ(RSSI)\<6 dB Stabilitätsgates, Burst-Loss-/fCnt-Run-Analyse, SNR-Sättigungs-Statistik als Gate, Clopper-Pearson/Wilson-Konfidenzintervalle, zweiter ADR-AN-Durchlauf, voller 6-Stufen-SF-Sweep, 20-23 Messpunkte (5/Etage), Laser-Entfernungsmesser/MagicPlan, 1,5-vs-2,5-m-Höhen-A/B, Hochgewinn-Antennen-Analyse, RAK10701-Field-Tester. Keiner dieser Punkte bewegt einen der drei Modell-Werte oder die Gateway-Anzahl.

#page(flipped: true)[
= Messwert-Tabelle (zum Ausfüllen vor Ort)
Pro Messpunkt nur die Kontext-Angaben hier eintragen. *RSSI, SNR, SF, Frequenz, fCnt und PDR* loggt `field_logger.py` je `pos_id` automatisch in die CSV (Spalten: `timestamp_utc, dev_eui, pos_id, rssi_dbm, snr_db, sf, freq_hz, f_cnt, gw_eui`). Punkt-Typ: `BASELINE` · `VERTIKALE_SAEULE` · `HORIZONTAL` · `LOW_E_INNEN` · `LOW_E_RAUM` · `WORST_CASE`.
#v(4pt)
#table(
  columns: (auto, auto, auto, 1fr, 1.2fr, auto, auto, auto, auto, 1.4fr),
  stroke: 0.5pt + rulec, inset: 5pt,
  table.header(th("POS_ID"), th("Phase"), th("Etage"), th("Raum / Lage"), th("Punkt-Typ"), th("SF"), th("Decken→GW"), th("Wände"), th("Uhrzeit"), th("Bemerkung (Bauzustand)")),
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
  [#v(12pt)], [], [], [], [], [], [], [], [], [],
)
]
