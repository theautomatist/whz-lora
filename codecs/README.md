# Device Codecs

This directory contains JavaScript payload codecs for LoRaWAN devices
registered in ChirpStack. Each codec decodes the raw bytes of a device's
uplink payload into structured JSON fields.

## Convention

- One file per device type: `<device-type>.js`
- Every codec file has a corresponding test file: `<device-type>.test.js`
- Tests run with Node.js built-in test runner: `node --test codecs/`

## Structure

A codec file exports two functions that ChirpStack calls:

```js
// Decode uplink payload bytes into JSON object.
function decodeUplink(input) {
  // input.bytes — Uint8Array of payload bytes
  // input.fPort — LoRaWAN port number
  return { data: {} };
}

// Encode downlink command from JSON object into bytes.
function encodeDownlink(input) {
  // input.data — JSON object
  return { bytes: [] };
}
```

The `*.test.js` files use `node:test` and `node:assert` — no external
dependencies required.
