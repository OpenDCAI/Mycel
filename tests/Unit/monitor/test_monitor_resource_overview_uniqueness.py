import pytest

from backend.web.services import resource_common, resource_projection_service
from storage import runtime as storage_runtime


class _FakeRepo:
    def __init__(self, rows, lease_threads=None, sandbox_threads=None, instance_ids=None):
        self._rows = rows
        self._lease_threads = lease_threads or {}
        self._sandbox_threads = sandbox_threads or {}
        self._instance_ids = instance_ids or {}

    def query_resource_sessions(self):
        return list(self._rows)

    def query_lease_threads(self, lease_id: str):
        return [{"thread_id": tid} for tid in self._lease_threads.get(lease_id, [])]

    def query_sandbox_threads(self, sandbox_id: str):
        return [{"thread_id": tid} for tid in self._sandbox_threads.get(sandbox_id, [])]

    def query_lease_instance_id(self, lease_id: str):
        return self._instance_ids.get(lease_id)

    def query_lease_instance_ids(self, lease_ids: list[str]):
        return {lease_id: self._instance_ids.get(lease_id) for lease_id in lease_ids}

    def query_sandbox_instance_ids(self, sandbox_ids: list[str]):
        return {sandbox_id: self._instance_ids.get(sandbox_id) for sandbox_id in sandbox_ids}

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
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})


def test_storage_runtime_no_longer_exposes_lease_shaped_snapshot_read_shell() -> None:
    assert not hasattr(storage_runtime, "list_resource_snapshots")


def test_list_resource_providers_no_longer_uses_lease_shaped_row_source_shell(monkeypatch) -> None:
    class _Repo(_FakeRepo):
        def list_sessions_with_leases(self):
            raise AssertionError("resource projection should not use list_sessions_with_leases as row-source shell")

    _patch_daytona_projection(
        monkeypatch,
        _Repo(
            [
                {
                    "provider": "daytona_selfhost",
                    "session_id": "sess-1",
                    "thread_id": "thread-1",
                    "sandbox_id": "sandbox-1",
                    "lease_id": "lease-1",
                    "observed_state": "running",
                    "desired_state": "running",
                    "created_at": "2026-04-04T00:00:00",
                }
            ],
            instance_ids={"sandbox-1": "provider-session-1"},
        ),
        lambda thread_ids: {tid: {"agent_user_id": "agent-1", "agent_name": "Toad", "avatar_url": None} for tid in thread_ids},
    )

    payload = resource_projection_service.list_resource_providers()

    assert payload["providers"][0]["sessions"][0]["id"] == "sandbox-1:thread-1"


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
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

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
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

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
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

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
        lambda: _FakeRepo(rows, sandbox_threads={"sandbox-1": ["subagent-deadbeef", "thread-parent"]}),
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
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

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


def test_list_resource_providers_uses_canonical_sandbox_thread_fallback(monkeypatch):
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

    class _SandboxThreadOnlyRepo(_FakeRepo):
        def query_lease_threads(self, lease_id: str):
            raise AssertionError(f"unexpected lease-shaped visible-thread fallback: {lease_id}")

    monkeypatch.setattr(
        resource_projection_service,
        "make_sandbox_monitor_repo",
        lambda: _SandboxThreadOnlyRepo(rows, sandbox_threads={"sandbox-1": ["subagent-deadbeef", "thread-parent"]}),
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
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

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


def test_list_resource_providers_no_longer_uses_lease_shaped_visible_thread_fallback_without_sandbox_id(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "subagent-deadbeef",
            "sandbox_id": None,
            "lease_id": "lease-1",
            "observed_state": "paused",
            "desired_state": "paused",
            "created_at": "2026-04-04T00:00:00",
        },
    ]

    class _NoLeaseFallbackRepo(_FakeRepo):
        def query_lease_threads(self, lease_id: str):
            raise AssertionError(f"lease-shaped visible-thread fallback should be gone: {lease_id}")

    monkeypatch.setattr(
        resource_projection_service,
        "make_sandbox_monitor_repo",
        lambda: _NoLeaseFallbackRepo(rows),
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
    monkeypatch.setattr(resource_projection_service, "_thread_owners", lambda _thread_ids: {})
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

    payload = resource_projection_service.list_resource_providers()

    assert payload["providers"][0]["sessions"] == []
    assert payload["summary"]["running_sessions"] == 0


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
            "sandbox_id": "sandbox-remote",
            "lease_id": "lease-remote",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
    ]

    _patch_daytona_projection(
        monkeypatch,
        _FakeRepo(rows, instance_ids={"sandbox-remote": "provider-session-1"}),
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
            "sandbox_id": "sandbox-a",
            "lease_id": "lease-a",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-b",
            "sandbox_id": "sandbox-b",
            "lease_id": "lease-b",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:01",
        },
    ]

    class _BatchOnlyRepo(_FakeRepo):
        def __init__(self):
            super().__init__(rows, instance_ids={"sandbox-a": "runtime-a", "sandbox-b": "runtime-b"})
            self.batch_calls: list[list[str]] = []

        def query_lease_instance_id(self, lease_id: str):
            raise AssertionError(f"unexpected per-lease lookup: {lease_id}")

        def query_lease_instance_ids(self, lease_ids: list[str]):
            raise AssertionError(f"unexpected lease batch lookup: {lease_ids}")

        def query_sandbox_instance_ids(self, sandbox_ids: list[str]):
            self.batch_calls.append(list(sandbox_ids))
            return super().query_sandbox_instance_ids(sandbox_ids)

    repo = _BatchOnlyRepo()
    _patch_daytona_projection(
        monkeypatch,
        repo,
        lambda thread_ids: {tid: {"agent_user_id": f"agent-{tid}", "agent_name": tid, "avatar_url": None} for tid in thread_ids},
    )

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert [session["runtimeSessionId"] for session in sessions] == ["runtime-a", "runtime-b"]
    assert repo.batch_calls == [["sandbox-a", "sandbox-b"]]


def test_visible_resource_session_stats_uses_sandbox_keyed_runtime_lookup(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-a",
            "sandbox_id": "sandbox-a",
            "lease_id": "lease-a",
            "observed_state": "detached",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
    ]

    class _BatchOnlyRepo(_FakeRepo):
        def __init__(self):
            super().__init__(rows, instance_ids={"sandbox-a": "runtime-a"})

        def query_lease_instance_ids(self, lease_ids: list[str]):
            raise AssertionError(f"unexpected lease batch lookup: {lease_ids}")

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _BatchOnlyRepo())
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots_by_sandbox", lambda _sessions: {})

    stats = resource_projection_service.visible_resource_session_stats()

    assert stats == {"daytona_selfhost": {"sessions": 1, "running": 1}}


def test_list_resource_snapshots_by_sandbox_requires_repo_sandbox_wrapper(monkeypatch):
    sessions = [
        {
            "sandbox_id": "sandbox-a",
            "lease_id": "lease-a",
        },
        {
            "sandbox_id": "sandbox-b",
            "lease_id": "lease-b",
        },
    ]

    class _LeaseOnlyRepo:
        def close(self):
            return None

        def list_snapshots_by_lease_ids(self, lease_ids):
            raise AssertionError("lease-shaped snapshot read shell should not remain an active runtime bridge")

    monkeypatch.setattr(storage_runtime, "build_resource_snapshot_repo", lambda **_kwargs: _LeaseOnlyRepo())

    with pytest.raises(RuntimeError, match="sandbox-shaped snapshot repo read requires list_snapshots_by_sandbox_ids"):
        storage_runtime.list_resource_snapshots_by_sandbox(sessions)


def test_list_resource_snapshots_by_sandbox_prefers_repo_sandbox_wrapper(monkeypatch):
    sessions = [
        {
            "sandbox_id": "sandbox-a",
            "lease_id": "lease-a",
        },
    ]

    class _SandboxWrappedRepo:
        def close(self):
            return None

        def list_snapshots_by_sandbox_ids(self, items):
            assert items == sessions
            return {"sandbox-a": {"lease_id": "lease-a", "cpu_used": 11}}

        def list_snapshots_by_lease_ids(self, _lease_ids):
            raise AssertionError("lease-keyed snapshot read should not be the active path")

    monkeypatch.setattr(storage_runtime, "build_resource_snapshot_repo", lambda **_kwargs: _SandboxWrappedRepo())

    snapshot_by_sandbox = storage_runtime.list_resource_snapshots_by_sandbox(sessions)

    assert snapshot_by_sandbox == {"sandbox-a": {"lease_id": "lease-a", "cpu_used": 11}}


def test_list_resource_providers_passes_sandbox_keyed_snapshots_to_provider_telemetry(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-a",
            "sandbox_id": "sandbox-a",
            "lease_id": "lease-a",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
    ]

    _patch_daytona_projection(
        monkeypatch,
        _FakeRepo(rows),
        lambda thread_ids: {tid: {"agent_user_id": f"agent-{tid}", "agent_name": tid, "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(
        resource_projection_service,
        "list_resource_snapshots_by_sandbox",
        lambda _sessions: {"sandbox-a": {"sandbox_id": "sandbox-a", "cpu_used": 11}},
    )

    captured: dict[str, object] = {}

    def _fake_aggregate_provider_telemetry(*, provider_sessions, running_count, snapshot_by_sandbox):
        captured["provider_sessions"] = provider_sessions
        captured["running_count"] = running_count
        captured["snapshot_keys"] = sorted(snapshot_by_sandbox.keys())
        return {
            "running": {"used": running_count},
            "cpu": {"used": 11},
            "memory": {"used": None},
            "disk": {"used": None},
        }

    monkeypatch.setattr(resource_projection_service, "_aggregate_provider_telemetry", _fake_aggregate_provider_telemetry)

    payload = resource_projection_service.list_resource_providers()

    assert captured["snapshot_keys"] == ["sandbox-a"]
    assert payload["providers"][0]["telemetry"]["cpu"]["used"] == 11


def test_load_visible_resource_runtime_uses_sandbox_snapshot_wrapper(monkeypatch):
    rows = [
        {
            "provider": "daytona_selfhost",
            "session_id": None,
            "thread_id": "thread-a",
            "sandbox_id": "sandbox-a",
            "lease_id": "lease-a",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-08T00:00:00",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
    monkeypatch.setattr(
        resource_projection_service,
        "list_resource_snapshots_by_sandbox",
        lambda sessions: {"sandbox-a": {"sandbox_id": "sandbox-a", "cpu_used": 11}},
    )

    sessions, runtime_session_ids, snapshot_by_lease, snapshot_by_sandbox = resource_projection_service._load_visible_resource_runtime()

    assert [session["sandbox_id"] for session in sessions] == ["sandbox-a"]
    assert runtime_session_ids == {"sandbox-a": None}
    assert snapshot_by_lease == {}
    assert snapshot_by_sandbox == {"sandbox-a": {"sandbox_id": "sandbox-a", "cpu_used": 11}}
