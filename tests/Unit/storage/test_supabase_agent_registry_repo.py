import storage.runtime as storage_runtime
from storage.container import StorageContainer
from storage.providers.supabase.agent_registry_repo import SupabaseAgentRegistryRepo


class _FakeTable:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.eq_calls: list[tuple[str, object]] = []
        self.select_calls: list[str] = []
        self.upsert_payload = None

    def select(self, cols):
        self.select_calls.append(cols)
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def upsert(self, payload):
        self.upsert_payload = payload
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self, label: str, rows=None):
        self.label = label
        self.table_obj = _FakeTable(rows)
        self.table_names: list[str] = []

    def table(self, name):
        self.table_names.append(name)
        return self.table_obj


def test_storage_container_agent_registry_repo_uses_staging_client_not_public_client() -> None:
    staging_client = _FakeClient("staging")
    public_client = _FakeClient("public")
    container = StorageContainer(supabase_client=staging_client, public_supabase_client=public_client)

    repo = container.agent_registry_repo()
    repo.register(
        agent_id="agent-1",
        name="Scout",
        thread_id="thread-1",
        status="running",
        parent_agent_id=None,
        subagent_type="General",
    )

    assert staging_client.table_names == ["agent_registry"]
    assert public_client.table_names == []


def test_storage_container_user_settings_repo_uses_staging_client_not_public_client() -> None:
    staging_client = _FakeClient("staging")
    public_client = _FakeClient("public")
    container = StorageContainer(supabase_client=staging_client, public_supabase_client=public_client)

    repo = container.user_settings_repo()
    repo.get("user-1")

    assert staging_client.table_names == ["user_settings"]
    assert public_client.table_names == []


def test_storage_container_sync_file_repo_uses_staging_client_not_public_client() -> None:
    staging_client = _FakeClient("staging")
    public_client = _FakeClient("public")
    container = StorageContainer(supabase_client=staging_client, public_supabase_client=public_client)

    repo = container.sync_file_repo()
    repo.track_file("thread-1", "notes/a.txt", "a" * 64, 123)

    assert staging_client.table_names == ["sync_files"]
    assert public_client.table_names == []


def test_runtime_agent_registry_builder_does_not_resolve_public_client(monkeypatch) -> None:
    staging_client = _FakeClient("staging")

    def fake_resolve_supabase_client(supabase_client=None, factory_ref=None):
        if factory_ref is not None:
            raise AssertionError(f"unexpected public factory resolution: {factory_ref}")
        return supabase_client

    monkeypatch.setattr(storage_runtime, "_resolve_supabase_client", fake_resolve_supabase_client)

    repo = storage_runtime.build_agent_registry_repo(supabase_client=staging_client)
    repo.register(
        agent_id="agent-1",
        name="Scout",
        thread_id="thread-1",
        status="running",
        parent_agent_id=None,
        subagent_type="General",
    )

    assert staging_client.table_names == ["agent_registry"]


def test_runtime_sync_file_builder_does_not_resolve_public_client(monkeypatch) -> None:
    staging_client = _FakeClient("staging")

    def fake_resolve_supabase_client(supabase_client=None, factory_ref=None):
        if factory_ref is not None:
            raise AssertionError(f"unexpected public factory resolution: {factory_ref}")
        return supabase_client

    monkeypatch.setattr(storage_runtime, "_resolve_supabase_client", fake_resolve_supabase_client)

    repo = storage_runtime.build_sync_file_repo(supabase_client=staging_client)
    repo.track_file("thread-1", "notes/a.txt", "a" * 64, 123)

    assert staging_client.table_names == ["sync_files"]


def test_supabase_agent_registry_repo_lists_running_by_name() -> None:
    rows = [
        {
            "agent_id": "agent-1",
            "name": "Scout",
            "thread_id": "thread-1",
            "status": "running",
            "parent_agent_id": "parent-1",
            "subagent_type": "General",
        }
    ]
    client = _FakeClient("staging", rows)
    repo = SupabaseAgentRegistryRepo(client)

    result = repo.list_running_by_name("Scout")

    assert result == [("agent-1", "Scout", "thread-1", "running", "parent-1", "General")]
    assert client.table_names == ["agent_registry"]
    assert client.table_obj.eq_calls == [("name", "Scout"), ("status", "running")]


def test_supabase_agent_registry_repo_no_longer_exposes_dead_methods() -> None:
    repo = SupabaseAgentRegistryRepo(_FakeClient("staging"))

    assert hasattr(repo, "get_by_id") is False
    assert hasattr(repo, "update_status") is False
    assert hasattr(repo, "get_latest_by_name_and_parent") is False
    assert hasattr(repo, "list_running") is False
