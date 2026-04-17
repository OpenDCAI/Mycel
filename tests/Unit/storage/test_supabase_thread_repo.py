import pytest

from storage.providers.supabase.thread_repo import SupabaseThreadRepo
from tests.fakes.supabase import FakeSupabaseClient


class _FakeTable:
    def __init__(self) -> None:
        self.insert_payload = None
        self.update_payload = None
        self.eq_calls: list[tuple[str, object]] = []
        self.in_calls: list[tuple[str, list[str]]] = []
        self.rows = [
            {
                "id": "thread-1",
                "agent_user_id": "agent-1",
                "sandbox_type": "local",
                "model": None,
                "cwd": None,
                "status": "active",
                "is_main": 1,
                "branch_index": 0,
                "created_at": 1.0,
                "updated_at": None,
                "last_active_at": None,
            }
        ]

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def in_(self, key, values):
        self.in_calls.append((key, list(values)))
        return self

    def execute(self):
        rows = self.rows
        for key, value in self.eq_calls:
            rows = [row for row in rows if row.get(key) == value]
        if self.in_calls:
            key, values = self.in_calls[-1]
            rows = [row for row in rows if row.get(key) in values]
        return type("Resp", (), {"data": rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.table_obj = _FakeTable()

    def schema(self, _name):
        return self

    def table(self, _name):
        return self.table_obj


def test_supabase_thread_repo_create_writes_integer_main_flag():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        agent_user_id="agent-1",
        sandbox_type="local",
        created_at=1.0,
        is_main=True,
        branch_index=0,
        owner_user_id="owner-1",
        current_workspace_id="workspace-1",
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["is_main"] == 1


def test_supabase_thread_repo_create_defaults_active_status():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        agent_user_id="agent-1",
        sandbox_type="local",
        created_at=1.0,
        is_main=True,
        branch_index=0,
        owner_user_id="owner-1",
        current_workspace_id="workspace-1",
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["status"] == "active"


def test_supabase_thread_repo_create_serializes_epoch_timestamps_for_agent_schema():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        agent_user_id="agent-1",
        sandbox_type="local",
        created_at=1.25,
        updated_at=2.5,
        last_active_at=3.75,
        is_main=True,
        branch_index=0,
        owner_user_id="owner-1",
        current_workspace_id="workspace-1",
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["created_at"] == "1970-01-01T00:00:01.250000+00:00"
    assert client.table_obj.insert_payload["updated_at"] == "1970-01-01T00:00:02.500000+00:00"
    assert client.table_obj.insert_payload["last_active_at"] == "1970-01-01T00:00:03.750000+00:00"


def test_supabase_thread_repo_create_defaults_updated_at_to_created_at_for_agent_schema():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        agent_user_id="agent-1",
        sandbox_type="local",
        created_at=1.25,
        is_main=True,
        branch_index=0,
        owner_user_id="owner-1",
        current_workspace_id="workspace-1",
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["created_at"] == "1970-01-01T00:00:01.250000+00:00"
    assert client.table_obj.insert_payload["updated_at"] == "1970-01-01T00:00:01.250000+00:00"
    assert client.table_obj.insert_payload["last_active_at"] is None


def test_supabase_thread_repo_create_uses_agent_user_id_not_member_id() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        agent_user_id="agent-1",
        sandbox_type="local",
        created_at=1.0,
        is_main=True,
        branch_index=0,
        owner_user_id="owner-1",
        current_workspace_id="workspace-1",
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["agent_user_id"] == "agent-1"
    assert "member_id" not in client.table_obj.insert_payload


def test_supabase_thread_repo_create_writes_current_workspace_id() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.create(
        thread_id="thread-1",
        agent_user_id="agent-1",
        sandbox_type="local",
        created_at=1.0,
        is_main=True,
        branch_index=0,
        owner_user_id="owner-1",
        current_workspace_id="workspace-1",
    )

    assert client.table_obj.insert_payload is not None
    assert client.table_obj.insert_payload["current_workspace_id"] == "workspace-1"


def test_supabase_thread_repo_create_requires_current_workspace_id() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    with pytest.raises(TypeError):
        repo.create(
            thread_id="thread-1",
            agent_user_id="agent-1",
            sandbox_type="local",
            created_at=1.0,
            is_main=True,
            branch_index=0,
            owner_user_id="owner-1",
        )


def test_supabase_thread_repo_create_rejects_blank_current_workspace_id() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    with pytest.raises(ValueError, match="current_workspace_id is required"):
        repo.create(
            thread_id="thread-1",
            agent_user_id="agent-1",
            sandbox_type="local",
            created_at=1.0,
            is_main=True,
            branch_index=0,
            owner_user_id="owner-1",
            current_workspace_id="   ",
        )


def test_supabase_thread_repo_create_requires_explicit_owner_user_id() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    with pytest.raises(TypeError):
        repo.create(
            thread_id="thread-1",
            agent_user_id="agent-1",
            sandbox_type="local",
            created_at=1.0,
            is_main=True,
            branch_index=0,
            current_workspace_id="workspace-1",
        )


def test_supabase_thread_repo_update_writes_model_only():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.update("thread-1", model="openai/gpt-5.4")

    assert client.table_obj.update_payload is not None
    assert client.table_obj.update_payload == {"model": "openai/gpt-5.4"}


def test_supabase_thread_repo_get_default_thread_reads_by_agent_user_and_main_flag():
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    result = repo.get_default_thread("agent-1")

    assert result is not None
    assert result["id"] == "thread-1"
    assert ("agent_user_id", "agent-1") in client.table_obj.eq_calls
    assert ("is_main", 1) in client.table_obj.eq_calls


def test_supabase_thread_repo_get_by_user_id_reads_thread_identity() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    result = repo.get_by_user_id("agent-1")

    assert result is not None
    assert result["id"] == "thread-1"
    assert result["agent_user_id"] == "agent-1"
    assert ("agent_user_id", "agent-1") in client.table_obj.eq_calls


def test_supabase_thread_repo_get_by_user_id_targets_default_main_thread() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    repo.get_by_user_id("agent-1")

    assert ("agent_user_id", "agent-1") in client.table_obj.eq_calls
    assert ("is_main", 1) in client.table_obj.eq_calls


def test_supabase_thread_repo_list_by_ids_reads_threads_in_batch() -> None:
    client = _FakeClient()
    repo = SupabaseThreadRepo(client)

    rows = repo.list_by_ids(["thread-1", "thread-2"])

    assert [row["id"] for row in rows] == ["thread-1"]
    assert ("id", ["thread-1", "thread-2"]) in client.table_obj.in_calls


def test_supabase_thread_repo_list_default_threads_reads_agent_users_in_batch() -> None:
    client = _FakeClient()
    client.table_obj.rows = [
        {
            "id": "thread-1",
            "agent_user_id": "agent-1",
            "sandbox_type": "local",
            "model": None,
            "cwd": None,
            "status": "active",
            "is_main": 1,
            "branch_index": 0,
            "created_at": 1.0,
            "updated_at": None,
            "last_active_at": None,
        },
        {
            "id": "thread-2",
            "agent_user_id": "agent-2",
            "sandbox_type": "local",
            "model": None,
            "cwd": None,
            "status": "active",
            "is_main": 0,
            "branch_index": 1,
            "created_at": 2.0,
            "updated_at": None,
            "last_active_at": None,
        },
    ]
    repo = SupabaseThreadRepo(client)

    rows = repo.list_default_threads(["agent-1", "agent-2"])

    assert list(rows) == ["agent-1"]
    assert rows["agent-1"]["id"] == "thread-1"
    assert ("agent_user_id", ["agent-1", "agent-2"]) in client.table_obj.in_calls
    assert ("is_main", 1) in client.table_obj.eq_calls


def test_supabase_thread_repo_list_by_ids_chunks_large_in_filters() -> None:
    client = _FakeClient()
    client.table_obj.rows = [
        {
            "id": "thread-0",
            "agent_user_id": "agent-1",
            "sandbox_type": "local",
            "model": None,
            "cwd": None,
            "status": "active",
            "is_main": 1,
            "branch_index": 0,
            "created_at": 1.0,
            "updated_at": None,
            "last_active_at": None,
        },
        {
            "id": "thread-80",
            "agent_user_id": "agent-1",
            "sandbox_type": "local",
            "model": None,
            "cwd": None,
            "status": "active",
            "is_main": 0,
            "branch_index": 1,
            "created_at": 2.0,
            "updated_at": None,
            "last_active_at": None,
        },
    ]
    repo = SupabaseThreadRepo(client)

    rows = repo.list_by_ids([f"thread-{i}" for i in range(81)])

    assert [row["id"] for row in rows] == ["thread-0", "thread-80"]
    assert [len(values) for _key, values in client.table_obj.in_calls] == [80, 1]


def test_supabase_thread_repo_reads_agent_threads_schema_table() -> None:
    client = FakeSupabaseClient(
        tables={
            "agent.threads": [
                {
                    "id": "thread-1",
                    "agent_user_id": "agent-1",
                    "owner_user_id": "owner-1",
                    "current_workspace_id": None,
                    "sandbox_type": "local",
                    "model": "large",
                    "cwd": "/work",
                    "status": "active",
                    "run_status": "idle",
                    "is_main": True,
                    "branch_index": 0,
                    "created_at": "2026-04-14T00:00:00+00:00",
                    "updated_at": "2026-04-14T00:00:00+00:00",
                    "last_active_at": None,
                }
            ]
        }
    )
    repo = SupabaseThreadRepo(client)

    row = repo.get_by_id("thread-1")

    assert row is not None
    assert row["id"] == "thread-1"
    assert row["agent_user_id"] == "agent-1"
    assert row["owner_user_id"] == "owner-1"


def test_supabase_thread_repo_list_by_owner_reads_identity_users_for_agent_display() -> None:
    client = FakeSupabaseClient(
        tables={
            "identity.users": [
                {
                    "id": "agent-1",
                    "display_name": "Toad",
                    "avatar": "avatars/agent-1.png",
                    "owner_user_id": "owner-1",
                }
            ],
            "agent.threads": [
                {
                    "id": "thread-1",
                    "agent_user_id": "agent-1",
                    "owner_user_id": "owner-1",
                    "current_workspace_id": "workspace-1",
                    "sandbox_type": "local",
                    "model": "leon:mini",
                    "cwd": "/workspace",
                    "status": "active",
                    "run_status": "idle",
                    "is_main": True,
                    "branch_index": 0,
                    "created_at": "2026-04-14T00:00:00+00:00",
                    "updated_at": "2026-04-14T00:00:00+00:00",
                    "last_active_at": None,
                }
            ],
        }
    )
    repo = SupabaseThreadRepo(client)

    rows = repo.list_by_owner_user_id("owner-1")

    assert rows == [
        {
            "id": "thread-1",
            "agent_user_id": "agent-1",
            "owner_user_id": "owner-1",
            "current_workspace_id": "workspace-1",
            "sandbox_type": "local",
            "model": "leon:mini",
            "cwd": "/workspace",
            "status": "active",
            "run_status": "idle",
            "is_main": True,
            "branch_index": 0,
            "created_at": "2026-04-14T00:00:00+00:00",
            "updated_at": "2026-04-14T00:00:00+00:00",
            "last_active_at": None,
            "agent_name": "Toad",
            "agent_avatar": "avatars/agent-1.png",
        }
    ]
