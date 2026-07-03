# Feldtest-Cockpit

FastAPI web app for managing WHZ LoRaWAN field test campaigns.

## Panels

0. **Phase / SF-Switch** — switch all registered devices between three
   measurement phases by reassigning their ChirpStack device profile via
   `POST /api/phase`:

   | Button | Phase label in CSV | ChirpStack profile | ADR algorithm |
   |---|---|---|---|
   | Normal · ADR | `adr` | `WHZ-Feldtest-EU868` | `default` |
   | Phase 1 · SF9 | `sf9` | `WHZ-Feldtest-SF9` | `fixed_dr3` (DR3) |
   | Phase 2 · SF12 | `sf12` | `WHZ-Feldtest-SF12` | `fixed_dr0` (DR0) |

   The three device profiles are auto-created at startup (idempotent
   find-or-create); no manual ChirpStack provisioning is needed.
   The `phase` column appears in every CSV row recorded after the switch.
   Campaign phase is only updated in memory when **all** devices switch
   successfully; a partial failure returns HTTP 502 and leaves the CSV
   label unchanged.

   **MClimate Vicki convenience downlinks** (sent to all registered devices):
   - *Intervall 5 min* — enqueues `0x0205` on FPort 1 (set keepalive period).
     Uses `count:false` so these commands do **not** inflate the DL-PDR
     denominator.
   - *HW/SW-Version lesen* — enqueues `0x04` on FPort 1 (read hardware and
     software version; elicits a confirmed reply). Uses `count:true` so
     successful ACKs are tracked in the downlink PDR.

1. **Devices** — register and list OTAA devices in `whz-feldtest`.
2. **Measurement point** — set current point metadata; start/stop CSV recording;
   download the current file.
3. **Live dashboard** — SSE-fed table of per-device RSSI/SNR/SF/fCnt/PDR.
4. **Downlink loopback** — enqueue a confirmed downlink; track ACK-PDR per point.
5. **Coexistence scan** — decode gateway protobuf frames; compute per-SF/channel
   CAF with traffic-light classification.
6. **Antenna** — toggle between 3 dBi and 12 dBi; written into every CSV row.

## Running locally (dev)

```bash
cd cockpit
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Needs `CHIRPSTACK_HOST`, `MQTT_HOST`, etc. — see `.env.example` at the repo root.

## Tests

```bash
cd cockpit
pytest tests/
```

Pure-logic tests run without a broker or gRPC server:

| File | What it covers |
|---|---|
| `test_lorawan.py` | LoRaWAN math (ToA, CAF, traffic-light, PHY parsing) |
| `test_state.py` | `CampaignState`, `build_csv_row`, CSV recording, phase/antenna |
| `test_chirpstack.py` | `set_device_profile` stub interactions (mocked gRPC) |
| `test_phase.py` | `_apply_phase_to_devices` aggregation + conditional `set_phase` |
