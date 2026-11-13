"""
PitchPulse 2026 - Pytest Test Isolation & Fixtures
Resets rate-limiting buckets and cache between test runs to prevent state bleed.
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("STAFF_SECRET_TOKEN", "fifa-staff-secure-2026")
os.environ.setdefault("GEMINI_API_KEY", "ci-mock-key-not-used")
os.environ.setdefault("ALLOWED_ORIGIN", "http://localhost:8000")

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.utils.cache import _CACHE
from src.utils.security import _CLIENT_REQUESTS


@pytest.fixture(autouse=True)
def reset_test_state():
    """Autouse fixture resetting in-memory rate limiter and TTL cache before and after every test."""
    _CACHE.clear()
    _CLIENT_REQUESTS.clear()
    yield
    _CACHE.clear()
    _CLIENT_REQUESTS.clear()


@pytest.fixture
def client():
    """Provides a fresh FastAPI test client."""
    with TestClient(app) as test_client:
        yield test_client
