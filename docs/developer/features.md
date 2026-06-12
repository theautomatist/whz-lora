# Feature Registry

This file is the single source of truth for the features this project is
built on. It is maintained by the feature process — see
`setup/feature-process.md` and the `/feature` skill.

While there are few features they live in this single file. Beyond about
eight, the feature process migrates them to one file per feature under
`docs/developer/features/`.

Status values: `proposed`, `active`, `deprecated`, `removed`. A removed
feature keeps its entry, marked `removed`, with the reason — the registry
records what was removed and why. The entry format is defined in
`setup/feature-process.md`.

## Features

### F-0001 — Gateway-Anbindung

- Status: active (Gateway-Pfad), Sensor-Uplink ausstehend bis erste
  Hardware verfügbar
- Summary: LoRaWAN-Gateways (Start: Kerlink Wirnet iFemtoCell Evolution
  868) sprechen mit dem im Stack betriebenen ChirpStack v4 LNS.
- Problem solved: Eigene Gateways müssen Uplinks an einen lokal
  betriebenen LNS liefern, ohne externen Cloud-Service.
- User-facing behavior: Der Betreiber konfiguriert sein Gateway laut
  Anleitung; das Gateway erscheint in der ChirpStack-UI als `online`
  und liefert empfangene Frames. Anleitung:
  [docs/user/kerlink-ifemtocell-bring-up.md](kerlink-ifemtocell-bring-up.md).
- Acceptance criteria:
  - **CI (Simulator-Modus)**: Das Smoke-Test-Skript registriert ein
    virtuelles Gateway in ChirpStack und sendet über UDP-Port 1700
    einen Stats-Frame; das Gateway erscheint in der gRPC-API mit Status
    `online` (`LastSeenAt` jünger als 30 Sekunden). — **erfüllt durch
    PR #2 (F-0004), Smoke-Test grün.**
  - **Manuell (Kerlink-Hardware, Gateway-Pfad)**: Der Kerlink
    iFemtoCell Evolution ist über das Packet Forwarder Protocol
    (UDP/1700) verbunden und in der ChirpStack-UI mit Status `online`
    sichtbar; Stats-Frames werden alle 30 Sekunden in der
    ChirpStack-Metrik-Tabelle gespeichert. — **erfüllt durch PR #4,
    Bring-up am 2026-05-26 gegen EUI `7076ff0064071a3d`.**
  - **Manuell (Sensor-Uplink)**: Ein realer OTAA-EU868-Sensor joint
    über das Gateway und sein Uplink erscheint als JSON-Nachricht auf
    `application/<id>/device/<eui>/event/up`. — **offen**, wartet auf
    Hardware (Empfehlung Dragino LHT52, ~21 € netto). Wird in einer
    Folge-Direktive abgeschlossen.
  - Unterstützt sind Semtech UDP Packet Forwarder und (auf TOML-Ebene
    konfigurierbar) Basics Station.
- Dependencies: F-0004 (Reproduzierbares Setup)
- Interfaces & data: Backhaul Gateway → Stack via Packet Forwarder
  (UDP/1700) oder Basics Station (WebSocket).
- Realised by: n/a (Single-Repo)
- Linked directives / ADRs: ADR-0014, ADR-0015, ADR-0018; Issue #3, PR #4
- History: 2026-05-26 added; 2026-05-26 Gateway-Pfad active (PR #4)

### F-0002 — Geräte-Verwaltung

- Status: proposed
- Summary: End-Devices (Sensoren) und Gateways werden in der
  ChirpStack-Browser-UI registriert, konfiguriert und überwacht; die
  zugehörigen JavaScript-Codecs sind unter `codecs/` versioniert und
  unit-getestet.
- Problem solved: Geräte müssen mit DevEUI, Keys, Profil und Codec
  verwaltbar sein, ohne eigene UI zu bauen.
- User-facing behavior: Der Betreiber meldet sich an der ChirpStack-UI
  an, legt Tenants, Applications, Devices und Gateways an, hinterlegt
  Codecs und beobachtet Uplinks live.
- Acceptance criteria:
  - Die ChirpStack-UI ist nach `docker compose up` unter
    `http://<host>:8080` erreichbar (HTTP-Status 200 auf `/`).
  - Das Smoke-Test-Skript legt per gRPC-API einen Tenant, eine
    Application, ein Device-Profile und ein Device an und liest sie per
    gRPC wieder aus.
  - Jeder Codec unter `codecs/` hat eine Test-Suite (`*.test.js`); das
    CI führt `node --test codecs/` und alle Tests sind grün.
  - Im Smoke-Test-Durchlauf erscheinen Uplinks mit dekodierten
    JSON-Feldern auf dem MQTT-Topic — leere Codecs lassen den Test
    scheitern.
- Dependencies: F-0001 (Gateway-Anbindung), F-0004 (Reproduzierbares Setup)
- Interfaces & data: ChirpStack-Web-UI (HTTP/8080), gRPC-API (TCP/8080),
  `codecs/`.
- Realised by: n/a
- Linked directives / ADRs: ADR-0014
- History: 2026-05-26 added

### F-0003 — Daten-Weiterleitung

- Status: proposed
- Summary: Uplink-Events werden über den im Stack betriebenen Mosquitto-
  MQTT-Broker veröffentlicht; externe Konsumenten subscriben darauf.
- Problem solved: Forschungs-Skripte und Auswerteketten brauchen einen
  standardisierten Push-Kanal, der unabhängig von der ChirpStack-UI ist.
- User-facing behavior: Ein externer MQTT-Subscriber verbindet sich mit
  Credentials gegen den Broker, abonniert die Standard-Topics und
  empfängt Uplinks als JSON-Nachrichten in Echtzeit.
- Acceptance criteria:
  - Mosquitto ist nach `docker compose up` unter `tcp://<host>:1883`
    erreichbar und akzeptiert Verbindungen nur mit gültigen Credentials
    aus `mosquitto/passwd`.
  - Anonyme Verbindungen sind deaktiviert (`allow_anonymous false`).
  - Im Smoke-Test-Durchlauf erscheint der eingespielte Test-Uplink
    binnen 30 Sekunden auf
    `application/<id>/device/<eui>/event/up` als JSON-Nachricht mit den
    dekodierten Codec-Feldern.
  - Die User-Doku enthält einen funktionierenden Python-Beispiel-
    Subscriber (`paho-mqtt`), der gegen die Test-Credentials läuft.
- Dependencies: F-0001, F-0002, F-0004
- Interfaces & data: MQTT (TCP/1883) gemäß ChirpStack-Topic-Schema
  (`application/{id}/device/{eui}/event/up`).
- Realised by: n/a
- Linked directives / ADRs: ADR-0014
- History: 2026-05-26 added

### F-0004 — Reproduzierbares Setup

- Status: active
- Summary: Der gesamte Server-Stack (ChirpStack v4, Gateway-Bridges,
  Mosquitto, PostgreSQL, Redis) ist als versioniertes Docker-Compose im
  Repository abgelegt und mit `docker compose up` startbar.
- Problem solved: Ohne reproduzierbares Setup ist die Basis nicht
  übertragbar (z.B. von Entwickler-Host auf Lab-VM) und nicht testbar.
- User-facing behavior: Aus einem frisch geklonten Repository startet
  der Stack mit einer einzigen Compose-Befehlsfolge; Konfigurationen und
  Secrets sind über `.env` parametrisiert.
- Acceptance criteria:
  - `git clone … && cp .env.example .env && docker compose up -d`
    bringt den Stack lauffähig hoch (alle Container `running`,
    PostgreSQL-Migrationen erfolgreich, keine Restart-Loops).
  - Alle Container-Images im Compose sind auf eine konkrete Version
    gepinnt (kein `:latest`).
  - `.env.example` ist im Repository, `.env` ist im `.gitignore`.
  - Der CI-Job (Linux/Ubuntu) führt den Stack-Hochlauf + Smoke-Test in
    unter 10 Minuten durch und beendet ihn sauber (`docker compose
    down -v` im Teardown).
- Dependencies: keine
- Interfaces & data: Repository, Docker, `.env`.
- Realised by: n/a
- Linked directives / ADRs: ADR-0014, ADR-0015, ADR-0017, PR #2
- History: 2026-05-26 added; 2026-05-26 status → active (PR #2)

### F-0005 — Aktuator-Provisioning- & Inbetriebnahme-App

- Status: proposed (im Bau über Issue #6; wird mit Gate 2 auf active gesetzt)
- Summary: Eine mobiltaugliche Web-App (nur im WHZ-Netz/VPN erreichbar), mit
  der OTAA-Aktuatoren (Stellantriebe) einzeln oder per CSV-Bulk-Import in
  ChirpStack eingebucht werden — inklusive direktem Feedback, ob ein Gerät
  tatsächlich gejoint hat und sendet. Die App ist eine eng umrissene Ausnahme
  von Non-Goal #5 (siehe ADR-0019).
- Problem solved: DevEUI und AppKey sind lange Hex-Ketten; bei manueller
  Eingabe entstehen Tippfehler, Geräte sind dann nicht eingeloggt und es fällt
  zu spät auf. Die App reduziert Tippfehler und macht den „ist es online?"-
  Status pro Gerät unmittelbar sichtbar.
- User-facing behavior: Der Betreiber öffnet die App im Browser (Handy oder
  Desktop), gibt einen Stellantrieb per Formular ein oder lädt eine CSV mit
  einer Zeile pro Gerät hoch, und sieht im Inbetriebnahme-Dashboard pro Gerät
  eine Drei-Zustands-Ampel ⚪ Provisioniert → 🟡 Gejoint → 🟢 Online (erster
  Uplink), mit Zeitpunkt und — soweit verfügbar — RSSI/SNR. Einzelne Geräte
  können bestätigungspflichtig gelöscht werden.
- Acceptance criteria:
  - Das Einzelformular legt Gerät **und** OTAA-Keys in ChirpStack an; bei
    LoRaWAN 1.0.x steht der AppKey in `DeviceKeys.nwk_key`, `app_key` = 32
    Hex-Nullen (per `GetKeys` rücklesbar); das Gerät kann über das Gateway
    OTAA-joinen.
  - CSV-Bulk-Import: eine Zeile pro Gerät, pro-Zeile-Ergebnis (angelegt /
    Keys aktualisiert / Fehler+Grund), fährt über fehlerhafte Zeilen hinweg;
    Re-Import ist idempotent (keine Duplikate); Hex-Längen (16/16/32) werden
    vor dem Schreiben geprüft.
  - Die hochgeladene CSV bzw. der AppKey wird **nie** auf Platte, in Logs oder
    ins Git geschrieben — nur im Arbeitsspeicher der Anfrage; ChirpStack/
    PostgreSQL ist der einzige Ruheort des Schlüssels.
  - Das Dashboard zeigt pro Gerät ⚪/🟡/🟢 live aus ChirpStack (keine eigene
    DB), mit Last-Seen und (best effort) RSSI/SNR; Aktualisierung on-demand.
  - Ein Gerät kann über die App aus ChirpStack gelöscht werden (mit expliziter
    Bestätigung).
  - Geräte landen unter einer konfigurierbaren Application (Default
    `WHZ-Stellantriebe`) mit einem Klasse-A-OTAA-Geräteprofil (EU868,
    LoRaWAN 1.0.x).
  - Die App ist ein einzelner neuer Docker-Compose-Service, nur im
    Host-/WHZ-Netz erreichbar (kein öffentlicher Zugang), spricht gRPC mit
    ChirpStack (kein REST-Proxy). Optionale HTTP-Basic-Auth über `.env`.
  - Der gRPC-Kern liegt in `scripts/chirpstack_client.py` und wird von
    `smoke_test.py` **und** der App genutzt; der bestehende Smoke-Test bleibt
    grün. Die Verifikation übt den zuvor ungetesteten OTAA-`CreateKeys`-Pfad.
- Dependencies: F-0001 (Gateway-Anbindung), F-0002 (Geräte-Verwaltung),
  F-0004 (Reproduzierbares Setup)
- Interfaces & data: HTTP-UI (TCP/8092, WHZ-Netz/VPN), gRPC zu ChirpStack
  (`chirpstack:8080`), CSV-Upload (transient). Keine eigene Persistenz.
- Bewusst draußen / Roadmap: QR-Scanner, OCR-Labelerkennung, MQTT-Live-Push,
  Raumzuweisung, Klasse-C/Netzgeräte, öffentliche Internet-Exposition,
  Nutzer-bezogene Authentifizierung.
- Realised by: `scripts/chirpstack_client.py`, `provisioning/`
- Linked directives / ADRs: Issue #6, ADR-0019
- History: 2026-06-12 added (Issue #6, Grilling-Session); Spec per ADR-0019
