from backend.web.services import resource_common, resource_projection_service


class _FakeRepo:
    def __init__(self, rows, lease_threads=None):
        self._rows = rows
        self._lease_threads = lease_threads or {}

    def list_sessions_with_leases(self):
        return list(self._rows)

    def query_lease_threads(self, lease_id: str):
        return [{"thread_id": tid} for tid in self._lease_threads.get(lease_id, [])]

    def close(self):
        pass


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def close(self):
        pass


class _FakeMember:
    def __init__(self, member_id: str, name: str, avatar: str | None = None):
        self.id = member_id
        self.name = name
        self.avatar = avatar


class _FakeMemberRepo:
    def __init__(self, members):
        self._members = members

    def list_all(self):
        return list(self._members)

    def close(self):
        pass


def test_list_resource_providers_deduplicates_terminal_fallback_rows(monkeypatch):
    rows = [
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "local",
            "session_id": None,
            "thread_id": "thread-1",
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
        lambda _config_name: (resource_projection_service._empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"member_id": "member-1", "member_name": "Toad", "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()
    local = payload["providers"][0]

    assert local["telemetry"]["running"]["used"] == 1
    assert local["sessions"] == [
        {
            "id": "lease-1:thread-1",
            "leaseId": "lease-1",
            "threadId": "thread-1",
            "memberName": "Toad",
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
        lambda _config_name: (resource_projection_service._empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_common,
        "build_thread_repo",
        lambda **_kwargs: _FakeThreadRepo({"thread-supabase": {"member_id": "member-1"}}),
    )
    monkeypatch.setattr(
        resource_common,
        "build_member_repo",
        lambda **_kwargs: _FakeMemberRepo([_FakeMember("member-1", "Toad")]),
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()

    assert payload["providers"][0]["sessions"] == [
        {
            "id": "lease-1:thread-supabase",
            "leaseId": "lease-1",
            "threadId": "thread-supabase",
            "memberName": "Toad",
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
        lambda _config_name: (resource_projection_service._empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"member_id": tid, "member_name": tid, "avatar_url": None} for tid in thread_ids},
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
        lambda _config_name: (resource_projection_service._empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"member_id": "member-1", "member_name": "Morel", "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert sessions == [
        {
            "id": "lease-1:thread-parent",
            "leaseId": "lease-1",
            "threadId": "thread-parent",
            "memberName": "Morel",
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
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:00",
        },
        {
            "provider": "daytona_selfhost",
            "session_id": "sess-b",
            "thread_id": "thread-parent",
            "lease_id": "lease-1",
            "observed_state": "running",
            "desired_state": "running",
            "created_at": "2026-04-04T00:00:01",
        },
    ]

    monkeypatch.setattr(resource_projection_service, "make_sandbox_monitor_repo", lambda: _FakeRepo(rows))
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
        lambda _config_name: (resource_projection_service._empty_capabilities(), None),
    )
    monkeypatch.setattr(
        resource_projection_service,
        "_thread_owners",
        lambda thread_ids: {tid: {"member_id": "member-1", "member_name": "Toad", "avatar_url": None} for tid in thread_ids},
    )
    monkeypatch.setattr(resource_projection_service, "list_resource_snapshots", lambda _lease_ids: {})

    payload = resource_projection_service.list_resource_providers()
    sessions = payload["providers"][0]["sessions"]

    assert sessions == [
        {
            "id": "lease-1:thread-parent",
            "leaseId": "lease-1",
            "threadId": "thread-parent",
            "memberName": "Toad",
            "avatarUrl": None,
            "status": "running",
            "startedAt": "2026-04-04T00:00:00",
            "metrics": None,
        }
    ]
