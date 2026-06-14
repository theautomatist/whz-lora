#import "report-template.typ": *
#show: report.with(
  title: "Fragenkatalog — Gebäudespezifische Kostenkalkulation",
  subtitle: "LoRaWAN-Einzelraumregelung · Erhebungsbogen für ein konkretes Gebäude",
  meta: "Projekt whz-lora · WHZ · 2026-06-14 · abgeleitet aus Report A + B · je vollständiger die Antworten, desto belastbarer das Wirtschaftlichkeits-Urteil",
)

#let q(nr, frage, typ, onsite: false) = block(breakable: false, below: 7pt, width: 100%)[
  #text(weight: "bold")[#nr]#if onsite [#text(fill: warn)[ ✎]]  #frage \
  #text(8pt, fill: muted, style: "italic")[#typ] \
  #box(width: 72%, height: 11pt, stroke: (bottom: 0.4pt + rulec))
]

#callout(title: "Ausfüllhinweis", color: accent)[
  Bitte je Frage die Antwort eintragen. Der kursive Hinweis nennt den Antworttyp bzw. die
  Auswahlmöglichkeiten. Ein *#text(fill: warn)[✎]* markiert Angaben, die nur vor Ort (bei
  einer Begehung/Messung) verlässlich feststellbar sind — alle übrigen lassen sich am
  Schreibtisch beantworten.
]

= A — Gebäude & Konstruktion

#q("A1", [In welcher *Bauepoche* wurde das Gebäude errichtet?], [Auswahl: vor 1949 · 1949–1957 · 1958–1990 (DDR/Plattenbau) · 1991–2001 · 2002 bis heute (GEG/EnEV) · unbekannt])
#q("A2", [Aus welchem *Hauptmaterial* besteht die tragende Außenwand?], [Auswahl: Vollziegel · Stahlbeton · Stahlbeton-Sandwich/Plattenbau (WBS 70) · Kalksandstein/Porenbeton · Holz · gemischt/unbekannt])
#q("A3", [Wurde nachträglich ein *Wärmedämm-Verbundsystem (WDVS)* an der Fassade angebracht?], [Ja/Nein])
#q("A4", [Welche *Verglasung* haben die Fenster überwiegend?], [Auswahl: Einfach Klarglas · Zweifach Isolier ohne Beschichtung · Zwei-/Dreifach Wärmeschutz (low-E, metallbeschichtet) · gemischt · unbekannt])
#q("A5", [Falls Plattenbau: Welche *Serie*?], [Auswahl: WBS 70 · P2/Q3A · andere DDR-Serie · kein Plattenbau · unbekannt])
#q("A6", [Liegt ein *Energieausweis* vor — welche Effizienzklasse bzw. welcher Endenergie-Kennwert (kWh/m²·a)?], [Text])
#q("A7", [Ist das Gebäude *einheitlich* gebaut, oder gibt es Anbauten/Aufstockungen aus anderer Epoche/anderem Material?], [Ja/Nein])
#q("A8", [Falls Baualter/Wandart unbekannt: Wie dick sind die Außenwände ungefähr (an der Fensterlaibung), und fühlt sich die Wand massiv-kalt (Ziegel/Beton) oder leicht/hohl (Trockenbau/Holz) an?], [Messung], onsite: true)
#q("A9", [Enthält das *Dämmmaterial* eine metallische Dampfsperre oder kaschierte Alu-Folie?], [Ja/Nein], onsite: true)

= B — Geometrie, Geschosse & Räume

#q("B1", [Wie viele oberirdische, beheizte *Vollgeschosse* hat das Gebäude?], [Zahl])
#q("B2", [Gibt es beheizte *Keller-/Dachgeschosse* mit Heizkörpern — wie viele?], [Zahl])
#q("B3", [Wie groß ist die *gesamte beheizte Fläche* (m²)?], [Zahl])
#q("B4", [Wie groß ist die beheizte *Fläche je Geschoss* (m², je Geschoss einzeln)?], [Zahl])
#q("B5", [Sind die Geschosse baulich *gleich* aufgebaut (gestapelte Standardetage)?], [Ja/Nein])
#q("B6", [Wie viele *beheizte Räume* gibt es insgesamt (Flure ausgenommen), und wie verteilen sie sich auf die Geschosse?], [Zahl + Verteilung])
#q("B7", [*Gesamtzahl der zu regelnden Heizkörper* im Gebäude?], [Zahl], onsite: true)
#q("B8", [Wie viele Heizkörper *je Raum*, und gibt es Räume mit 2 oder mehr (z. B. Säle, Hörsäle)?], [Zahl je Raum], onsite: true)
#q("B9", [Gibt es Heizkörper in *ausgeschlossenen Bereichen* (Flure, Treppenhaus, Sanitär, Nebenräume)?], [Ja/Nein], onsite: true)
#q("B10", [Wie viele getrennte *Treppenhäuser/Steigzonen* gibt es, und wo liegen sie (zentral / Außenwand / Rand)?], [Text])

= C — Heizung, Energie & Einsparung

#q("C1", [Womit wird das Gebäude *beheizt*?], [Auswahl: Erdgas · Fernwärme · Heizöl · Wärmepumpe · Pellets/Biomasse · Sonstiges])
#q("C2", [Realer *Arbeitspreis* in €/kWh laut Abrechnung (netto, ohne Grund-/Leistungspreis)?], [Zahl])
#q("C3", [Jährlicher *Heizenergieverbrauch* in kWh (nur Raumheizung, falls trennbar)?], [Zahl])
#q("C4", [Jährliche *Heizkosten* in € laut letzter Abrechnung?], [Zahl])
#q("C5", [Enthält die Abrechnung *Warmwasser*, und ist der Raumheizungsanteil getrennt ausgewiesen?], [Auswahl: nur Raumheizung · Heizung+WW getrennt · Heizung+WW nicht getrennt · unbekannt])
#q("C6", [Wurde bereits ein *hydraulischer Abgleich* durchgeführt (falls ja: wann/welches Verfahren)?], [Auswahl: Ja Verfahren B · Ja Verfahren A · Ja unbekannt · Nein · unbekannt])
#q("C7", [Gibt es Hinweise auf *hydraulische Schieflage* (kalte/überheizte Heizkörper, Ventilgeräusche)?], [Ja/Nein], onsite: true)
#q("C8", [Wie werden die Räume *genutzt*?], [Auswahl: durchgehend (Wohnen) · werktags tagsüber (Büro) · zeitweise/Belegungsplan · stark unregelmäßig/leerstehend · gemischt])
#q("C9", [Wie wird *heute geregelt*?], [Auswahl: nur manuelle Thermostatköpfe · zentrale Nachtabsenkung · einzelne Zeitschaltuhren · teilweise Smart · keine aktive Regelung])
#q("C10", [Welche *Soll-/Absenktemperatur* ist vorgesehen, und ist Absenkung bei Abwesenheit gewünscht/zulässig?], [Text])
#q("C11", [Gibt es Räume mit dauerhaft *abweichendem Heizbedarf* (Server, Archive, Lager), die ausgenommen werden sollen?], [Text], onsite: true)
#q("C12", [Wie alt ist die Heizungsanlage, und steht in 10 Jahren ein *Austausch/Energieträger-Wechsel* an?], [Text])
#q("C13", [Zahlt der *Betreiber* die Heizkosten selbst, oder werden sie auf Mieter umgelegt?], [Auswahl: Betreiber zahlt selbst · volle Umlage · teilweise Umlage · unbekannt])

= D — Ventile & Montagebedingungen

#q("D1", [Welcher *Heizkörpertyp* überwiegt?], [Auswahl: Plattenheizkörper · Röhren-Glieder (Altbau) · Konvektor · Handtuch-Bad · gemischt], onsite: true)
#q("D2", [Welcher *Ventilanschluss* (Gewindemaß) und -hersteller?], [Auswahl: M30×1,5 Standard · M28×1,5 (Herz/Comap) · Danfoss RA · Danfoss RAVL/RAV · gemischt/unbekannt · Sonstiges], onsite: true)
#q("D3", [Sind die Ventile *gangbar* oder festsitzend/verkalkt (Stichprobe)?], [Auswahl: überwiegend gangbar · teilweise festsitzend · überwiegend festsitzend · nicht geprüft], onsite: true)
#q("D4", [Sind bereits *elektronische/funkbasierte Thermostate* verbaut (z. B. Homematic)?], [Ja/Nein], onsite: true)
#q("D5", [Wie viele Heizkörper sind hinter *Verkleidungen/Nischen/Möbeln* schwer zugänglich?], [Zahl], onsite: true)
#q("D6", [Sind die Wände an den Ventilstandorten *verputzt/zugänglich*, oder Rohbau/Sanierung?], [Ja/Nein], onsite: true)

= E — Infrastruktur, Zugang & Logistik

#q("E1", [Ist bereits ein *LoRaWAN-Gateway* installiert/in Betrieb — an welchem Standort (Geschoss/Raum)?], [Text · ✎ exakter Standort vor Ort])
#q("E2", [Gibt es am Gateway-Standort eine dauerhafte *230-V-Steckdose*, oder muss eine gelegt werden?], [Auswahl: vorhanden · muss gelegt werden · unklar], onsite: true)
#q("E3", [*Netzanbindung* des Gateways / LAN-Dose am Standort?], [Auswahl: LAN-Dose vorhanden · Kabel verlegen · WLAN · Mobilfunk geplant · keine Anbindung], onsite: true)
#q("E4", [Gibt es in Treppenhaus/Allgemeinbereichen *Strom + Netz in mehreren Geschossen* (für ein mögliches Zweit-Gateway)?], [Auswahl: ja in mehreren · nur einzelne · nein · unklar], onsite: true)
#q("E5", [Liegen aus dem Gateway-Bring-up bereits *Funk-Messdaten (RSSI/SNR)* vor?], [Ja/Nein])
#q("E6", [*Aufputz* akzeptabel oder *Unterputz* gewünscht (Gateway-Verkabelung)?], [Auswahl: Aufputz akzeptabel · Unterputz gewünscht · egal/offen])
#q("E7", [Gibt es *Denkmalschutz-/Eigentümer-/Mietauflagen*, die sichtbare Geräte oder Eingriffe einschränken?], [Ja/Nein])
#q("E8", [Wer regelt den *Zutritt*, in welchen Zeitfenstern ist Zugang möglich, welche Räume nur über Mieter-Terminierung?], [Text])
#q("E9", [Welcher *Anteil* der Heizkörper-Räume ist frei zugänglich vs. zutrittsgebunden?], [Zahl/%])
#q("E10", [Steht ein *abschließbarer Lager-/Stellplatz* für die Hardware während der Installationswellen zur Verfügung?], [Ja/Nein], onsite: true)
#q("E11", [Existiert auf dem WHZ-Host bereits ein laufender *ChirpStack-LNS* für dieses Gebäude, oder ist eine separate Instanz nötig?], [Ja/Nein])

= F — Funk & Abdeckung (Zweit-Gateway-Risiko)

#q("F1", [Aus welchem Material bestehen die *Geschossdecken*?], [Auswahl: Stahlbeton bewehrt · Beton unbewehrt · Holzbalken · Ziegel-Gewölbe · gemischt · unbekannt], onsite: true)
#q("F2", [*Durchgehende Decken* oder vertikale Funk-Bypässe?], [Auswahl: durchgehend · Treppenauge offen · Installationsschächte · offene Galerien · mehrere Durchbrüche], onsite: true)
#q("F3", [*Innenwände* massiv (Beton/Ziegel) oder leichte Trennwände?], [Auswahl: massiv · leicht · gemischt · unbekannt], onsite: true)
#q("F4", [*Metallische Großbauteile/Störquellen* auf der Funkstrecke (Aufzug, Metallwände, Blechfassade, metallbedampfte Dämmung, Klimakanäle, 868-MHz-Störer)?], [Auswahl: keine · Aufzugsschacht · Metallständerwände · Blechverkleidung · metallbedampfte Dämmung · Klimakanäle · 868-MHz-Störer · mehrere], onsite: true)
#q("F5", [Wie viele *Stahl-Brandschutztüren* (T30/T90) liegen auf der Funkstrecke?], [Zahl], onsite: true)
#q("F6", [Wie viele Geschosse, welche *horizontale Distanz* (m) und wie viele Innenwände liegen zwischen Gateway und entferntestem Heizkörper?], [Messung], onsite: true)
#q("F7", [Reicht die *Funkreserve* am entferntesten Heizkörper auch im langsamsten Modus (SF12) noch aus (RSSI/SNR über −137 dBm + Fade-Margin)?], [Messung — der definitive Zweit-Gateway-Test], onsite: true)
#q("F8", [Falls nein: Gibt es einen geeigneten *Standort für ein zweites Gateway* (Strom, Netz, zentrale Lage)?], [Ja/Nein], onsite: true)
#q("F9", [Ist das Gebäude in funktechnisch *getrennte Bauteile/Flügel* gegliedert (durchgehende Brandwände)?], [Auswahl: ein Baukörper · zwei Flügel · drei oder mehr · unbekannt])

#v(4pt)
#callout(color: warn)[
  Die mit *#text(fill: warn)[✎]* markierten Punkte — vor allem *F6* (Worst-Case-Pfad ausmessen)
  und *F7* (SF12-Reservemessung am entferntesten Heizkörper) — sind der *definitive
  Zweit-Gateway-Test* und nur mit einem Test-Node vor Ort feststellbar. Sie bilden den
  Messplan, der die verbleibende Unsicherheit der Kalkulation schließt.
]
