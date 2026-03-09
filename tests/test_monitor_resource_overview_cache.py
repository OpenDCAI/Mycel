from backend.web.services import resource_cache as cache


def test_resource_overview_cache_refresh_adds_metadata(monkeypatch):
    cache.clear_resource_overview_cache()
    monkeypatch.setattr(
        cache.resource_service,
        "list_resource_providers",
        lambda: {
            "summary": {
                "snapshot_at": "2026-03-03T00:00:00Z",
                "total_providers": 1,
                "active_providers": 1,
                "unavailable_providers": 0,
                "running_sessions": 2,
            },
            "providers": [{"id": "local"}],
        },
    )

    payload = cache.refresh_resource_overview_sync()
    assert payload["summary"]["refresh_status"] == "ok"
    assert payload["summary"]["refresh_error"] is None
    assert payload["summary"]["last_refreshed_at"] == "2026-03-03T00:00:00Z"

    cached = cache.get_resource_overview_snapshot()
    assert cached["providers"][0]["id"] == "local"


def test_resource_overview_cache_keeps_last_snapshot_on_refresh_error(monkeypatch):
    cache.clear_resource_overview_cache()
    monkeypatch.setattr(
        cache.resource_service,
        "list_resource_providers",
        lambda: {
            "summary": {
                "snapshot_at": "2026-03-03T00:00:00Z",
                "total_providers": 1,
                "active_providers": 1,
                "unavailable_providers": 0,
                "running_sessions": 1,
            },
            "providers": [{"id": "docker"}],
        },
    )
    cache.refresh_resource_overview_sync()

    def _raise():
        raise RuntimeError("probe failed")

    monkeypatch.setattr(cache.resource_service, "list_resource_providers", _raise)
    degraded = cache.refresh_resource_overview_sync()
    assert degraded["providers"][0]["id"] == "docker"
    assert degraded["summary"]["refresh_status"] == "error"
    assert degraded["summary"]["refresh_error"] == "probe failed"
