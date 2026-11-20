import pytest

from dotanalyst import opendota


@pytest.fixture(autouse=True)
def no_opendota_pause(monkeypatch):
    """Tests answer OpenDota's calls themselves, so the pause that keeps us under its rate limit only slows them."""
    monkeypatch.setattr(opendota, "PAUSE", 0)
