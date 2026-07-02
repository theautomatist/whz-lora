# Feldtest-Cockpit

FastAPI web app for managing WHZ LoRaWAN field test campaigns.

## Panels

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

Pure-logic tests (`test_lorawan.py`, `test_state.py`) run without a broker or
gRPC server.
