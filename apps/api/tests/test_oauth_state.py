from datetime import datetime, timezone

import pytest

from app.integration_routes import _oauth_state, _verify_oauth_state
from app.config import settings

def test_oauth_state_round_trip():
    state = _oauth_state("tenant-1", "youtube")
    assert _verify_oauth_state(state) == ("tenant-1", "youtube")

def test_oauth_state_expiry(monkeypatch):
    original = settings.oauth_state_ttl_seconds
    try:
        settings.oauth_state_ttl_seconds = 0
        state = _oauth_state("tenant-1", "youtube")
        with pytest.raises(Exception):
            _verify_oauth_state(state)
    finally:
        settings.oauth_state_ttl_seconds = original
