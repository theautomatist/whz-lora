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

- Status: proposed
- Summary: LoRaWAN-Gateways (Start: Kerlink Wirnet iFemtoCell Evolution
  868) sprechen mit dem im Stack betriebenen ChirpStack v4 LNS.
- Problem solved: Eigene Gateways müssen Uplinks an einen lokal
  betriebenen LNS liefern, ohne externen Cloud-Service.
- User-facing behavior: Der Betreiber konfiguriert sein Gateway laut
  Anleitung; das Gateway erscheint in der ChirpStack-UI als `online`
  und liefert empfangene Frames.
- Acceptance criteria:
  - **CI (Simulator-Modus)**: Das Smoke-Test-Skript registriert ein
    virtuelles Gateway in ChirpStack und sendet über UDP-Port 1700
    einen Stats-Frame; das Gateway erscheint in der gRPC-API mit Status
    `online` (`LastSeenAt` jünger als 30 Sekunden).
  - **Manuell**: Der Kerlink iFemtoCell ist über das Packet Forwarder
    Protocol (UDP/1700) oder Basics Station (WebSocket) verbunden und
    in der ChirpStack-UI mit Status `online` sichtbar.
  - Unterstützt sind Semtech UDP Packet Forwarder und Basics Station.
- Dependencies: F-0004 (Reproduzierbares Setup)
- Interfaces & data: Backhaul Gateway → Stack via Packet Forwarder
  (UDP/1700) oder Basics Station (WebSocket).
- Realised by: n/a (Single-Repo)
- Linked directives / ADRs: ADR-0014, ADR-0015
- History: 2026-05-26 added

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
