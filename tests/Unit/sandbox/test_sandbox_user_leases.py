from types import SimpleNamespace

import pytest

from backend.web.services import sandbox_service

def _lease_row(
    lease_id: str,
    thread_id: str,
    *,
    provider_name: str = "local",
    recipe_id: str | None = None,
    observed_state: str = "running",
    desired_state: str = "running",
    created_at: str = "2026-04-07T10:00:00Z",
    cwd: str = "/tmp/app",
    **extra,
):
    return {
        "lease_id": lease_id,
        "provider_name": provider_name,
        "recipe_id": recipe_id or f"{provider_name}:default",
        "recipe_json": None,
        "observed_state": observed_state,
        "desired_state": desired_state,
        "created_at": created_at,
        "cwd": cwd,
        "thread_id": thread_id,
        **extra,
    }


def _single_agent_repos(*thread_ids: str):
    thread_repo = _FakeThreadRepo(
        {
            thread_id: {"agent_user_id": "agent-1", "owner_user_id": "owner-1"}
            for thread_id in thread_ids
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )
    return thread_repo, user_repo


def _agent_user(user_id: str, display_name: str, *, owner_user_id: str, avatar: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, display_name=display_name, avatar=avatar, owner_user_id=owner_user_id)


def _assert_daytona_recipe(lease: dict, *, runtime_session_id: str | None = None) -> None:
    assert lease["recipe_id"] == "daytona:default"
    assert lease["recipe_name"] == "Daytona Default"
    assert lease["recipe"]["id"] == "daytona:default"
    assert lease["recipe"]["provider_type"] == "daytona"
    if runtime_session_id is None:
        assert "runtime_session_id" not in lease
    else:
        assert lease["runtime_session_id"] == runtime_session_id


class _FakeMonitorRepo:
    def __init__(self, rows, instance_ids=None):
        self._rows = rows
        self._instance_ids = instance_ids or {}
        self.instance_id_calls: list[str] = []

    def list_leases_with_threads(self):
        return list(self._rows)

    def query_lease_instance_id(self, lease_id: str):
        self.instance_id_calls.append(lease_id)
        return self._instance_ids.get(lease_id)

    def query_lease(self, lease_id: str):
        for row in self._rows:
            if row.get("lease_id") == lease_id:
                return dict(row)
        return None

    def query_lease_threads(self, lease_id: str):
        return [{"thread_id": row.get("thread_id")} for row in self._rows if row.get("lease_id") == lease_id]

    def close(self):
        pass


class _FakeThreadRepo:
    def __init__(self, rows):
        self._rows = rows
        self.list_by_owner_calls: list[str] = []

    def get_by_id(self, thread_id: str):
        return self._rows.get(thread_id)

    def list_by_owner_user_id(self, owner_user_id: str):
        self.list_by_owner_calls.append(owner_user_id)
        result = []
        for thread_id, row in self._rows.items():
            if row.get("owner_user_id") == owner_user_id:
                result.append({"id": thread_id, **row})
        return result

    def close(self):
        pass


class _FakeUserRepo:
    def __init__(self, rows):
        self._rows = rows
        self.list_by_owner_calls: list[str] = []

    def get_by_id(self, user_id: str):
        return self._rows.get(user_id)

    def list_by_owner_user_id(self, owner_user_id: str):
        self.list_by_owner_calls.append(owner_user_id)
        return [row for row in self._rows.values() if getattr(row, "owner_user_id", None) == owner_user_id]

    def close(self):
        pass


@pytest.mark.parametrize(
    ("rows", "thread_ids", "expected_thread_ids", "expected_agents"),
    [
        (
            [
                _lease_row("lease-1", "thread-parent", provider_name="daytona_selfhost", cwd="/home/daytona/files/app"),
                _lease_row("lease-1", "subagent-deadbeef", provider_name="daytona_selfhost", cwd="/home/daytona/files/app"),
            ],
            ("thread-parent", "subagent-deadbeef"),
            ["thread-parent"],
            [
                {
                    "thread_id": "thread-parent",
                    "agent_user_id": "agent-1",
                    "agent_name": "Morel",
                    "avatar_url": "/api/users/agent-1/avatar",
                }
            ],
        ),
        (
            [
                _lease_row("lease-1", "thread-a"),
                _lease_row("lease-1", "thread-b"),
            ],
            ("thread-a", "thread-b"),
            ["thread-a", "thread-b"],
            [
                {
                    "thread_id": "thread-a",
                    "agent_user_id": "agent-1",
                    "agent_name": "Morel",
                    "avatar_url": "/api/users/agent-1/avatar",
                },
                {
                    "thread_id": "thread-b",
                    "agent_user_id": "agent-1",
                    "agent_name": "Morel",
                    "avatar_url": "/api/users/agent-1/avatar",
                },
            ],
        ),
    ],
    ids=["hide-subagent-threads", "keep-distinct-visible-threads"],
)
def test_list_user_leases_visible_thread_contract(monkeypatch, rows, thread_ids, expected_thread_ids, expected_agents):
    thread_repo, user_repo = _single_agent_repos(*thread_ids)

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert len(leases) == 1
    lease = leases[0]
    assert lease["lease_id"] == "lease-1"
    assert lease["thread_ids"] == expected_thread_ids
    assert lease["agents"] == expected_agents
    _assert_daytona_recipe(lease)


def test_list_user_leases_uses_owner_bulk_repo_surfaces(monkeypatch):
    rows = [
        _lease_row("lease-1", "thread-a"),
        _lease_row("lease-2", "thread-b", created_at="2026-04-07T10:01:00Z", cwd="/tmp/app2"),
    ]

    class _BulkOnlyThreadRepo(_FakeThreadRepo):
        def get_by_id(self, thread_id: str):
            raise AssertionError(f"unexpected per-thread lookup: {thread_id}")

    class _BulkOnlyUserRepo(_FakeUserRepo):
        def get_by_id(self, user_id: str):
            raise AssertionError(f"unexpected per-user lookup: {user_id}")

    thread_repo = _BulkOnlyThreadRepo(
        {
            "thread-a": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-b": {"agent_user_id": "agent-2", "owner_user_id": "owner-1"},
        }
    )
    user_repo = _BulkOnlyUserRepo(
        {
            "agent-1": _agent_user("agent-1", "Morel", avatar="x", owner_user_id="owner-1"),
            "agent-2": _agent_user("agent-2", "Toad", avatar=None, owner_user_id="owner-1"),
        }
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert [lease["lease_id"] for lease in leases] == ["lease-1", "lease-2"]
    assert thread_repo.list_by_owner_calls == ["owner-1"]
    assert user_repo.list_by_owner_calls == ["owner-1"]


@pytest.mark.parametrize(
    ("rows", "include_runtime_session_id", "instance_ids", "expected_runtime_session_id", "expected_calls"),
    [
        (
            [
                _lease_row("lease-1", "thread-a"),
                _lease_row("lease-1", "thread-b", created_at="2026-04-07T10:00:01Z"),
            ],
            True,
            {"lease-1": "provider-session-1"},
            "provider-session-1",
            ["lease-1"],
        ),
        (
            [
                _lease_row(
                    "lease-1",
                    "thread-parent",
                    provider_name="daytona_selfhost",
                    recipe_id="daytona:default",
                    cwd="/home/daytona/files/app",
                    current_instance_id="provider-session-inline",
                )
            ],
            True,
            {"lease-1": "provider-session-probed"},
            "provider-session-inline",
            [],
        ),
        (
            [
                _lease_row(
                    "lease-1",
                    "thread-parent",
                    provider_name="daytona_selfhost",
                    recipe_id="daytona:default",
                    cwd="/home/daytona/files/app",
                )
            ],
            True,
            {"lease-1": "provider-session-1"},
            "provider-session-1",
            ["lease-1"],
        ),
        (
            [
                _lease_row(
                    "lease-1",
                    "thread-parent",
                    provider_name="daytona_selfhost",
                    recipe_id="daytona:default",
                    cwd="/home/daytona/files/app",
                )
            ],
            False,
            {"lease-1": "provider-session-1"},
            None,
            [],
        ),
    ],
    ids=["probe-once-per-lease", "prefer-inline-instance-id", "keep-runtime-session-id", "skip-probe-by-default"],
)
def test_list_user_leases_runtime_session_id_contract(
    monkeypatch,
    rows,
    include_runtime_session_id,
    instance_ids,
    expected_runtime_session_id,
    expected_calls,
):
    monitor_repo = _FakeMonitorRepo(rows, instance_ids=instance_ids)
    thread_ids = tuple(str(row["thread_id"]) for row in rows)
    thread_repo, user_repo = _single_agent_repos(*thread_ids)

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: monitor_repo)

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=include_runtime_session_id,
    )

    lease = leases[0]
    if expected_runtime_session_id is None:
        assert "runtime_session_id" not in lease
    else:
        assert lease["runtime_session_id"] == expected_runtime_session_id
    assert monitor_repo.instance_id_calls == expected_calls


def test_resolve_owned_lease_filters_to_single_authorized_lease(monkeypatch):
    rows = [
        _lease_row("lease-1", "thread-parent", provider_name="daytona_selfhost", cwd="/home/daytona/files/app"),
        _lease_row("lease-2", "thread-other", created_at="2026-04-07T10:01:00Z", cwd="/tmp/other"),
    ]
    thread_repo = _FakeThreadRepo(
        {
            "thread-parent": {"agent_user_id": "agent-1"},
            "thread-other": {"agent_user_id": "agent-2"},
        }
    )
    user_repo = _FakeUserRepo(
        {
            "agent-1": _agent_user("agent-1", "Morel", avatar="x", owner_user_id="owner-1"),
            "agent-2": _agent_user("agent-2", "Toad", avatar=None, owner_user_id="owner-2"),
        }
    )

    monkeypatch.setattr(
        sandbox_service,
        "make_sandbox_monitor_repo",
        lambda: _FakeMonitorRepo(rows, instance_ids={"lease-1": "provider-session-1"}),
    )

    lease = sandbox_service.resolve_owned_lease(
        "owner-1",
        "lease-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert lease is not None
    assert lease["lease_id"] == "lease-1"
    assert lease["provider_name"] == "daytona_selfhost"
    assert lease["observed_state"] == "running"
    assert lease["desired_state"] == "running"
    assert lease["created_at"] == "2026-04-07T10:00:00Z"
    assert lease["cwd"] == "/home/daytona/files/app"
    assert lease["thread_id"] == "thread-parent"
    assert lease["thread_ids"] == ["thread-parent"]
    assert lease["agents"] == [
        {
            "thread_id": "thread-parent",
            "agent_user_id": "agent-1",
            "agent_name": "Morel",
            "avatar_url": "/api/users/agent-1/avatar",
        }
    ]
    _assert_daytona_recipe(lease, runtime_session_id="provider-session-1")


def test_list_user_leases_keeps_detached_but_hides_destroying_leases(monkeypatch):
    rows = [
        _lease_row("lease-running", "thread-running", cwd="/tmp/running"),
        _lease_row(
            "lease-paused",
            "thread-paused",
            provider_name="daytona_selfhost",
            recipe_id="daytona:default",
            observed_state="paused",
            desired_state="paused",
            created_at="2026-04-07T10:01:00Z",
            cwd="/home/daytona/app",
        ),
        _lease_row(
            "lease-detached",
            "thread-detached",
            observed_state="detached",
            desired_state="running",
            created_at="2026-04-07T10:02:00Z",
            cwd="/tmp/stale",
        ),
        _lease_row(
            "lease-destroying",
            "thread-destroying",
            observed_state="paused",
            desired_state="destroyed",
            created_at="2026-04-07T10:03:00Z",
            cwd="/tmp/destroying",
        ),
    ]
    thread_repo, user_repo = _single_agent_repos(
        "thread-running",
        "thread-paused",
        "thread-detached",
        "thread-destroying",
    )

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    leases = sandbox_service.list_user_leases(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert [lease["lease_id"] for lease in leases] == ["lease-running", "lease-paused", "lease-detached"]
