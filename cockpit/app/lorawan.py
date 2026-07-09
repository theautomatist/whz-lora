"""lorawan.py — pure LoRa/LoRaWAN helper functions.

No external dependencies; importable without any pip packages installed.
All functions are stateless and deterministic — safe to unit-test in isolation.
"""
import math
from typing import Optional

# ---------------------------------------------------------------------------
# Time-on-Air
# ---------------------------------------------------------------------------


def lora_airtime(
    sf: int,
    payload_len: int,
    bw: float = 125e3,
    cr: int = 1,
    n_preamble: int = 8,
) -> float:
    """Compute LoRa packet Time-on-Air in seconds (Semtech AN1200.13).

    sf          — spreading factor (7–12)
    payload_len — PHY payload length in bytes
    bw          — bandwidth in Hz (default 125 kHz)
    cr          — coding rate offset: 1=4/5, 2=4/6, 3=4/7, 4=4/8
    n_preamble  — preamble symbols (default 8)

    Assumes explicit header (IH=0) and CRC enabled (CRC=1), which is standard
    for LoRaWAN uplinks.
    Low-data-rate optimisation (LDRO/DE) is enabled automatically for SF≥11
    at BW=125 kHz, per LoRaWAN regional parameters.
    """
    de = 1 if (sf >= 11 and bw <= 125e3) else 0

    t_sym = (2 ** sf) / bw  # symbol duration [s]

    # Number of payload symbols (explicit header, CRC=1)
    num = 8 * payload_len - 4 * sf + 28 + 16
    den = 4 * (sf - 2 * de)
    n_payload = 8 + max(math.ceil(num / den) * (cr + 4), 0)

    t_preamble = (n_preamble + 4.25) * t_sym
    t_payload = n_payload * t_sym
    return t_preamble + t_payload


# ---------------------------------------------------------------------------
# CAF — Channel Airtime Fraction
# ---------------------------------------------------------------------------


def caf(frames_per_hour: float, sf: int, payload_len: int) -> float:
    """Channel Airtime Fraction for a given traffic rate.

    Returns a dimensionless fraction in [0, 1].
    Uses lora_airtime with default BW=125 kHz and CR=1.
    """
    if frames_per_hour <= 0:
        return 0.0
    toa = lora_airtime(sf, payload_len)
    return frames_per_hour * toa / 3600.0


def traffic_light(caf_value: float) -> str:
    """Classify a CAF value as 'green', 'yellow', or 'red'.

    green  — CAF < 2 %
    yellow — 2 % ≤ CAF ≤ 10 %
    red    — CAF > 10 %
    """
    if caf_value < 0.02:
        return "green"
    if caf_value <= 0.10:
        return "yellow"
    return "red"


# ---------------------------------------------------------------------------
# PHY payload parsing
# ---------------------------------------------------------------------------


def parse_mhdr(phy_payload: bytes) -> int:
    """Extract MType from the MHDR byte (bits 7–5) of a LoRaWAN PHY payload.

    Returns -1 for an empty payload.
    Common MType values:
      0 — Join Request
      1 — Join Accept
      2 — Unconfirmed Data Up
      3 — Unconfirmed Data Down
      4 — Confirmed Data Up
      5 — Confirmed Data Down
    """
    if not phy_payload:
        return -1
    return (phy_payload[0] >> 5) & 0x07


def parse_devaddr(phy_payload: bytes) -> Optional[str]:
    """Extract DevAddr from a LoRaWAN data-frame PHY payload.

    Bytes 1–4 of the FHDR carry the DevAddr in little-endian order.
    Returns an 8-character big-endian hex string (ChirpStack convention),
    or None if the payload is too short.

    Only meaningful when MType is a data-frame type (2, 3, 4, 5).
    """
    if len(phy_payload) < 5:
        return None
    dev_addr_le = phy_payload[1:5]
    return dev_addr_le[::-1].hex()


# ---------------------------------------------------------------------------
# MType decode (RF-environment survey — F-0006)
# ---------------------------------------------------------------------------

MTYPE_NAMES: dict[int, str] = {
    0: "join_request",
    1: "join_accept",
    2: "unconfirmed_data_up",
    3: "unconfirmed_data_down",
    4: "confirmed_data_up",
    5: "confirmed_data_down",
    6: "rejoin_request",
    7: "proprietary",
}


def mtype_name(mtype: int) -> str:
    """Canonical name for a parse_mhdr() result. 'unknown' for anything
    outside 0–7 (e.g. parse_mhdr's -1 for an empty payload) — never raises.
    """
    return MTYPE_NAMES.get(mtype, "unknown")


# ---------------------------------------------------------------------------
# Network classification (RF-environment survey — F-0006)
#
# Best-effort, DevAddr TOP BYTE only — this is deliberately NOT a full
# NetID/NwkID decode (LoRaWAN 1.0.x's NetIdType prefix is variable-length,
# 1–7 MSBs depending on NetID class); it just flags the well-known ranges
# relevant to a field test: TTN's public community-network prefix and the
# private/experimental range.
# ---------------------------------------------------------------------------


def classify_network(dev_addr_hex: Optional[str]) -> dict:
    """Best-effort network label from a DevAddr's top byte:
    0x26/0x27 -> "The Things Network" (its public community-network prefix),
    0x00/0x01 -> "private/experimental", else "other".

    Returns {"label": str, "top_byte": Optional[int]}; never raises.
    """
    if not dev_addr_hex or len(dev_addr_hex) < 2:
        return {"label": "unknown", "top_byte": None}
    try:
        top_byte = int(dev_addr_hex[0:2], 16)
    except ValueError:
        return {"label": "unknown", "top_byte": None}
    if top_byte in (0x26, 0x27):
        label = "The Things Network"
    elif top_byte in (0x00, 0x01):
        label = "private/experimental"
    else:
        label = "other"
    return {"label": label, "top_byte": top_byte}


# ---------------------------------------------------------------------------
# Join-request parsing (RF-environment survey — F-0006)
# ---------------------------------------------------------------------------


def parse_join_request(phy_payload: bytes) -> Optional[dict]:
    """Parse a Join-Request PHY payload:
    MHDR(1) | JoinEUI(8, LE) | DevEUI(8, LE) | DevNonce(2) | MIC(4) = 23 bytes.

    Returns {"dev_eui", "join_eui"} as big-endian hex strings (the same
    display convention as parse_devaddr), or None if the payload is too
    short/empty. Only meaningful when parse_mhdr(phy_payload) == 0 (a
    join-request) — never raises.
    """
    if not phy_payload or len(phy_payload) < 23:
        return None
    join_eui_le = phy_payload[1:9]
    dev_eui_le = phy_payload[9:17]
    return {
        "dev_eui": dev_eui_le[::-1].hex(),
        "join_eui": join_eui_le[::-1].hex(),
    }


# ---------------------------------------------------------------------------
# Vendor OUI lookup (RF-environment survey — F-0006)
#
# Best-effort — NOT verified against the IEEE OUI registry, just a small,
# hand-curated set for common field-test hardware (Dragino, Milesight are
# reasonably well attested in public product documentation; 70B3D5 is a
# widely shared/reused block, not one vendor). Elsys/Browan/Adeunis/MClimate
# are intentionally NOT guessed here — add their OUIs once confirmed rather
# than risk a wrong vendor label. Unknown OUIs fall back to their raw hex,
# which is the expected common case for a field survey near campus/urban RF.
# ---------------------------------------------------------------------------

_VENDOR_OUIS: dict[str, str] = {
    "70b3d5": "LoRa Alliance shared (70B3D5)",  # large shared/reused block, many vendors
    "a84041": "Dragino",
    "24e124": "Milesight",
}


def vendor_for_oui(oui_hex: str) -> dict:
    """{"name", "oui"} for a DevEUI's first 3 bytes (6 hex chars, lowercase).
    Unknown OUIs fall back to name=f"OUI {oui_hex}" — never raises.
    """
    oui_hex = (oui_hex or "").lower()
    name = _VENDOR_OUIS.get(oui_hex, f"OUI {oui_hex}" if oui_hex else "unknown")
    return {"name": name, "oui": oui_hex}


# ---------------------------------------------------------------------------
# EU868 channel plan
# ---------------------------------------------------------------------------

# EU868 default + optional uplink channels (frequency in Hz → channel index)
_EU868_CHANNELS: dict[int, int] = {
    868100000: 0,
    868300000: 1,
    868500000: 2,
    867100000: 3,
    867300000: 4,
    867500000: 5,
    867700000: 6,
    867900000: 7,
    868800000: 8,  # FSK / extra LoRa
}


def freq_to_channel(freq_hz: int) -> int:
    """Map an EU868 uplink frequency (Hz) to a channel index (0–8).

    Returns -1 for frequencies not in the standard EU868 plan.
    """
    return _EU868_CHANNELS.get(freq_hz, -1)
