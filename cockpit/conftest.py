"""conftest.py — import path, and a data directory that is never the real one.

Two jobs:

1. Put `cockpit/` on `sys.path` so tests can `from app.lorawan import ...`.

2. Point every data path at a per-test temporary directory.

The second one is not housekeeping. `config.DATA_DIR` defaults to `/data`,
and a large part of the suite never overrode it. On Linux that is a
root-owned path, so 35 tests failed with `PermissionError: /data` the first
time the suite ran in CI. On Windows the same string resolves to a
drive-relative `C:\\data`, which Python creates happily — so the tests
passed locally while quietly writing run CSVs into the root of the
developer's system drive, going back months.

Two environments, two different wrong behaviours, no failure either way.
An autouse fixture is the right level for this: it cannot be forgotten by
the next test that needs to write something, which is exactly how the gap
appeared in the first place.
"""
import os
import sys

import pytest

# Allow `from app.lorawan import ...` in tests
sys.path.insert(0, os.path.dirname(__file__))


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Redirect every configured data path into this test's tmp_path.

    Patched on the `config` module rather than via the environment, because
    `config` reads the environment once at import time — by the time a test
    runs, setting `DATA_DIR` in `os.environ` would change nothing.

    Tests that set their own paths still win: monkeypatch applies in order,
    so a later `monkeypatch.setattr(config, "FLOORPLANS_DIR", ...)` inside a
    test simply overrides this one.
    """
    from app import config

    data_dir = tmp_path / "data"
    photos = data_dir / "photos"
    floorplans = data_dir / "floorplans"
    for d in (data_dir, photos, floorplans):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config, "DATA_DIR", str(data_dir), raising=False)
    monkeypatch.setattr(config, "DB_PATH", str(data_dir / "cockpit.db"), raising=False)
    monkeypatch.setattr(config, "PHOTOS_DIR", str(photos), raising=False)
    monkeypatch.setattr(config, "FLOORPLANS_DIR", str(floorplans), raising=False)
    yield
