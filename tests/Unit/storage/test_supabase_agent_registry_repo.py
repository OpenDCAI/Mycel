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
