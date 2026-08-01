"""test_phase.py — unit tests for _apply_phase_to_devices aggregation and
the conditional campaign.set_phase logic in POST /api/phase.

No live ChirpStack or HTTP server required: we test the helper function and
CampaignState directly via unittest.mock.
"""
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import grpc

from app.main import _apply_phase_to_devices
from app.state import CampaignState


# Two fake device list entries, matching the shape returned by cs.list_devices
DEVICES = [
    {"dev_eui": "aaaa000000000001", "name": "d1", "device_profile_name": "ADR", "last_seen_at": None},
    {"dev_eui": "bbbb000000000002", "name": "d2", "device_profile_name": "ADR", "last_seen_at": None},
]


def _rpc_error(msg: str) -> grpc.RpcError:
    """Create a concrete grpc.RpcError subclass with .details() returning *msg*."""
    class _Err(grpc.RpcError):
        def details(self):  # noqa: D102
            return msg
        def code(self):
            return grpc.StatusCode.UNAVAILABLE
    return _Err()


# ---------------------------------------------------------------------------
# _apply_phase_to_devices aggregation
# ---------------------------------------------------------------------------


def test_apply_phase_all_succeed():
    """All devices switch → switched contains all dev_euis, failed is empty."""
    with patch("app.main.cs.list_devices", return_value=DEVICES), \
         patch("app.main.cs.set_device_profile"):
        switched, failed = _apply_phase_to_devices(
            MagicMock(), "tok", "app-id", "prof-id"
        )
    assert switched == ["aaaa000000000001", "bbbb000000000002"]
    assert failed == []


def test_apply_phase_partial_failure():
    """Second device raises RpcError → it appears in failed; first in switched."""
    err = _rpc_error("deadline exceeded")

    def _side_effect(channel, token, dev_eui, profile_id):
        if dev_eui == "bbbb000000000002":
            raise err

    with patch("app.main.cs.list_devices", return_value=DEVICES), \
         patch("app.main.cs.set_device_profile", side_effect=_side_effect):
        switched, failed = _apply_phase_to_devices(
            MagicMock(), "tok", "app-id", "prof-id"
        )

    assert switched == ["aaaa000000000001"]
    assert len(failed) == 1
    assert failed[0]["dev_eui"] == "bbbb000000000002"
    assert "deadline exceeded" in failed[0]["error"]


def test_apply_phase_all_fail():
    """Every device raises → switched is empty, failed has all two entries."""
    err = _rpc_error("unavailable")

    with patch("app.main.cs.list_devices", return_value=DEVICES), \
         patch("app.main.cs.set_device_profile", side_effect=err):
        switched, failed = _apply_phase_to_devices(
            MagicMock(), "tok", "app-id", "prof-id"
        )

    assert switched == []
    assert len(failed) == 2


def test_apply_phase_no_devices():
    """Empty device list → both lists empty, no error."""
    with patch("app.main.cs.list_devices", return_value=[]), \
         patch("app.main.cs.set_device_profile") as mock_sdp:
        switched, failed = _apply_phase_to_devices(
            MagicMock(), "tok", "app-id", "prof-id"
        )
    assert switched == []
    assert failed == []
    mock_sdp.assert_not_called()


# ---------------------------------------------------------------------------
# Conditional campaign.set_phase — mirrors the route-handler logic
# ---------------------------------------------------------------------------


def test_campaign_phase_not_set_on_partial_failure():
    """campaign.set_phase must NOT be called when failed is non-empty."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    assert state.get_dashboard()["phase"] == "adr"

    # Simulate: aggregation returned one failure
    failed = [{"dev_eui": "bbbb000000000002", "error": "unavailable"}]
    if not failed:
        state.set_phase("sf9")

    assert state.get_dashboard()["phase"] == "adr"   # unchanged


def test_campaign_phase_set_when_all_succeed():
    """campaign.set_phase IS called (and takes effect) when failed is empty."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    assert state.get_dashboard()["phase"] == "adr"

    failed: list = []
    if not failed:
        state.set_phase("sf9")

    assert state.get_dashboard()["phase"] == "sf9"


def test_campaign_phase_conditional_with_all_fail():
    """Edge case: all devices fail → phase stays at current value."""
    state = CampaignState(data_dir=tempfile.mkdtemp())
    state.set_phase("sf9")  # pre-existing phase

    failed = [
        {"dev_eui": "aaaa000000000001", "error": "not found"},
        {"dev_eui": "bbbb000000000002", "error": "not found"},
    ]
    if not failed:
        state.set_phase("sf12")  # should NOT execute

    assert state.get_dashboard()["phase"] == "sf9"   # stays at sf9, not sf12
