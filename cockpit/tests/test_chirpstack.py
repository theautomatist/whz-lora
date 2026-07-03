"""test_chirpstack.py — unit tests for chirpstack.py helper functions.

Uses unittest.mock to replace the gRPC stub so these tests run without a
live ChirpStack instance.  Only tests logic in chirpstack.py itself.
"""
from unittest.mock import MagicMock, patch

import pytest
from chirpstack_api.api import device_pb2

from app import chirpstack as cs


# ---------------------------------------------------------------------------
# set_device_profile
# ---------------------------------------------------------------------------


def _make_stub_with_device(dev: device_pb2.Device):
    """Return a mock DeviceServiceStub whose .Get returns *dev*."""
    mock_get_resp = MagicMock()
    mock_get_resp.device = dev
    stub = MagicMock()
    stub.Get.return_value = mock_get_resp
    return stub


def test_set_device_profile_calls_update():
    """set_device_profile must call Update exactly once."""
    original = device_pb2.Device(
        dev_eui="0102030405060708",
        name="sensor-01",
        application_id="app-abc",
        device_profile_id="old-profile-id",
        join_eui="0000000000000000",
    )
    stub = _make_stub_with_device(original)

    with patch("app.chirpstack.device_pb2_grpc.DeviceServiceStub", return_value=stub):
        cs.set_device_profile(MagicMock(), "tok", "0102030405060708", "new-profile-id")

    stub.Update.assert_called_once()


def test_set_device_profile_new_profile_id_in_update():
    """The Update request must carry the new device_profile_id."""
    original = device_pb2.Device(
        dev_eui="0102030405060708",
        name="sensor-01",
        application_id="app-abc",
        device_profile_id="old-profile-id",
        join_eui="0000000000000000",
    )
    stub = _make_stub_with_device(original)

    with patch("app.chirpstack.device_pb2_grpc.DeviceServiceStub", return_value=stub):
        cs.set_device_profile(MagicMock(), "tok", "0102030405060708", "new-profile-id")

    update_req = stub.Update.call_args[0][0]
    assert update_req.device.device_profile_id == "new-profile-id"


def test_set_device_profile_preserves_other_fields():
    """Name, join_eui, application_id must be unchanged after the update."""
    original = device_pb2.Device(
        dev_eui="aaaa000000000001",
        name="vicki-01",
        application_id="app-xyz",
        device_profile_id="profile-adr",
        join_eui="0102030405060708",
    )
    stub = _make_stub_with_device(original)

    with patch("app.chirpstack.device_pb2_grpc.DeviceServiceStub", return_value=stub):
        cs.set_device_profile(MagicMock(), "tok", "aaaa000000000001", "profile-sf9")

    d = stub.Update.call_args[0][0].device
    assert d.device_profile_id == "profile-sf9"    # changed
    assert d.name == "vicki-01"                     # preserved
    assert d.application_id == "app-xyz"            # preserved
    assert d.join_eui == "0102030405060708"          # preserved
    assert d.dev_eui == "aaaa000000000001"           # preserved
