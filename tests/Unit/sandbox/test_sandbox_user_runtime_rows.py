from types import SimpleNamespace

import pytest

from backend.web.services import sandbox_service


def _runtime_row(
    lower_runtime_id: str,
    thread_id: str,
    *,
    provider_name: str = "local",
    recipe_id: str | None = None,
    observed_state: str = "running",
    desired_state: str = "running",
    created_at: str = "2026-04-07T10:00:00Z",
    cwd: str = "/tmp/app",
    sandbox_id: str | None = None,
    **extra,
):
    return {
        "lease_id": lower_runtime_id,
        "sandbox_id": sandbox_id or lower_runtime_id.replace("lease", "sandbox", 1),
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


def _single_agent_repos(*thread_specs: str | tuple[str, dict]):
    rows: dict[str, dict] = {}
    for spec in thread_specs:
        if isinstance(spec, tuple):
            thread_id, extra = spec
            rows[thread_id] = {"agent_user_id": "agent-1", "owner_user_id": "owner-1", **extra}
            continue
        rows[spec] = {"agent_user_id": "agent-1", "owner_user_id": "owner-1"}
    thread_repo = _FakeThreadRepo(rows)
    user_repo = _FakeUserRepo(
        {
            "agent-1": SimpleNamespace(id="agent-1", display_name="Morel", avatar="x", owner_user_id="owner-1"),
        }
    )
    return thread_repo, user_repo


def _agent_user(user_id: str, display_name: str, *, owner_user_id: str, avatar: str | None) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, display_name=display_name, avatar=avatar, owner_user_id=owner_user_id)


class _FakeMonitorRepo:
    def __init__(self, rows, instance_ids=None):
        self._rows = rows
        self._instance_ids = instance_ids or {}
        self.sandbox_instance_id_calls: list[str] = []

    def query_sandboxes(self):
        return list(self._rows)

    def query_sandbox_threads(self, sandbox_id: str):
        return [{"thread_id": row.get("thread_id")} for row in self._rows if row.get("sandbox_id") == sandbox_id]

    def query_sandbox_instance_id(self, sandbox_id: str):
        self.sandbox_instance_id_calls.append(sandbox_id)
        for row in self._rows:
            if row.get("sandbox_id") == sandbox_id:
                return self._instance_ids.get(str(row.get("lease_id") or ""))
        return None

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
    ("rows", "thread_specs", "expected_thread_ids", "expected_agents", "expected_recipe_id"),
    [
        (
            [
                _runtime_row("lease-1", "thread-parent", provider_name="daytona_selfhost", cwd="/home/daytona/files/app"),
                _runtime_row("lease-1", "subagent-deadbeef", provider_name="daytona_selfhost", cwd="/home/daytona/files/app"),
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
            "daytona_selfhost:default",
        ),
        (
            [
                _runtime_row("lease-1", "thread-a"),
                _runtime_row("lease-1", "thread-b"),
            ],
            (
                ("thread-a", {"branch_index": 2, "is_main": False}),
                ("thread-b", {"branch_index": 0, "is_main": True}),
            ),
            ["thread-b"],
            [
                {
                    "thread_id": "thread-b",
                    "agent_user_id": "agent-1",
                    "agent_name": "Morel",
                    "avatar_url": "/api/users/agent-1/avatar",
                },
            ],
            "local:default",
        ),
    ],
    ids=["hide-subagent-threads", "collapse-visible-threads-to-canonical-owner-thread"],
)
def test_user_runtime_rows_visible_thread_contract(
    monkeypatch,
    rows,
    thread_specs,
    expected_thread_ids,
    expected_agents,
    expected_recipe_id,
):
    thread_repo, user_repo = _single_agent_repos(*thread_specs)

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo(rows))

    sandboxes = sandbox_service._list_user_runtime_rows(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert len(sandboxes) == 1
    sandbox = sandboxes[0]
    assert sandbox["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in sandbox
    assert sandbox["thread_ids"] == expected_thread_ids
    assert sandbox["agents"] == expected_agents
    assert sandbox["recipe_id"] == expected_recipe_id


def test_user_runtime_rows_uses_owner_bulk_repo_surfaces(monkeypatch):
    rows = [
        _runtime_row("lease-1", "thread-a"),
        _runtime_row("lease-2", "thread-b", created_at="2026-04-07T10:01:00Z", cwd="/tmp/app2"),
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

    sandboxes = sandbox_service._list_user_runtime_rows(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert [sandbox["sandbox_id"] for sandbox in sandboxes] == ["sandbox-1", "sandbox-2"]
    assert thread_repo.list_by_owner_calls == ["owner-1"]
    assert user_repo.list_by_owner_calls == ["owner-1"]


def test_count_user_visible_sandboxes_by_provider_uses_narrow_owner_surface(monkeypatch):
    rows = [
        _runtime_row("lease-local", "thread-a", provider_name="local"),
        _runtime_row("lease-local-duplicate", "thread-a", provider_name="local", sandbox_id="sandbox-local"),
        _runtime_row("lease-daytona", "thread-b", provider_name="daytona_selfhost"),
        _runtime_row("lease-subagent", "subagent-hidden", provider_name="daytona_selfhost"),
        _runtime_row("lease-other-owner", "thread-other", provider_name="e2b"),
        _runtime_row("lease-destroying", "thread-c", provider_name="docker", desired_state="destroyed"),
    ]

    class _BulkOnlyThreadRepo(_FakeThreadRepo):
        def get_by_id(self, thread_id: str):
            raise AssertionError(f"unexpected per-thread lookup: {thread_id}")

    thread_repo = _BulkOnlyThreadRepo(
        {
            "thread-a": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
            "thread-b": {"agent_user_id": "agent-2", "owner_user_id": "owner-1"},
            "thread-c": {"agent_user_id": "agent-3", "owner_user_id": "owner-1"},
            "thread-other": {"agent_user_id": "agent-4", "owner_user_id": "owner-2"},
        }
    )
    supabase_client = object()
    seen: dict[str, object] = {}

    def _fake_make_sandbox_monitor_repo(**kwargs):
        seen.update(kwargs)
        return _FakeMonitorRepo(rows)

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", _fake_make_sandbox_monitor_repo)

    counts = sandbox_service.count_user_visible_sandboxes_by_provider(
        "owner-1",
        thread_repo=thread_repo,
        supabase_client=supabase_client,
    )

    assert counts == {"local": 1, "daytona_selfhost": 1}
    assert thread_repo.list_by_owner_calls == ["owner-1"]
    assert seen == {"supabase_client": supabase_client}


def test_list_user_sandboxes_returns_user_visible_runtime_fields(monkeypatch):
    rows = [_runtime_row("lease-1", "thread-a", sandbox_id="sandbox-1")]
    thread_repo, user_repo = _single_agent_repos("thread-a")
    monitor_repo = _FakeMonitorRepo(rows)

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: monitor_repo)
    sandboxes = sandbox_service.list_user_sandboxes(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert len(sandboxes) == 1
    sandbox = sandboxes[0]
    assert "lease_id" not in sandbox
    assert sandbox["sandbox_id"] == "sandbox-1"
    assert sandbox["provider_name"] == "local"
    assert sandbox["recipe_id"] == "local:default"
    assert sandbox["recipe_name"] == "Local Default"
    assert sandbox["observed_state"] == "running"
    assert sandbox["desired_state"] == "running"
    assert sandbox["thread_ids"] == ["thread-a"]
    assert sandbox["agents"] == [
        {
            "thread_id": "thread-a",
            "agent_user_id": "agent-1",
            "agent_name": "Morel",
            "avatar_url": "/api/users/agent-1/avatar",
        }
    ]


def test_list_user_sandboxes_does_not_require_lower_runtime_identity(monkeypatch):
    row = _runtime_row("lease-1", "thread-a", sandbox_id="sandbox-1")
    row.pop("lease_id")
    thread_repo, user_repo = _single_agent_repos("thread-a")
    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: _FakeMonitorRepo([row]))

    sandboxes = sandbox_service.list_user_sandboxes(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert len(sandboxes) == 1
    assert sandboxes[0]["sandbox_id"] == "sandbox-1"
    assert "lease_id" not in sandboxes[0]


def test_count_user_visible_sandboxes_by_provider_does_not_require_lower_runtime_identity(monkeypatch):
    row = _runtime_row("lease-1", "thread-a", sandbox_id="sandbox-1")
    row.pop("lease_id")
    thread_repo = _FakeThreadRepo(
        {
            "thread-a": {"agent_user_id": "agent-1", "owner_user_id": "owner-1"},
        }
    )
    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda **kwargs: _FakeMonitorRepo([row]))

    counts = sandbox_service.count_user_visible_sandboxes_by_provider(
        "owner-1",
        thread_repo=thread_repo,
    )

    assert counts == {"local": 1}


@pytest.mark.parametrize(
    (
        "rows",
        "include_runtime_session_id",
        "instance_ids",
        "expected_runtime_session_id",
        "expected_sandbox_calls",
    ),
    [
        (
            [
                _runtime_row("lease-1", "thread-a", sandbox_id="sandbox-1"),
                _runtime_row("lease-1", "thread-b", created_at="2026-04-07T10:00:01Z", sandbox_id="sandbox-1"),
            ],
            True,
            {"lease-1": "provider-session-1", "sandbox-1": "provider-session-1"},
            "provider-session-1",
            ["sandbox-1"],
        ),
        (
            [
                _runtime_row(
                    "lease-1",
                    "thread-parent",
                    sandbox_id="sandbox-1",
                    provider_name="daytona_selfhost",
                    recipe_id="daytona:default",
                    cwd="/home/daytona/files/app",
                    current_instance_id="provider-session-inline",
                )
            ],
            True,
            {"lease-1": "provider-session-probed", "sandbox-1": "provider-session-probed"},
            "provider-session-inline",
            [],
        ),
        (
            [
                _runtime_row(
                    "lease-1",
                    "thread-parent",
                    sandbox_id="sandbox-1",
                    provider_name="daytona_selfhost",
                    recipe_id="daytona:default",
                    cwd="/home/daytona/files/app",
                )
            ],
            True,
            {"lease-1": "provider-session-1", "sandbox-1": "provider-session-1"},
            "provider-session-1",
            ["sandbox-1"],
        ),
        (
            [
                _runtime_row(
                    "lease-1",
                    "thread-parent",
                    sandbox_id="sandbox-1",
                    provider_name="daytona_selfhost",
                    recipe_id="daytona:default",
                    cwd="/home/daytona/files/app",
                )
            ],
            False,
            {"lease-1": "provider-session-1", "sandbox-1": "provider-session-1"},
            None,
            [],
        ),
    ],
    ids=["probe-once-per-sandbox", "prefer-inline-instance-id", "keep-runtime-session-id", "skip-probe-by-default"],
)
def test_user_runtime_rows_runtime_session_id_contract(
    monkeypatch,
    rows,
    include_runtime_session_id,
    instance_ids,
    expected_runtime_session_id,
    expected_sandbox_calls,
):
    monitor_repo = _FakeMonitorRepo(rows, instance_ids=instance_ids)
    thread_ids = tuple(str(row["thread_id"]) for row in rows)
    thread_repo, user_repo = _single_agent_repos(*thread_ids)

    monkeypatch.setattr(sandbox_service, "make_sandbox_monitor_repo", lambda: monitor_repo)

    sandboxes = sandbox_service._list_user_runtime_rows(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
        include_runtime_session_id=include_runtime_session_id,
    )

    sandbox = sandboxes[0]
    if expected_runtime_session_id is None:
        assert "runtime_session_id" not in sandbox
    else:
        assert sandbox["runtime_session_id"] == expected_runtime_session_id
    assert monitor_repo.sandbox_instance_id_calls == expected_sandbox_calls


def test_user_runtime_rows_keeps_detached_but_hides_destroying_runtimes(monkeypatch):
    rows = [
        _runtime_row("lease-running", "thread-running", cwd="/tmp/running"),
        _runtime_row(
            "lease-paused",
            "thread-paused",
            provider_name="daytona_selfhost",
            recipe_id="daytona:default",
            observed_state="paused",
            desired_state="paused",
            created_at="2026-04-07T10:01:00Z",
            cwd="/home/daytona/app",
        ),
        _runtime_row(
            "lease-detached",
            "thread-detached",
            observed_state="detached",
            desired_state="running",
            created_at="2026-04-07T10:02:00Z",
            cwd="/tmp/stale",
        ),
        _runtime_row(
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

    sandboxes = sandbox_service._list_user_runtime_rows(
        "owner-1",
        thread_repo=thread_repo,
        user_repo=user_repo,
    )

    assert [sandbox["sandbox_id"] for sandbox in sandboxes] == ["sandbox-running", "sandbox-paused", "sandbox-detached"]
