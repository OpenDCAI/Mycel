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


def test_list_resource_providers_inherits_desired_state_for_detached_sessions(monkeypatch):
    rows = [
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
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
        lambda _config_name: (_caps(metrics=False), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})
    monkeypatch.setattr(resource_projection_service.LocalSessionProvider, "get_metrics", lambda self, _session_id: None)

    payload = resource_projection_service.list_resource_providers()

    assert payload["providers"][0]["sessions"][0]["status"] == "running"
    assert payload["providers"][0]["sessions"][0]["agentName"] == "Toad"
    assert payload["summary"]["running_sessions"] == 1


def test_list_resource_providers_keeps_sessions_under_unavailable_provider(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-2",
            "lease_id": "lease-2",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-04T00:00:01",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "daytona_selfhost", "available": False, "reason": "provider unavailable in current process"}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (_caps(metrics=False), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {
            tid: {"agent_user_id": f"agent-{tid}", "agent_name": tid, "avatar_url": None} for tid in thread_ids
        },
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})
    monkeypatch.setattr(resource_projection_service.LocalSessionProvider, "get_metrics", lambda self, _session_id: None)

    payload = resource_projection_service.list_resource_providers()
    provider = payload["providers"][0]

    assert provider["status"] == "unavailable"
    assert provider["unavailableReason"] == "provider unavailable in current process"
    assert [session["leaseId"] for session in provider["sessions"]] == ["lease-1", "lease-2"]
    assert [session["status"] for session in provider["sessions"]] == ["running", "paused"]
    assert [session["agentName"] for session in provider["sessions"]] == ["thread-1", "thread-2"]
    assert payload["summary"]["running_sessions"] == 1


def test_list_resource_providers_keeps_remote_session_actor_first(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": "provider-session-1",
            "thread_id": "thread-remote",
            "lease_id": "lease-remote",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "daytona_selfhost", "available": False, "reason": "provider unavailable in current process"}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (_caps(metrics=False), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {
            tid: {"agent_user_id": "agent-remote", "agent_name": "Remote Agent", "avatar_url": None}
            for tid in thread_ids
        },
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})
    monkeypatch.setattr(resource_projection_service.LocalSessionProvider, "get_metrics", lambda self, _session_id: None)

    payload = resource_projection_service.list_resource_providers()
    session = payload["providers"][0]["sessions"][0]

    assert payload["providers"][0]["status"] == "unavailable"
    assert session == {
        "id": "lease-remote:thread-remote",
        "leaseId": "lease-remote",
        "threadId": "thread-remote",
        "agentUserId": "agent-remote",
        "agentName": "Remote Agent",
        "avatarUrl": None,
        "status": "running",
        "startedAt": "2026-04-08T00:00:00",
        "metrics": None,
    }
    assert "memberId" not in session
    assert "memberName" not in session
