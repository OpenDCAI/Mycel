from backend.web.services import resource_common, resource_projection_service


class _FakeRepo:
    def __init__(self, rows, lease_threads=None, instance_ids=None):
        self._rows = rows
        self._lease_threads = lease_threads or {}
        self._instance_ids = instance_ids or {}

    def list_sessions_with_leases(self):
        return list(self._rows)

    def query_lease_threads(self, lease_id: str):
        return [{"thread_id": tid} for tid in self._lease_threads.get(lease_id, [])]

    def query_lease_instance_id(self, lease_id: str):
        return self._instance_ids.get(lease_id)

    def query_lease_instance_ids(self, lease_ids: list[str]):
        return {lease_id: self._instance_ids.get(lease_id) for lease_id in lease_ids}

    def close(self):
        pass


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def list_by_ids(self, thread_ids: list[str]):
        return [{"id": thread_id, **row} for thread_id, row in self._rows.items() if thread_id in set(thread_ids)]

    def close(self):
        pass


class _FakeUser:
    def __init__(self, user_id: str, display_name: str, avatar: str | None = None):
        self.id = user_id
        self.display_name = display_name
        self.avatar = avatar


class _FakeUserRepo:
    def __init__(self, users):
        self._users = users

    def list_all(self):
        return list(self._users)

    def close(self):
        pass


def _patch_daytona_projection(monkeypatch, repo, owners, *, console_url=None):
    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: repo)
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "daytona_selfhost", "available": True}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: console_url)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (resource_common.empty_capabilities(), None),
    )
    monkeypatch.setattr(resource_projection_service, "_thread_owners", owners)
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})


def test_list_resource_providers_deduplicates_terminal_derived_rows(monkeypatch):
    rows = [
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "observed_state": "running",
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
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (resource_common.empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()
    local = payload["providers"][0]

    assert local["telemetry"]["running"]["used"] == 1
    assert local["sessions"] == [
        {
            "id": "sandbox-1:thread-1",
            "sandboxId": "sandbox-1",
            "leaseId": "lease-1",
            "threadId": "thread-1",
            "agentUserId": "agent-1",
            "agentName": "Toad",
            "avatarUrl": None,
            "status": "running",
            "startedAt": "2026-04-04T00:00:00",
            "metrics": None,
        }
    ]


def test_list_resource_providers_resolves_owner_metadata_from_runtime_storage(monkeypatch):
    rows = [
        {
            "provider": "daytona",
            "session_id": "sess-1",
            "thread_id": "thread-supabase",
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "daytona", "available": True}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (resource_common.empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_common,
        "build_thread_repo",
        lambda **_kwargs: _FakeThreadRepo({"thread-supabase": {"agent_user_id": "agent-1"}}),
    )
    monkeypatch.setattr(
        resource_common,
        "build_user_repo",
        lambda **_kwargs: _FakeUserRepo([_FakeUser("agent-1", "Toad")]),
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()

    assert payload["providers"][0]["sessions"] == [
        {
            "id": "sandbox-1:thread-supabase",
            "sandboxId": "sandbox-1",
            "leaseId": "lease-1",
            "threadId": "thread-supabase",
            "agentUserId": "agent-1",
            "agentName": "Toad",
            "avatarUrl": None,
            "status": "running",
            "startedAt": "2026-04-04T00:00:00",
            "metrics": None,
        }
    ]


def test_list_resource_providers_hides_subagent_threads(monkeypatch):
    rows = [
        {
            "provider": "daytona",
            "session_id": "sess-parent",
            "thread_id": "thread-parent",
            "lease_id": "lease-parent",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "daytona",
            "session_id": "sess-child",
            "thread_id": "subagent-deadbeef",
            "lease_id": "lease-child",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:01",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "daytona", "available": True}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (resource_common.empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"agent_user_id": tid, "agent_name": tid, "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert [session["threadId"] for session in sessions] == ["thread-parent"]
    assert payload["summary"]["running_sessions"] == 1


def test_list_resource_providers_projects_visible_parent_when_raw_monitor_row_is_subagent(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "subagent-deadbeef",
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-04T00:00:00",
        },
    ]

    monkeypatch.setattr(
        resource_projection_service,
        "make_sandbox_monitor_repo",
        lambda: _FakeRepo(rows, lease_threads={"lease-1": ["subagent-deadbeef", "thread-parent"]}),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "available_sandbox_types",
        lambda: [{"name": "daytona_selfhost", "available": True}],
    )
    monkeypatch.setattr(resource_projection_service, "resolve_provider_name", lambda *_args, **_kwargs: "daytona")
    monkeypatch.setattr(resource_projection_service, "_resolve_console_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        resource_projection_service,
        "_resolve_instance_capabilities",
        lambda _config_name: (resource_common.empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"agent_user_id": "agent-1", "agent_name": "Morel", "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert sessions == [
        {
            "id": "sandbox-1:thread-parent",
            "sandboxId": "sandbox-1",
            "leaseId": "lease-1",
            "threadId": "thread-parent",
            "agentUserId": "agent-1",
            "agentName": "Morel",
            "avatarUrl": None,
            "status": "paused",
            "startedAt": "2026-04-04T00:00:00",
            "metrics": None,
        }
    ]


def test_list_resource_providers_deduplicates_same_lease_thread_even_with_distinct_session_ids(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": "sess-a",
            "thread_id": "thread-parent",
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": "sess-b",
            "thread_id": "thread-parent",
            "sandbox_id": "sandbox-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:01",
        },
    ]

    _patch_daytona_projection(
        monkeypatch,
        _FakeRepo(rows),
        lambda thread_ids: {tid: {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": None} for tid in thread_ids},
    )

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert sessions == [
        {
            "id": "sandbox-1:thread-parent",
            "sandboxId": "sandbox-1",
            "leaseId": "lease-1",
            "threadId": "thread-parent",
            "agentUserId": "agent-1",
            "agentName": "Toad",
            "avatarUrl": None,
            "status": "running",
            "startedAt": "2026-04-04T00:00:00",
            "metrics": None,
        }
    ]


def test_list_resource_providers_keeps_remote_runtime_session_id_actor_first(monkeypatch):
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

    _patch_daytona_projection(
        monkeypatch,
        _FakeRepo(rows, instance_ids={"lease-remote": "provider-session-1"}),
        lambda thread_ids: {
            tid: {
                "agent_user_id": "agent-remote",
                "agent_name": "Remote Agent",
                "avatar_url": "/api/users/agent-remote/avatar",
            }
            for tid in thread_ids
        },
        console_url="https://example.com/daytona",
    )

    payload = resource_projection_service.list_resource_providers()
    provider = payload["providers"][0]
    session = provider["sessions"][0]

    assert provider["consoleUrl"] == "https://example.com/daytona"
    assert session["runtimeSessionId"] == "provider-session-1"
    assert session["agentUserId"] == "agent-remote"
    assert session["agentName"] == "Remote Agent"
    assert session["avatarUrl"] == "/api/users/agent-remote/avatar"
    assert "memberId" not in session
    assert "memberName" not in session


def test_list_resource_providers_uses_batch_runtime_lookup_for_remote_leases(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-a",
            "lease_id": "lease-a",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-b",
            "lease_id": "lease-b",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:01",
        },
    ]

    class _BatchOnlyRepo(_FakeRepo):
        def __init__(self):
            super().__init__(rows, instance_ids={"lease-a": "runtime-a", "lease-b": "runtime-b"})
            self.batch_calls: list[list[str]] = []

        def query_lease_instance_id(self, lease_id: str):
            raise AssertionError(f"unexpected per-lease lookup: {lease_id}")

        def query_lease_instance_ids(self, lease_ids: list[str]):
            self.batch_calls.append(list(lease_ids))
            return super().query_lease_instance_ids(lease_ids)

    repo = _BatchOnlyRepo()
    _patch_daytona_projection(
        monkeypatch,
        repo,
        lambda thread_ids: {tid: {"agent_user_id": f"agent-{tid}", "agent_name": tid, "avatar_url": None} for tid in thread_ids},
    )

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert [session["runtimeSessionId"] for session in sessions] == ["runtime-a", "runtime-b"]
    assert repo.batch_calls == [["lease-a", "lease-b"]]
