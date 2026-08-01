"""conftest.py — add cockpit/ to sys.path so tests can import app.* directly."""
import os
import sys

# Allow `from app.lorawan import ...` in tests
sys.path.insert(0, os.path.dirname(__file__))
