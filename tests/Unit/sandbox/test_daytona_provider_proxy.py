"""Unit tests for Daytona local toolbox URL normalization."""

import sys
from types import ModuleType
from typing import Any, cast

import pytest

from sandbox.providers.daytona import DaytonaProvider


def test_daytona_provider_rewrites_local_toolbox_proxy_url_to_loopback():
    provider = object.__new__(DaytonaProvider)
    provider.api_url = "http://localhost:3986/api"

    rewritten = provider._normalize_toolbox_proxy_url("http://172.18.0.1:4000/toolbox")

    assert rewritten == "http://127.0.0.1:4000/toolbox"


def test_daytona_provider_leaves_remote_toolbox_proxy_url_unchanged():
    provider = object.__new__(DaytonaProvider)
    provider.api_url = "https://daytona.example.com/api"

    untouched = provider._normalize_toolbox_proxy_url("https://proxy.example.com/toolbox")

    assert untouched == "https://proxy.example.com/toolbox"


def test_daytona_provider_passes_target_through_sdk_config(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, object] = {}

    class FakeConfig:
        def __init__(self, *, api_key: str, api_url: str, target: str) -> None:
            self.api_key = api_key
            self.api_url = api_url
            self.target = target

    class FakeClient:
        def __init__(self, config: FakeConfig) -> None:
            captured["config"] = config
            self._get_proxy_toolbox_url = lambda sandbox_id, region_id: "http://proxy/toolbox"

    fake_module = cast(Any, ModuleType("daytona_sdk"))
    fake_module.Daytona = FakeClient
    fake_module.DaytonaConfig = FakeConfig
    monkeypatch.setitem(sys.modules, "daytona_sdk", fake_module)

    provider = DaytonaProvider(api_key="test-key", api_url="http://daytona.test/api", target="self-host")

    config = captured["config"]
    assert getattr(config, "api_key", None) == "test-key"
    assert getattr(config, "api_url", None) == "http://daytona.test/api"
    assert getattr(config, "target", None) == "self-host"
    assert provider.client is not None
