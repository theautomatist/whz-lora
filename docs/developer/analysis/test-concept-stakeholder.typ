#import "report-template.typ": *
#show: report.with(
  title: "Funk-Voruntersuchung vor dem Sensornetz",
  subtitle: "Warum wir an der WHZ erst messen und dann installieren — und was das dem Gebäude bringt",
  meta: "Projekt whz-lora · WHZ · 2026-06-23 · nicht-technische Zusammenfassung für Eigentümer & Leitung · Begleitpapier zum technischen Testkonzept",
)

#callout(title: "Das Wichtigste in Kürze", color: accent)[
  Wir planen an der WHZ ein eigenes Funknetz, über das später Sensoren und Heizungs-Ventile
  *kabellos* kleine Datenmengen melden. Bevor wir Geräte fest einbauen, führen wir eine kurze
  *Funk-Voruntersuchung* durch — einen Mess-Durchgang durchs Gebäude. Er prüft zweierlei:
  *kommt unser Signal überall sicher an?* und *funkt uns ein fremdes Netz dazwischen?*
  Der Test kostet wenig (Größenordnung ein Begehungstag) und braucht *keine* baulichen
  Eingriffe — wir hören nur zu und messen. Sein Ergebnis ist eine belastbare
  Entscheidungsgrundlage: Reicht ein zentraler Funk-Knoten, oder braucht es einen zweiten?
  Kurz: ein kleiner Vorab-Aufwand kauft die Sicherheit, *nach* der Installation keine bösen
  Überraschungen zu erleben.
]

= Warum dieser Test?

Funk im Gebäude ist nicht selbstverständlich. Wände, Decken und besonders moderne Fenster
schlucken das Signal unterschiedlich stark — und niemand kann das von außen sicher
vorhersagen. Beim WHZ-Neubau kommt hinzu, dass energiesparende Fenster (mit hauchdünner
Metallbeschichtung) und gedämmte Außenwände Funk besonders abschirmen können. *Wie stark
genau*, weiß man erst, wenn man es misst.

Statt zu raten und zu hoffen, drehen wir die Reihenfolge um: *erst messen, dann planen.*
Genau die Unsicherheit über Wände, Etagen und Fenster ist der Grund für den Test — und der
Test löst sie auf. Ein zweiter Grund: Wir teilen uns die Funkfrequenz mit jedem anderen, der
in der Umgebung dieselbe Technik nutzt. Wir wollen früh wissen, ob da schon „jemand spricht".

#plain[Stellen Sie sich das Funkloch vor wie beim Handy im Keller oder Aufzug: „kein Netz". Der Test findet solche Stellen *vorab* — bevor dort ein Gerät verbaut ist.]

= Was wir genau messen

Der Test beantwortet zwei einfache Fragen — eine zur eigenen Reichweite, eine zur Umgebung.

#figure(
  image("assets/stakeholder-uebersicht.svg", width: 100%),
  caption: [Links: Kommt unser Signal an jeder geplanten Stelle an? Wir kartieren das Gebäude in Grün/Gelb/Rot. Rechts: Wie viel fremder Funk-Betrieb herrscht schon auf unserem Kanal? (Schematische Darstellung.)],
)

== Frage 1 — Kommt unser Signal überall an?

Dazu verteilen wir die real vorhandene Technik im Gebäude: *einen* Funk-Knoten (das Gateway)
und drei Test-Thermostate. Wir halten genau fest, *wo* jedes Gerät steht und *was* an Wänden
und Decken dazwischenliegt, und prüfen an jeder geplanten Stelle, wie kräftig das Signal noch
ankommt. Dabei rechnen wir bewusst mit dem *ungünstigsten Fall* (schwächste Stelle, dickste
Wand, oberste/unterste Etage) — wenn es dort funktioniert, funktioniert es überall. Das
Ergebnis ist eine Landkarte des Gebäudes: *grün* = sicherer Empfang, *gelb/rot* = kritisch.

#plain[Jede Wand legt einen „Vorhang" über das Signal — eine Gipswand ist ein dünner Vorhang, eine Stahlbetondecke ein dicker, ein metallbeschichtetes Fenster fast ein zugezogener Rollladen.]

Damit der Test die Wirklichkeit trifft, befestigen wir die Test-Thermostate so, wie sie später
am Heizkörper sitzen — gleiche Ausrichtung und Höhe, notfalls mit einer kleinen 3D-gedruckten
Halterung. Sonst wäre das Ergebnis zu schöngerechnet: Am echten Heizkörper dämpft das Metall
das Funksignal zusätzlich, und das bilden wir bewusst mit ab.

== Frage 2 — Funkt uns jemand dazwischen?

Wir hören einige Minuten lang *passiv* mit — wir senden dabei selbst nichts — ob fremde
Funknetze im Gebäude oder der Nachbarschaft auf denselben Frequenzen aktiv sind und wie viel
„Betrieb" dort herrscht. Wichtig und ehrlich: Wir erkennen dabei nur, *dass* ein fremdes
Gerät funkt und *wie stark/häufig* — niemals *was* es überträgt. Fremde Inhalte sind
verschlüsselt und bleiben es. Das ist kein Abhören, sondern ein Zählen von Funkverkehr.

= Der besondere Mehrwert: fremde Funknetze früh erkennen

Unsere Funktechnik teilt sich ein *offenes* Frequenzband mit anderen — vom Heizungszähler des
Nachbarn bis zu städtischen Sensornetzen. Niemand „besitzt" diesen Kanal; alle dürfen ihn
nutzen. Unser eigener Funk-Knoten kann technikbedingt jedes fremde Signal auf diesen
Frequenzen mithören (wieder: nur als Funkverkehr, nicht inhaltlich). Das nutzen wir für eine
ehrliche Bestandsaufnahme *vor* der Installation.

Der konkrete Nutzen: Wir erkennen früh, ob andere Funknetze im Haus uns später stören
könnten — und können gegensteuern, *bevor* Geräte verbaut sind, statt teuer nachzurüsten. Und
es ist eine Absicherung für beide Seiten: Sollte es nach der Installation einmal Ausfälle
geben, haben wir ein dokumentiertes „So war die Funklage vorher" — das trennt
Gebäude-Ursachen von Geräte-Ursachen von fremder Störung.

#plain[Auf unserer Frequenz reden alle ohne Reihenfolge durcheinander — es gibt keinen „Moderator". Solange wenige sprechen, versteht man sich gut; wird es voll, gehen einzelne Sätze unter. Der Test misst, *wie laut der Raum schon ist*.]

= Was das Ergebnis für Ihre Entscheidung bedeutet

Das Ergebnis ist keine Ja/Nein-Black-Box, sondern liefert die *Begründung* für jede
Folge-Investition. Ein zweiter Funk-Knoten wird nur dann empfohlen, wenn die Messung ihn
rechtfertigt — nicht auf Verdacht.

#table(
  columns: (auto, 1.3fr, 1.4fr),
  stroke: 0.5pt + rulec, inset: 7pt, align: left,
  table.header(th("Befund"), th("Was das heißt"), th("Empfehlung")),
  [#text(fill: good)[*Grün*] — Empfang gut, kaum Fremdverkehr], [Standard-Aufbau reicht], [Ein zentraler Funk-Knoten genügt; planmäßig installieren],
  [#text(fill: warn)[*Gelb*] — vereinzelt schwacher Empfang *oder* spürbarer Fremdverkehr], [Funktioniert, aber mit Reserve-Risiko], [Beobachten; ggf. zweiten Knoten als „Versicherung" einplanen],
  [#text(fill: bad)[*Rot*] — Funklöcher *oder* starker Fremdverkehr], [Ohne Maßnahme drohen Ausfälle], [Zweiter Funk-Knoten / andere Antenne / angepasste Planung — vor der Installation klären],
)

= Ehrlich gesagt: die Grenzen

- Wir versprechen *keine* 100-%-Zuverlässigkeit. Da wir uns die Frequenz mit anderen teilen,
  ist ein winziger Rest an Funk-„Zusammenstößen" physikalisch nie ganz auszuschließen —
  realistisch sind sehr hohe, aber keine perfekten Zustellraten.
- „Heute nichts gehört" heißt nicht „garantiert nie etwas da": Manche fremden Geräte senden
  nur sehr selten. Wir benennen das offen, statt eine Scheinsicherheit zu verkaufen.
- Genau deshalb *messen* wir, statt anzunehmen — und dokumentieren auch das, was wir *nicht*
  sicher wissen. Das ist die seriöse Grundlage für eine Hochschule, die Nachweise braucht.
- Erfahrungsgemäß ist die Funklage in solchen Umgebungen meist entspannt; kritische Störungen
  sind selten und treten nur bei sehr dichten Nachbarnetzen auf. Der Test bestätigt das — oder
  warnt rechtzeitig.

#plain[Das Mithören ist wie der Wetterbericht, nicht wie ein Lauschangriff: Wir sehen nur, *dass* und *wie kräftig* fremde Funksignale auftreten — wie man Regentropfen am Fenster zählt, ohne zu wissen, woher jeder einzelne kommt.]

= So gehen wir vor

+ *Vorab am Schreibtisch:* öffentliche Funk-Karten prüfen — ein kostenfreier Erst-Indikator,
  ob in der Umgebung schon Netze aktiv sind.
+ *Begehung:* Funk-Knoten an einen festen Platz stellen, die drei Thermostate über die geplanten
  Standorte verteilen, an jeder Stelle messen — und festhalten, *wo* die Geräte stehen und *was*
  an Wänden und Fenstern dazwischenliegt (mit Fotos je Etage). Dazu ein kurzer Mithör-Scan.
+ *Auswertung:* Empfangs-Landkarte plus Ampel-Bewertung der Fremdfunklage, kompakt in einem Bericht.
+ *Entscheidung:* gemeinsam festlegen, ob der Standard-Aufbau reicht oder eine Zusatzmaßnahme
  sinnvoll ist — auf Basis von *Messwerten*, nicht Vermutungen.

#callout(color: teal)[
  Die technischen Details — Messgrößen, Funkphysik, Schwellenwerte und das genaue Mess- und
  Auswerteverfahren — stehen im Begleitdokument *„Testkonzept — LoRaWAN-Funkabdeckung,
  -Stabilität & -Koexistenz"* (`test-concept.pdf`). Dieses Papier hier fasst nur das Warum und
  den Nutzen zusammen.
]
