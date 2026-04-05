"""Unit tests for Daytona local toolbox URL normalization."""

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
