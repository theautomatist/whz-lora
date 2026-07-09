"""test_lorawan.py — unit tests for pure LoRa/LoRaWAN helper functions.

Runs without any external packages (only stdlib + the local lorawan module).
"""
import pytest
from app.lorawan import (
    caf,
    classify_network,
    freq_to_channel,
    lora_airtime,
    mtype_name,
    parse_devaddr,
    parse_join_request,
    parse_mhdr,
    traffic_light,
    vendor_for_oui,
)

# ---------------------------------------------------------------------------
# lora_airtime — known values (Semtech AN1200.13 formula)
# ---------------------------------------------------------------------------
#
# Reference calculations (BW=125 kHz, CR=1 (4/5), n_preamble=8,
#   explicit header IH=0, CRC=1, LDRO enabled for SF≥11):
#
#   SF7  PL=10  DE=0  n_payload=28  t≈41.2 ms
#   SF12 PL=10  DE=1  n_payload=18  t≈991.2 ms
#   SF9  PL=20  DE=0  n_payload=33  t≈185.3 ms


@pytest.mark.parametrize(
    "sf, pl, expected_ms, tol_ms",
    [
        (7,  10,   41.2,  2.0),
        (12, 10,  991.2,  5.0),
        (9,  20,  185.3,  5.0),
    ],
)
def test_lora_airtime(sf, pl, expected_ms, tol_ms):
    result_ms = lora_airtime(sf, pl) * 1000
    assert abs(result_ms - expected_ms) < tol_ms, (
        f"SF{sf} PL={pl}: got {result_ms:.2f} ms, expected {expected_ms} ms ±{tol_ms} ms"
    )


def test_lora_airtime_increases_with_sf():
    """Higher SF must always produce longer ToA at fixed payload."""
    times = [lora_airtime(sf, 20) for sf in range(7, 13)]
    assert times == sorted(times), "airtime must increase monotonically with SF"


def test_lora_airtime_ldro_boundary():
    """SF11 must enable LDRO (longer than SF10 would be without it)."""
    t10 = lora_airtime(10, 10)
    t11 = lora_airtime(11, 10)
    assert t11 > t10


# ---------------------------------------------------------------------------
# CAF
# ---------------------------------------------------------------------------


def test_caf_zero_rate():
    assert caf(0, 7, 10) == 0.0


def test_caf_low_traffic():
    # 1 frame/hour at SF7, ~41 ms ToA: CAF << 0.01
    result = caf(1, 7, 10)
    assert result < 0.001


def test_caf_high_traffic():
    # 2 000 frames/hour at SF12, ~991 ms ToA → >50 % → well above red threshold
    result = caf(2000, 12, 10)
    assert result > 0.10


def test_caf_proportional_to_rate():
    c1 = caf(10, 9, 15)
    c2 = caf(20, 9, 15)
    assert abs(c2 / c1 - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# traffic_light
# ---------------------------------------------------------------------------


def test_tl_green():
    assert traffic_light(0.00) == "green"
    assert traffic_light(0.01) == "green"
    assert traffic_light(0.019) == "green"


def test_tl_yellow_lower_boundary():
    # exactly 2% is yellow
    assert traffic_light(0.02) == "yellow"


def test_tl_yellow_upper_boundary():
    # exactly 10% is yellow
    assert traffic_light(0.10) == "yellow"


def test_tl_yellow_mid():
    assert traffic_light(0.05) == "yellow"


def test_tl_red():
    assert traffic_light(0.101) == "red"
    assert traffic_light(0.50)  == "red"


# ---------------------------------------------------------------------------
# parse_mhdr
# ---------------------------------------------------------------------------


def test_parse_mhdr_join_request():
    # MType 000 → 0x00 MHDR
    assert parse_mhdr(bytes([0x00])) == 0


def test_parse_mhdr_unconfirmed_data_up():
    # MType 010 → (0b010 << 5) = 0x40
    assert parse_mhdr(bytes([0x40, 0x00, 0x00, 0x00, 0x00])) == 2


def test_parse_mhdr_confirmed_data_up():
    # MType 100 → (0b100 << 5) = 0x80
    assert parse_mhdr(bytes([0x80, 0x00, 0x00, 0x00, 0x00])) == 4


def test_parse_mhdr_empty():
    assert parse_mhdr(b"") == -1


# ---------------------------------------------------------------------------
# parse_devaddr
# ---------------------------------------------------------------------------


def test_parse_devaddr_basic():
    # DevAddr 0x01020304 stored little-endian: bytes 1-4 = [04, 03, 02, 01]
    # big-endian hex result = "01020304"
    phy = bytes([0x40, 0x04, 0x03, 0x02, 0x01, 0x00, 0x01, 0x00])
    assert parse_devaddr(phy) == "01020304"


def test_parse_devaddr_too_short():
    assert parse_devaddr(bytes([0x40, 0x01, 0x02])) is None


def test_parse_devaddr_smoke_test_value():
    # From smoke_test.py: ABP_DEV_ADDR = "01020304", stored LE as 04 03 02 01
    phy = bytes([0x40]) + bytes([0x04, 0x03, 0x02, 0x01]) + bytes(10)
    assert parse_devaddr(phy) == "01020304"


# ---------------------------------------------------------------------------
# freq_to_channel
# ---------------------------------------------------------------------------


def test_freq_to_channel_defaults():
    assert freq_to_channel(868100000) == 0
    assert freq_to_channel(868300000) == 1
    assert freq_to_channel(868500000) == 2


def test_freq_to_channel_optional():
    assert freq_to_channel(867100000) == 3
    assert freq_to_channel(867900000) == 7


def test_freq_to_channel_unknown():
    assert freq_to_channel(900000000) == -1


# ---------------------------------------------------------------------------
# mtype_name — RF-environment survey (F-0006)
# ---------------------------------------------------------------------------


def test_mtype_name_known_values():
    assert mtype_name(0) == "join_request"
    assert mtype_name(1) == "join_accept"
    assert mtype_name(2) == "unconfirmed_data_up"
    assert mtype_name(3) == "unconfirmed_data_down"
    assert mtype_name(4) == "confirmed_data_up"
    assert mtype_name(5) == "confirmed_data_down"
    assert mtype_name(6) == "rejoin_request"
    assert mtype_name(7) == "proprietary"


def test_mtype_name_unknown():
    assert mtype_name(-1) == "unknown"
    assert mtype_name(99) == "unknown"


# ---------------------------------------------------------------------------
# classify_network — RF-environment survey (F-0006)
# ---------------------------------------------------------------------------


def test_classify_network_ttn():
    assert classify_network("26000000")["label"] == "The Things Network"
    assert classify_network("27abcdef")["label"] == "The Things Network"


def test_classify_network_private():
    assert classify_network("00112233")["label"] == "private/experimental"
    assert classify_network("01aabbcc")["label"] == "private/experimental"


def test_classify_network_other():
    assert classify_network("05aabbcc")["label"] == "other"


def test_classify_network_reports_top_byte():
    result = classify_network("26aabbcc")
    assert result["top_byte"] == 0x26


def test_classify_network_malformed_never_raises():
    assert classify_network(None) == {"label": "unknown", "top_byte": None}
    assert classify_network("") == {"label": "unknown", "top_byte": None}
    assert classify_network("z") == {"label": "unknown", "top_byte": None}
    assert classify_network("zz") == {"label": "unknown", "top_byte": None}


# ---------------------------------------------------------------------------
# parse_join_request — RF-environment survey (F-0006)
# ---------------------------------------------------------------------------


def test_parse_join_request_basic():
    # MHDR(1) | JoinEUI(8 LE) | DevEUI(8 LE) | DevNonce(2) | MIC(4) = 23 bytes
    join_eui_be = "0102030405060708"
    dev_eui_be = "a84041aabbccddee"
    join_eui_le = bytes.fromhex(join_eui_be)[::-1]
    dev_eui_le = bytes.fromhex(dev_eui_be)[::-1]
    phy = bytes([0x00]) + join_eui_le + dev_eui_le + bytes([0x00, 0x01]) + bytes(4)
    assert len(phy) == 23

    result = parse_join_request(phy)
    assert result == {"dev_eui": dev_eui_be, "join_eui": join_eui_be}


def test_parse_join_request_too_short():
    assert parse_join_request(bytes(22)) is None


def test_parse_join_request_empty():
    assert parse_join_request(b"") is None


def test_parse_join_request_exactly_23_bytes_required():
    ok = bytes(23)
    assert parse_join_request(ok) is not None
    assert parse_join_request(ok[:-1]) is None


# ---------------------------------------------------------------------------
# vendor_for_oui — RF-environment survey (F-0006)
# ---------------------------------------------------------------------------


def test_vendor_for_oui_known():
    assert vendor_for_oui("a84041") == {"name": "Dragino", "oui": "a84041"}
    assert vendor_for_oui("24e124") == {"name": "Milesight", "oui": "24e124"}


def test_vendor_for_oui_case_insensitive():
    assert vendor_for_oui("A84041") == {"name": "Dragino", "oui": "a84041"}


def test_vendor_for_oui_shared_block():
    result = vendor_for_oui("70b3d5")
    assert result["name"] == "LoRa Alliance shared (70B3D5)"


def test_vendor_for_oui_unknown_falls_back_to_raw_hex():
    assert vendor_for_oui("aabbcc") == {"name": "OUI aabbcc", "oui": "aabbcc"}


def test_vendor_for_oui_empty_never_raises():
    assert vendor_for_oui("") == {"name": "unknown", "oui": ""}
    assert vendor_for_oui(None) == {"name": "unknown", "oui": ""}
