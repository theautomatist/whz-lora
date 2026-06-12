"""
validators.py — pure validation and parsing helpers for the provisioning app.

No external dependencies; all tests in test_validators.py use stdlib unittest.
"""

import csv
import io
import re

# ---------------------------------------------------------------------------
# Hex normalisation and validation
# ---------------------------------------------------------------------------

_HEX_STRIP_RE = re.compile(r"[\s:\-]")


def normalise_hex(s: str) -> str:
    """Strip spaces, colons and hyphens, then lower-case."""
    return _HEX_STRIP_RE.sub("", s).lower()


def valid_eui(s: str) -> str:
    """
    Validate and return a normalised 8-byte (16 hex char) EUI string.

    Raises ValueError with the offending value if invalid.
    """
    norm = normalise_hex(s)
    if len(norm) != 16 or not all(c in "0123456789abcdef" for c in norm):
        raise ValueError(
            f"Invalid EUI {s!r}: expected 16 hex characters (got {norm!r})"
        )
    return norm


def valid_appkey(s: str) -> str:
    """
    Validate and return a normalised 16-byte (32 hex char) AppKey string.

    Raises ValueError with the offending value if invalid.
    """
    norm = normalise_hex(s)
    if len(norm) != 32 or not all(c in "0123456789abcdef" for c in norm):
        raise ValueError(
            f"Invalid AppKey {s!r}: expected 32 hex characters (got {norm!r})"
        )
    return norm


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

# Accepted column name aliases (lower-cased, stripped).
_COL_ALIASES = {
    "dev_eui": "dev_eui",
    "deveui": "dev_eui",
    "eui": "dev_eui",
    "app_key": "app_key",
    "appkey": "app_key",
    "application_key": "app_key",
    "join_eui": "join_eui",
    "joineui": "join_eui",
    "appeui": "join_eui",
    "app_eui": "join_eui",
    "name": "name",
    "device_name": "name",
    "class": "class",
    "device_class": "class",
    "lorawan_class": "class",
}

_DEFAULT_JOIN_EUI = "0000000000000000"
_DEFAULT_CLASS = "A"


def parse_csv(text: str) -> list:
    """
    Parse a CSV string into a list of per-row results.

    Each element is either:
      {"ok": True, "data": {"dev_eui": ..., "app_key": ..., "join_eui": ...,
                            "name": ..., "class": ...}}
    or:
      {"ok": False, "error": "<human-readable message>", "row": <raw dict>}

    Accepts a header row; tolerates column order; case-insensitive headers.
    Required columns: dev_eui, app_key.
    Optional columns: join_eui (default "0000000000000000"), name (default =
    dev_eui), class (default "A").
    """
    reader = csv.DictReader(io.StringIO(text.strip()))
    if reader.fieldnames is None:
        return []

    # Map actual header names to canonical names.
    col_map = {}
    for raw_col in reader.fieldnames:
        canonical = _COL_ALIASES.get(raw_col.strip().lower())
        if canonical:
            col_map[raw_col] = canonical

    results = []
    for raw_row in reader:
        # Remap columns.
        row = {col_map[k]: v.strip() for k, v in raw_row.items() if k in col_map}

        if "dev_eui" not in row or not row["dev_eui"]:
            results.append(
                {"ok": False, "error": "Missing required column: dev_eui", "row": dict(raw_row)}
            )
            continue
        if "app_key" not in row or not row["app_key"]:
            results.append(
                {"ok": False, "error": "Missing required column: app_key", "row": dict(raw_row)}
            )
            continue

        try:
            dev_eui = valid_eui(row["dev_eui"])
        except ValueError as exc:
            results.append({"ok": False, "error": str(exc), "row": dict(raw_row)})
            continue

        try:
            app_key = valid_appkey(row["app_key"])
        except ValueError as exc:
            results.append({"ok": False, "error": str(exc), "row": dict(raw_row)})
            continue

        join_eui_raw = row.get("join_eui", _DEFAULT_JOIN_EUI) or _DEFAULT_JOIN_EUI
        try:
            join_eui = valid_eui(join_eui_raw)
        except ValueError as exc:
            results.append({"ok": False, "error": str(exc), "row": dict(raw_row)})
            continue

        name = row.get("name", "") or dev_eui

        raw_class = (row.get("class", _DEFAULT_CLASS) or _DEFAULT_CLASS).strip().upper()
        if raw_class not in ("", "A"):
            results.append(
                {
                    "ok": False,
                    "error": (
                        f"Class {raw_class} / non-A not supported in v1 "
                        "(battery Class A only)"
                    ),
                    "row": dict(raw_row),
                }
            )
            continue
        device_class = "A"

        results.append(
            {
                "ok": True,
                "data": {
                    "dev_eui": dev_eui,
                    "app_key": app_key,
                    "join_eui": join_eui,
                    "name": name,
                    "class": device_class,
                },
            }
        )

    return results
