#import "report-template.typ": *
#show: report.with(
  title: "Testkonzept — Kurzfassung",
  subtitle: "Das Wesentliche auf einer Seite · das ausführliche Konzept liegt als Anhang bei",
  meta: "Projekt whz-lora · WHZ · 2026-07-02 · Vorblatt zum ausführlichen Testkonzept (test-concept.pdf)",
)

// Vorblatt: keine Kapitelnummern, kompakt.
#set heading(numbering: none)

#callout(title: "Kernaussage", color: accent)[
  Bevor an der WHZ ein LoRaWAN-Funknetz für Sensorik und Heizungsventile fest installiert wird,
  prüft eine *eintägige Messkampagne mit minimalem Aufbau*, ob die Funktechnik im Gebäude trägt:
  *Kommt unser Signal überall an? Kommt der Steuerbefehl zurück? Funkt ein fremdes Netz dazwischen?*
  Ergebnis ist eine belastbare Entscheidungsgrundlage — ohne baulichen Eingriff, weil nur gemessen
  und zugehört wird.
]

= Die eine Leitfrage

*Reicht ein Gateway, um das gesamte Gebäude zu versorgen?* Das ist die Frage, die die Arbeit
trägt. Ihre Antwort hängt daran, wie stark die Geschossdecken und die metallbedampften
Energiespar-Fenster (Low-E) das Funksignal dämpfen — und *wie stark genau*, weiß man erst nach der
Messung, nicht aus der Literatur. Nebenfragen (Deckendämpfung je Etage, Glasdämpfung, Antennennutzen,
Fremdfunk-Last, Erreichbarkeit des Rückwegs) stützen diese eine Entscheidung.

= Vorgehen an einem Messtermin

- *Aufbau:* ein Gateway an festem Standort plus drei LoRaWAN-Heizkörper-Thermostate, an den
  geplanten Stellen im Gebäude verteilt.
- *Gemessen je Punkt:* Empfangsstärke und Zustellrate (kommt das Signal an?), Stabilität über die
  Zeit — dazu ein *passiver Scan* auf fremde Funknetze und ein kurzer *Rückweg-Test* (Downlink).
- *Dokumentiert:* wo jedes Gerät steht und was an Wänden und Decken dazwischenliegt — sonst ist ein
  schlechter Messwert später nicht deutbar.

= Ergebnis & Entscheidung

Aus den Messwerten entsteht eine *Ampel-Karte* des Gebäudes; daraus folgt die einzige Investitions-
Entscheidung, um die es hier geht — auf Basis von Messwerten, nicht Vermutung:

#table(
  columns: (auto, 1.5fr, 1.4fr),
  stroke: 0.5pt + rulec, inset: 6pt, align: left,
  table.header(th("Befund"), th("Bedeutung"), th("Entscheidung")),
  [#text(fill: good)[*Grün*]], [Empfang gut, kaum Fremdfunk], [ein zentrales Gateway genügt],
  [#text(fill: warn)[*Gelb*]], [vereinzelt schwach oder Fremdfunk spürbar], [beobachten; zweites Gateway als Reserve prüfen],
  [#text(fill: bad)[*Rot*]], [Funkloch oder starke Störung], [zweites Gateway / andere Antenne — vor der Installation klären],
)

= Bewusst ausgeklammert

Kapazität bei sehr vielen Geräten, andere Gebäudetypen und Langzeit-/Saisoneffekte prüft dieser
eine Termin nicht — sie sind im Anhang mit Schweregrad und Alternativmethode ausdrücklich benannt,
statt verschwiegen.

#callout(color: teal)[
  *Mehr Tiefe nur bei Bedarf:* Alle Messgrößen, Schwellenwerte, die Funkphysik und das genaue Mess-
  und Auswerteverfahren stehen im ausführlichen *Testkonzept* (`test-concept.pdf`) und den
  Begleitpapieren zu Grenzen/Restrisiken und offenen Punkten. Diese Seite ist das Vorblatt — sie soll
  genügen, um das Vorhaben zu verstehen und zu entscheiden.
]
