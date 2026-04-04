"""Tests for Daytona sandbox provider."""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DAYTONA_API_KEY"),
    reason="DAYTONA_API_KEY not set",
)


class TestDaytonaProvider:
    """Test Daytona provider basic functionality."""

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
