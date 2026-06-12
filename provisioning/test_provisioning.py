"""
test_provisioning.py — stdlib unittest for provisioning.py logic.

Uses a fake DeviceServiceStub that records calls and can raise a fake
grpc.RpcError without a live ChirpStack connection.

Run with:
  python -m unittest provisioning/test_provisioning.py
  # or from within the provisioning/ directory:
  python -m unittest test_provisioning
"""

import os
import sys
import threading
import types
import unittest

import grpc

# ---------------------------------------------------------------------------
# Path setup — allow imports from this file's directory and from scripts/
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.join(_HERE, "..", "scripts")
for _p in (_HERE, _SCRIPTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# Fake gRPC error
# ---------------------------------------------------------------------------

class _FakeRpcError(grpc.RpcError):
    """Minimal grpc.RpcError stand-in that returns a fixed StatusCode."""

    def __init__(self, code: grpc.StatusCode, details: str = "fake"):
        self._code = code
        self._details = details

    def code(self) -> grpc.StatusCode:
        return self._code

    def details(self) -> str:
        return self._details


# ---------------------------------------------------------------------------
# Fake protobuf-like objects
# ---------------------------------------------------------------------------

def _device_keys_obj(nwk_key: str, app_key: str = "0" * 32):
    """Return a simple namespace mimicking DeviceKeys."""
    return types.SimpleNamespace(nwk_key=nwk_key, app_key=app_key)


def _device_activation_obj(dev_addr: str = ""):
    return types.SimpleNamespace(dev_addr=dev_addr)


def _device_list_item(dev_eui: str, name: str = "test", has_last_seen: bool = False,
                      dev_addr: str = ""):
    """
    Return a fake DeviceListItem.

    HasField("last_seen_at") mirrors the protobuf sentinel.
    """
    item = types.SimpleNamespace(
        dev_eui=dev_eui,
        name=name,
        _has_last_seen=has_last_seen,
        _dev_addr=dev_addr,
    )
    item.HasField = lambda field: item._has_last_seen if field == "last_seen_at" else False
    if has_last_seen:
        import datetime
        ts = types.SimpleNamespace(seconds=0, nanos=0)
        item.last_seen_at = ts
    return item


# ---------------------------------------------------------------------------
# Fake DeviceServiceStub
# ---------------------------------------------------------------------------

class _FakeDeviceStub:
    """
    Records all calls and can be configured to raise on specific methods.
    """

    def __init__(self):
        self.calls: list = []          # list of (method_name, request)
        self._raise_on: dict = {}      # method_name -> exception to raise
        self._stored_keys = None       # set by CreateKeys, read by GetKeys

    def _record(self, name, req):
        self.calls.append((name, req))

    def _maybe_raise(self, name):
        exc = self._raise_on.get(name)
        if exc is not None:
            raise exc

    def raise_on(self, method: str, exc: Exception):
        self._raise_on[method] = exc

    # --- device CRUD -------------------------------------------------------

    def Get(self, req, metadata=None):
        self._record("Get", req)
        self._maybe_raise("Get")
        return types.SimpleNamespace(device=types.SimpleNamespace(dev_eui=req.dev_eui))

    def Create(self, req, metadata=None):
        self._record("Create", req)
        self._maybe_raise("Create")
        return types.SimpleNamespace()

    def Delete(self, req, metadata=None):
        self._record("Delete", req)
        self._maybe_raise("Delete")
        return types.SimpleNamespace()

    # --- key management ----------------------------------------------------

    def CreateKeys(self, req, metadata=None):
        self._record("CreateKeys", req)
        self._maybe_raise("CreateKeys")
        self._stored_keys = req.device_keys
        return types.SimpleNamespace()

    def GetKeys(self, req, metadata=None):
        self._record("GetKeys", req)
        self._maybe_raise("GetKeys")
        if self._stored_keys is None:
            # Mirror ChirpStack: a device with no keys yet → NOT_FOUND.
            raise _FakeRpcError(grpc.StatusCode.NOT_FOUND)
        return types.SimpleNamespace(device_keys=self._stored_keys)

    def UpdateKeys(self, req, metadata=None):
        self._record("UpdateKeys", req)
        self._maybe_raise("UpdateKeys")
        self._stored_keys = req.device_keys
        return types.SimpleNamespace()

    # --- activation / metrics ----------------------------------------------

    def GetActivation(self, req, metadata=None):
        self._record("GetActivation", req)
        self._maybe_raise("GetActivation")
        return types.SimpleNamespace(
            device_activation=_device_activation_obj()
        )

    def List(self, req, metadata=None):
        self._record("List", req)
        self._maybe_raise("List")
        return types.SimpleNamespace(result=[], total_count=0)


# ---------------------------------------------------------------------------
# Helpers — patch provisioning module's internals to avoid live gRPC calls
# ---------------------------------------------------------------------------

import provisioning as prov


def _make_patched_stub(fake_stub):
    """
    Return a context manager that replaces _resolve_ids and DeviceServiceStub
    with controlled fakes for the duration of the with-block.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        orig_resolve = prov._resolve_ids
        orig_get_meta = prov._get_meta
        # Patch _get_meta to return (None, []) — channel/meta not used by fake stub.
        prov._get_meta = lambda: (None, [])
        # Patch _resolve_ids to return fixed IDs.
        prov._resolve_ids = lambda channel, meta: ("tenant-1", "app-1", "profile-1")

        # Patch DeviceServiceStub inside provisioning module.
        import chirpstack_api.api.device_pb2_grpc as _dg
        orig_stub_cls = _dg.DeviceServiceStub
        _dg.DeviceServiceStub = lambda channel: fake_stub

        try:
            yield fake_stub
        finally:
            prov._get_meta = orig_get_meta
            prov._resolve_ids = orig_resolve
            _dg.DeviceServiceStub = orig_stub_cls

    return _ctx()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProvisionDeviceKeyMapping(unittest.TestCase):
    """(a) nwk_key == appkey, app_key == '0'*32 (LoRaWAN 1.0.x inversion)."""

    def test_nwk_key_is_appkey_app_key_is_zeros(self):
        app_key = "deadbeefdeadbeefdeadbeefdeadbeef"
        fake = _FakeDeviceStub()
        # Device does not exist yet → Get raises NOT_FOUND → Create is called.
        fake.raise_on("Get", _FakeRpcError(grpc.StatusCode.NOT_FOUND))

        with _make_patched_stub(fake):
            status = prov.provision_device(
                dev_eui="0102030405060708",
                name="test-device",
                join_eui="0000000000000000",
                app_key=app_key,
            )

        self.assertEqual(status, "created")
        # Find the CreateKeys call and assert key values.
        create_keys_calls = [c for c in fake.calls if c[0] == "CreateKeys"]
        self.assertEqual(len(create_keys_calls), 1)
        keys = create_keys_calls[0][1].device_keys
        self.assertEqual(keys.nwk_key, app_key)
        self.assertEqual(keys.app_key, "0" * 32)


class TestProvisionDeviceKeysFallback(unittest.TestCase):
    """(b) Existing device with different stored keys → GetKeys then UpdateKeys."""

    def test_update_keys_when_stored_keys_differ(self):
        app_key = "aabbccddeeff00112233445566778899"
        fake = _FakeDeviceStub()
        # Device already exists → Get succeeds. Stored keys differ from the
        # submitted appkey → GetKeys returns the mismatch and UpdateKeys must
        # be called. CreateKeys must NOT be called (GetKeys-first).
        fake._stored_keys = _device_keys_obj("0" * 32)

        with _make_patched_stub(fake):
            status = prov.provision_device(
                dev_eui="0102030405060708",
                name="test-device",
                join_eui="0000000000000000",
                app_key=app_key,
            )

        self.assertEqual(status, "keys-updated")
        method_names = [c[0] for c in fake.calls]
        self.assertIn("GetKeys", method_names)
        self.assertIn("UpdateKeys", method_names)
        self.assertNotIn("CreateKeys", method_names)


class TestProvisionDeviceExistsStatus(unittest.TestCase):
    """(c) Re-provision where stored keys already equal appkey → 'exists', no write."""

    def test_no_write_when_keys_already_match(self):
        app_key = "aabbccddeeff00112233445566778899"
        fake = _FakeDeviceStub()
        # Device exists; GetKeys returns the same key → no Create, no Update.
        fake._stored_keys = _device_keys_obj(app_key)  # already matches

        with _make_patched_stub(fake):
            status = prov.provision_device(
                dev_eui="0102030405060708",
                name="test-device",
                join_eui="0000000000000000",
                app_key=app_key,
            )

        self.assertEqual(status, "exists")
        method_names = [c[0] for c in fake.calls]
        self.assertIn("GetKeys", method_names)
        self.assertNotIn("UpdateKeys", method_names)
        self.assertNotIn("CreateKeys", method_names)


class TestDeviceStateLogic(unittest.TestCase):
    """(d) Three-state precedence: last_seen_at → online; dev_addr → joined; else provisioned."""

    def _state(self, has_last_seen: bool, dev_addr: str = "") -> str:
        """Run _device_state with a controlled fake stub and item."""
        item = _device_list_item(
            dev_eui="0102030405060708",
            has_last_seen=has_last_seen,
            dev_addr=dev_addr,
        )

        fake = _FakeDeviceStub()

        if dev_addr:
            fake.GetActivation = lambda req, metadata=None: types.SimpleNamespace(
                device_activation=_device_activation_obj(dev_addr)
            )
        else:
            fake.GetActivation = lambda req, metadata=None: types.SimpleNamespace(
                device_activation=_device_activation_obj("")
            )

        result = prov._device_state(fake, [], item)
        return result["state"]

    def test_last_seen_at_present_is_online(self):
        self.assertEqual(self._state(has_last_seen=True), "online")

    def test_no_last_seen_with_dev_addr_is_joined(self):
        self.assertEqual(self._state(has_last_seen=False, dev_addr="01020304"), "joined")

    def test_no_last_seen_no_dev_addr_is_provisioned(self):
        self.assertEqual(self._state(has_last_seen=False, dev_addr=""), "provisioned")

    def test_last_seen_takes_precedence_over_dev_addr(self):
        """online wins even if a dev_addr is somehow present."""
        self.assertEqual(self._state(has_last_seen=True, dev_addr="01020304"), "online")


class TestProvisionDeviceConcurrency(unittest.TestCase):
    """Thread-safety: concurrent calls must not corrupt the cache."""

    def test_concurrent_provision_does_not_raise(self):
        """
        Fire 10 threads each calling provision_device.  The test verifies
        no exception escapes (races would surface as AttributeError or
        KeyError on the shared _cache).
        """
        app_key = "deadbeefdeadbeefdeadbeefdeadbeef"
        errors = []

        def _worker():
            try:
                fake = _FakeDeviceStub()
                fake.raise_on("Get", _FakeRpcError(grpc.StatusCode.NOT_FOUND))
                with _make_patched_stub(fake):
                    prov.provision_device(
                        dev_eui="0102030405060708",
                        name="t",
                        join_eui="0000000000000000",
                        app_key=app_key,
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Unexpected errors: {errors}")


if __name__ == "__main__":
    unittest.main()
