"""Tests for Daytona sandbox provider."""

import os
from types import SimpleNamespace

import pytest


class _MissingDaytonaVolumeError(Exception):
    status = 404


class _BoomError(Exception):
    status = 500


class _FakeVolumeClient:
    def __init__(self, get_error: Exception | None = None):
        self.get_error = get_error
        self.deleted = []

    def get(self, backend_ref: str):
        if self.get_error:
            raise self.get_error
        return SimpleNamespace(id=backend_ref)

    def delete(self, volume) -> None:
        self.deleted.append(volume)


class TestDaytonaProvider:
    """Test Daytona provider basic functionality."""

    pytestmark = pytest.mark.skipif(
        not os.getenv("DAYTONA_API_KEY"),
        reason="DAYTONA_API_KEY not set",
    )

    def test_import(self):
        """Test that Daytona provider can be imported."""
        from sandbox.providers.daytona import DaytonaProvider

        assert DaytonaProvider.name == "daytona"

    def test_create_provider(self):
        """Test creating a Daytona provider instance."""
        from sandbox.providers.daytona import DaytonaProvider

        api_key = os.getenv("DAYTONA_API_KEY")
        provider = DaytonaProvider(api_key=api_key)
        assert provider.name == "daytona"
        assert provider.api_key == api_key


def test_delete_managed_volume_ignores_missing_daytona_volume():
    from sandbox.providers.daytona import DaytonaProvider

    provider = object.__new__(DaytonaProvider)
    volume = _FakeVolumeClient(get_error=_MissingDaytonaVolumeError("missing"))
    provider.client = SimpleNamespace(volume=volume)

    provider.delete_managed_volume("leon-volume-lease-missing")

    assert volume.deleted == []


def test_delete_managed_volume_reraises_non_missing_daytona_error():
    from sandbox.providers.daytona import DaytonaProvider

    provider = object.__new__(DaytonaProvider)
    provider.client = SimpleNamespace(volume=_FakeVolumeClient(get_error=_BoomError("boom")))

    with pytest.raises(_BoomError):
        provider.delete_managed_volume("leon-volume-lease-boom")
