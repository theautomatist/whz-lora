# System Design

The authoritative architecture of whz-lora is **not duplicated here** — it lives in
the single sources of truth, so there is only ever one place to update:

- **Topology, data model & data flow** — [Concept Paper §2](../concept/concept-paper.md)
  (component, ER and data-flow diagrams).
- **What the product does** — the [Feature Registry](../features.md) (F-0001 … F-0005).
- **Why it is built this way** — the [Architecture Decision Records](../decisions/index.md),
  notably ADR-0014 (ChirpStack v4), ADR-0015 (smoke-test toolchain), ADR-0017
  (local verification), ADR-0018 (gateway USB-NDIS) and ADR-0019 (provisioning app).

## Runtime components (at a glance)

A navigational summary only — the compose file is authoritative for versions and ports.

| Container | Role | Host port |
|---|---|---|
| `chirpstack` | LoRaWAN Network Server + gRPC API + Web UI | 8080 |
| `chirpstack-gateway-bridge` | Semtech UDP packet forwarder endpoint | 1700/udp |
| `chirpstack-gateway-bridge-basicstation` | Basics Station endpoint | 3001 |
| `mosquitto` | MQTT broker (auth + ACL) | 1883 |
| `postgres` | LNS persistence | — |
| `redis` | sessions / cache | — |
| `provisioning-app` | Actuator provisioning & commissioning web app (F-0005) | 8092 |

For the rationale behind each component, follow the ADRs linked above.
