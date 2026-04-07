from backend.web.services import resource_projection_service


class _FakeRepo:
    def __init__(self, rows):
        self._rows = rows

    def list_sessions_with_leases(self):
        return list(self._rows)

    def query_lease_threads(self, lease_id: str):
        return []

    def close(self):
        pass


def _caps(*, metrics: bool = False) -> dict[str, bool]:
    caps = resource_projection_service._empty_capabilities()
    caps["metrics"] = metrics
    return caps


def test_list_resource_providers_keeps_local_card_without_host_metrics(monkeypatch):
    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo([]))
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "local", "available": True}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "local")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (_caps(metrics=True), None),
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})
    monkeypatch.setattr(resource_projection_service, "_thread_owners", lambda _thread_ids: {})
    monkeypatch.setattr(resource_projection_service.LocalSessionProvider, "get_metrics", lambda self, _session_id: None)

    payload = resource_projection_service.list_resource_providers()
    local = payload["providers"][0]

    assert payload["summary"]["total_providers"] == 1
    assert local["id"] == "local"
    assert local["status"] == "ready"
    assert local["sessions"] == []
    assert isinstance(local["cardCpu"], dict)
    assert local["cardCpu"]["used"] is None
    assert local["cardCpu"]["limit"] is None


def test_list_resource_providers_keeps_unavailable_remote_card_with_reason(monkeypatch):
    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo([]))
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [
            {"name": "local", "available": True},
            {"name": "daytona_selfhost", "available": False, "reason": "provider unavailable in current process"},
        ],
    )
    monkeypatch.setattr(
        resource_projection_service,
        "resolve_provider_name",
        lambda config_name, **_kwargs: "local" if config_name == "local" else "daytona",
    )
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (_caps(metrics=False), None),
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})
    monkeypatch.setattr(resource_projection_service, "_thread_owners", lambda _thread_ids: {})
    monkeypatch.setattr(resource_projection_service.LocalSessionProvider, "get_metrics", lambda self, _session_id: None)

    payload = resource_projection_service.list_resource_providers()
    providers = {provider["id"]: provider for provider in payload["providers"]}
    remote = providers["daytona_selfhost"]

    assert "local" in providers
    assert remote["status"] == "unavailable"
    assert remote["unavailableReason"] == "provider unavailable in current process"
    assert remote["sessions"] == []
    assert isinstance(remote["cardCpu"], dict)
