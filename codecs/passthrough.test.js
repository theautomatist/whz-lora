"use strict";

// Passthrough codec — returns raw bytes as a hex string.
// This is a trivial example and test to verify the codec test harness works.

const { test } = require("node:test");
const assert = require("node:assert/strict");

function decodeUplink(input) {
  const hex = Array.from(input.bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  return { data: { raw: hex } };
}

function encodeDownlink(input) {
  return { bytes: [] };
}

test("decodeUplink returns hex string for given bytes", () => {
  const result = decodeUplink({ bytes: [0xde, 0xad, 0xbe, 0xef], fPort: 1 });
  assert.deepEqual(result, { data: { raw: "deadbeef" } });
});

test("decodeUplink returns empty string for empty payload", () => {
  const result = decodeUplink({ bytes: [], fPort: 1 });
  assert.deepEqual(result, { data: { raw: "" } });
});

test("encodeDownlink returns empty bytes", () => {
  const result = encodeDownlink({ data: { command: "reset" } });
  assert.deepEqual(result, { bytes: [] });
});
