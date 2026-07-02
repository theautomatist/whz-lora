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
