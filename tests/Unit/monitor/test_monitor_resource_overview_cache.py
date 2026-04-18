from backend.web.services import resource_cache as cache


def _triage_payload(category: str) -> dict:
    summary = {
        "total": 1,
        "active_drift": 0,
        "detached_residue": 0,
        "orphan_cleanup": 0,
        "healthy_capacity": 0,
    }
    summary[category] = 1
    return {
        "triage": {
            "summary": summary,
            "groups": [{"key": category, "items": [{"lease_id": "lease-1"}]}],
        }
    }


def test_resource_overview_cache_refresh_adds_metadata(monkeypatch):
    cache.clear_resource_overview_cache()
    monkeypatch.setattr(
        cache.resource_projection_service,
        "visible_resource_row_stats",
        lambda: {"local": {"resource_rows": 0, "running": 0}},
    )
    monkeypatch.setattr(
        cache.resource_projection_service,
        "list_resource_providers",
        lambda: {
            "summary": {
                "snapshot_at": "2026-03-03T00:00:00Z",
                "total_providers": 1,
                "active_providers": 1,
                "unavailable_providers": 0,
                "running_sessions": 2,
            },
            "providers": [{"id": "local", "cardCpu": {}}],
        },
    )
    monkeypatch.setattr(
        cache,
        "monitor_service",
        type("_MonitorService", (), {"list_monitor_sandboxes": staticmethod(lambda: _triage_payload("detached_residue"))}),
        raising=False,
    )

    payload = cache.refresh_resource_overview_sync()
    assert payload["summary"]["refresh_status"] == "ok"
    assert payload["summary"]["refresh_error"] is None
    assert payload["summary"]["last_refreshed_at"] == "2026-03-03T00:00:00Z"
    assert payload["triage"]["summary"]["detached_residue"] == 1

    cached = cache.get_resource_overview_snapshot()
    assert cached["providers"][0]["id"] == "local"
    assert cached["triage"]["groups"][0]["key"] == "detached_residue"


def test_resource_overview_cache_refresh_fails_loudly_on_refresh_error(monkeypatch):
    cache.clear_resource_overview_cache()
    monkeypatch.setattr(
        cache.resource_projection_service,
        "visible_resource_row_stats",
        lambda: {"docker": {"resource_rows": 1, "running": 1}},
    )
    monkeypatch.setattr(
        cache.resource_projection_service,
        "list_resource_providers",
        lambda: {
            "summary": {
                "snapshot_at": "2026-03-03T00:00:00Z",
                "total_providers": 1,
                "active_providers": 1,
                "unavailable_providers": 0,
                "running_sessions": 1,
            },
            "providers": [{"id": "docker", "cardCpu": {}}],
        },
    )
    monkeypatch.setattr(
        cache,
        "monitor_service",
        type("_MonitorService", (), {"list_monitor_sandboxes": staticmethod(lambda: _triage_payload("orphan_cleanup"))}),
        raising=False,
    )
    cache.refresh_resource_overview_sync()

    def _raise():
        raise RuntimeError("probe failed")

    monkeypatch.setattr(cache.resource_projection_service, "list_resource_providers", _raise)
    try:
        cache.refresh_resource_overview_sync()
    except RuntimeError as exc:
        assert str(exc) == "probe failed"
    else:
        raise AssertionError("refresh_resource_overview_sync should fail loudly")

    monkeypatch.setattr(
        cache.resource_projection_service,
        "visible_resource_row_stats",
        lambda: {"docker": {"resource_rows": 0, "running": 0}},
    )
    cached = cache.get_resource_overview_snapshot()
    assert cached["providers"][0]["id"] == "docker"
    assert cached["summary"]["refresh_status"] == "ok"
    assert cached["summary"]["refresh_error"] is None
    assert cached["triage"]["groups"][0]["key"] == "orphan_cleanup"


def test_resource_overview_cache_refreshes_when_live_resource_row_counts_drift(monkeypatch):
    cache.clear_resource_overview_cache()

    stale_payload = {
        "summary": {
            "snapshot_at": "2026-03-03T00:00:00Z",
            "total_providers": 1,
            "active_providers": 0,
            "unavailable_providers": 0,
            "running_sessions": 0,
        },
        "providers": [
            {
                "id": "local",
                "cardCpu": {},
                "sessions": [],
                "telemetry": {"running": {"used": 0}},
            }
        ],
    }
    fresh_payload = {
        "summary": {
            "snapshot_at": "2026-03-03T00:01:00Z",
            "total_providers": 1,
            "active_providers": 1,
            "unavailable_providers": 0,
            "running_sessions": 1,
        },
        "providers": [
            {
                "id": "local",
                "cardCpu": {},
                "sessions": [{"id": "lease-1:m_thread"}],
                "telemetry": {"running": {"used": 1}},
            }
        ],
    }

    calls = iter([stale_payload, fresh_payload])
    monkeypatch.setattr(cache.resource_projection_service, "list_resource_providers", lambda: next(calls))
    monkeypatch.setattr(
        cache.resource_projection_service,
        "visible_resource_row_stats",
        lambda: {"local": {"resource_rows": 1, "running": 1}},
    )
    monkeypatch.setattr(
        cache,
        "monitor_service",
        type("_MonitorService", (), {"list_monitor_sandboxes": staticmethod(lambda: _triage_payload("healthy_capacity"))}),
        raising=False,
    )

    cache.refresh_resource_overview_sync()
    payload = cache.get_resource_overview_snapshot()

    assert payload["providers"][0]["telemetry"]["running"]["used"] == 1
    assert len(payload["providers"][0]["sessions"]) == 1
    assert payload["triage"]["summary"]["healthy_capacity"] == 1
