"""
test_validators.py — stdlib unittest for validators.py.

Run with:
  python -m unittest provisioning/test_validators.py
  # or from within the provisioning/ directory:
  python -m unittest test_validators
"""

import unittest

from validators import normalise_hex, valid_eui, valid_appkey, parse_csv


class TestNormaliseHex(unittest.TestCase):
    def test_strips_colons(self):
        self.assertEqual(normalise_hex("01:02:03:04:05:06:07:08"), "0102030405060708")

    def test_strips_hyphens(self):
        self.assertEqual(normalise_hex("01-02-03-04-05-06-07-08"), "0102030405060708")

    def test_strips_spaces(self):
        self.assertEqual(normalise_hex("01 02 03 04"), "01020304")

    def test_lowercases(self):
        self.assertEqual(normalise_hex("AABBCCDD"), "aabbccdd")

    def test_already_clean(self):
        self.assertEqual(normalise_hex("aabbccdd"), "aabbccdd")


class TestValidEui(unittest.TestCase):
    def test_valid_plain(self):
        self.assertEqual(valid_eui("0102030405060708"), "0102030405060708")

    def test_valid_with_colons(self):
        self.assertEqual(valid_eui("01:02:03:04:05:06:07:08"), "0102030405060708")

    def test_valid_uppercase(self):
        self.assertEqual(valid_eui("AABBCCDDEEFF0011"), "aabbccddeeff0011")

    def test_too_short(self):
        with self.assertRaises(ValueError) as ctx:
            valid_eui("010203")
        self.assertIn("010203", str(ctx.exception))

    def test_too_long(self):
        with self.assertRaises(ValueError):
            valid_eui("010203040506070809")

    def test_non_hex_chars(self):
        with self.assertRaises(ValueError):
            valid_eui("ZZZZZZZZZZZZZZZZ")

    def test_empty_string(self):
        with self.assertRaises(ValueError):
            valid_eui("")


class TestValidAppKey(unittest.TestCase):
    def test_valid_32_chars(self):
        key = "0102030405060708090a0b0c0d0e0f10"
        self.assertEqual(valid_appkey(key), key)

    def test_valid_with_colons(self):
        key_colon = "01:02:03:04:05:06:07:08:09:0a:0b:0c:0d:0e:0f:10"
        self.assertEqual(valid_appkey(key_colon), "0102030405060708090a0b0c0d0e0f10")

    def test_too_short(self):
        with self.assertRaises(ValueError):
            valid_appkey("0102030405060708")

    def test_non_hex(self):
        with self.assertRaises(ValueError):
            valid_appkey("ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ")

    def test_zeros(self):
        zeros = "0" * 32
        self.assertEqual(valid_appkey(zeros), zeros)


class TestParseCsv(unittest.TestCase):
    def _csv(self, *rows):
        return "\n".join(rows)

    def test_basic_required_fields(self):
        text = self._csv(
            "dev_eui,app_key",
            "0102030405060708,0102030405060708090a0b0c0d0e0f10",
        )
        results = parse_csv(text)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["ok"])
        d = results[0]["data"]
        self.assertEqual(d["dev_eui"], "0102030405060708")
        self.assertEqual(d["app_key"], "0102030405060708090a0b0c0d0e0f10")
        self.assertEqual(d["join_eui"], "0000000000000000")
        self.assertEqual(d["name"], "0102030405060708")
        self.assertEqual(d["class"], "A")

    def test_optional_fields_present(self):
        text = self._csv(
            "dev_eui,app_key,join_eui,name,class",
            "0102030405060708,0102030405060708090a0b0c0d0e0f10,aabbccddee010203,My Device,A",
        )
        results = parse_csv(text)
        self.assertTrue(results[0]["ok"])
        d = results[0]["data"]
        self.assertEqual(d["join_eui"], "aabbccddee010203")
        self.assertEqual(d["name"], "My Device")
        self.assertEqual(d["class"], "A")

    def test_column_alias_deveui_appkey(self):
        text = self._csv(
            "DevEUI,AppKey",
            "0102030405060708,0102030405060708090a0b0c0d0e0f10",
        )
        results = parse_csv(text)
        self.assertTrue(results[0]["ok"])

    def test_column_alias_joineui_appeui(self):
        text = self._csv(
            "dev_eui,app_key,AppEUI",
            "0102030405060708,0102030405060708090a0b0c0d0e0f10,aabbccddee010203",
        )
        results = parse_csv(text)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["data"]["join_eui"], "aabbccddee010203")

    def test_mixed_valid_and_invalid_rows(self):
        text = self._csv(
            "dev_eui,app_key",
            "0102030405060708,0102030405060708090a0b0c0d0e0f10",
            "badinput,tooshort",
            "aabbccddeeff0011,aabbccddeeff00110102030405060708",
        )
        results = parse_csv(text)
        self.assertEqual(len(results), 3)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertTrue(results[2]["ok"])

    def test_missing_dev_eui(self):
        text = self._csv(
            "app_key",
            "0102030405060708090a0b0c0d0e0f10",
        )
        results = parse_csv(text)
        self.assertFalse(results[0]["ok"])
        self.assertIn("dev_eui", results[0]["error"])

    def test_missing_app_key(self):
        text = self._csv(
            "dev_eui",
            "0102030405060708",
        )
        results = parse_csv(text)
        self.assertFalse(results[0]["ok"])
        self.assertIn("app_key", results[0]["error"])

    def test_eui_with_colons_normalised(self):
        text = self._csv(
            "dev_eui,app_key",
            "01:02:03:04:05:06:07:08,0102030405060708090a0b0c0d0e0f10",
        )
        results = parse_csv(text)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["data"]["dev_eui"], "0102030405060708")

    def test_class_uppercased(self):
        text = self._csv(
            "dev_eui,app_key,class",
            "0102030405060708,0102030405060708090a0b0c0d0e0f10,a",
        )
        results = parse_csv(text)
        self.assertTrue(results[0]["ok"])
        self.assertEqual(results[0]["data"]["class"], "A")

    def test_empty_csv(self):
        results = parse_csv("")
        self.assertEqual(results, [])

    def test_header_only(self):
        results = parse_csv("dev_eui,app_key")
        self.assertEqual(results, [])

    def test_multiple_rows(self):
        rows = ["dev_eui,app_key"]
        for i in range(1, 6):
            eui = f"{i:016x}"
            key = f"{i:032x}"
            rows.append(f"{eui},{key}")
        results = parse_csv("\n".join(rows))
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r["ok"] for r in results))

    def test_key_mapping_nwk_key_is_app_key(self):
        """The provisioning app passes app_key from CSV as nwk_key to ChirpStack
        (LoRaWAN 1.0.x mapping). The validator must preserve the app_key value."""
        text = self._csv(
            "dev_eui,app_key",
            "0102030405060708,deadbeefdeadbeefdeadbeefdeadbeef",
        )
        results = parse_csv(text)
        self.assertTrue(results[0]["ok"])
        # The value from the CSV column "app_key" is what the provisioner maps
        # to nwk_key on the ChirpStack side.
        self.assertEqual(results[0]["data"]["app_key"], "deadbeefdeadbeefdeadbeefdeadbeef")


if __name__ == "__main__":
    unittest.main()
