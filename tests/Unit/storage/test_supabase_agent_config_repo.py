from storage.providers.supabase.agent_config_repo import SupabaseAgentConfigRepo
from tests.fakes.supabase import FakeSupabaseClient


class _FakeTable:
    def __init__(self) -> None:
        self.eq_calls: list[tuple[str, object]] = []
        self.upsert_payload = None
        self.upsert_conflict = None
        self.rows = [
            {
                "id": "cfg-1",
                "agent_user_id": "user-agent-1",
                "name": "Toad",
                "description": "test config",
            }
        ]

    def select(self, _cols):
        return self

    def eq(self, key, value):
        self.eq_calls.append((key, value))
        return self

    def upsert(self, payload, on_conflict=None):
        self.upsert_payload = payload
        self.upsert_conflict = on_conflict
        return self

    def delete(self):
        return self

    def execute(self):
        return type("Resp", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self, tables: dict[str, _FakeTable] | None = None, schema_name: str | None = None) -> None:
        self.tables: dict[str, _FakeTable] = tables if tables is not None else {}
        self.schema_name = schema_name

    def table(self, name):
        resolved = f"{self.schema_name}.{name}" if self.schema_name else name
        table = self.tables.get(resolved)
        if table is None:
            table = _FakeTable()
            self.tables[resolved] = table
        return table

    def schema(self, name):
        return _FakeClient(self.tables, schema_name=name)


def test_supabase_agent_config_repo_get_config_filters_on_agent_config_id() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    row = repo.get_config("cfg-1")

    assert row is not None
    assert ("id", "cfg-1") in client.tables["agent.agent_configs"].eq_calls
    assert ("member_id", "cfg-1") not in client.tables["agent.agent_configs"].eq_calls


def test_supabase_agent_config_repo_save_config_uses_agent_config_id_payload() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.save_config(
        "cfg-1",
        {
            "id": "cfg-1",
            "agent_user_id": "user-agent-1",
            "name": "Toad",
            "tools": ["search"],
            "runtime": {"tools:search": {"enabled": True}},
            "mcp": {"demo": {"command": "npx"}},
            "meta": {"source": {"marketplace_item_id": "item-1"}},
            "compact": {"trigger_tokens": 1000},
        },
    )

    payload = client.tables["agent.agent_configs"].upsert_payload
    assert payload is not None
    assert payload["id"] == "cfg-1"
    assert "member_id" not in payload
    assert payload["tools_json"] == ["search"]
    assert payload["runtime_json"] == {"tools:search": {"enabled": True}}
    assert payload["mcp_json"] == {"demo": {"command": "npx"}}
    assert payload["meta_json"] == {
        "source": {"marketplace_item_id": "item-1"},
        "compact": {"trigger_tokens": 1000},
    }
    assert "tools" not in payload
    assert "runtime" not in payload
    assert "mcp" not in payload
    assert "meta" not in payload
    assert "compact" not in payload


def test_supabase_agent_config_repo_get_config_normalizes_json_columns() -> None:
    client = _FakeClient()
    client.tables["agent.agent_configs"] = _FakeTable()
    client.tables["agent.agent_configs"].rows = [
        {
            "id": "cfg-1",
            "agent_user_id": "user-agent-1",
            "name": "Toad",
            "tools_json": ["search"],
            "runtime_json": {"tools:search": {"enabled": True}},
            "mcp_json": {"demo": {"command": "npx"}},
            "meta_json": {
                "source": {"marketplace_item_id": "item-1"},
                "compact": {"trigger_tokens": 1000},
            },
        }
    ]
    repo = SupabaseAgentConfigRepo(client)

    row = repo.get_config("cfg-1")

    assert row is not None
    assert row["tools"] == ["search"]
    assert row["runtime"] == {"tools:search": {"enabled": True}}
    assert row["mcp"] == {"demo": {"command": "npx"}}
    assert row["meta"] == {"source": {"marketplace_item_id": "item-1"}}
    assert row["compact"] == {"trigger_tokens": 1000}


def test_supabase_agent_config_repo_save_skill_conflicts_on_agent_config_id_and_name() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.save_skill("cfg-1", "Search", "search skill", meta={"enabled": True})

    table = client.tables["agent.agent_skills"]
    assert table.upsert_payload is not None
    assert table.upsert_payload["agent_config_id"] == "cfg-1"
    assert table.upsert_conflict == "agent_config_id,name"
    assert table.upsert_payload["meta_json"] == {"enabled": True}


def test_supabase_agent_config_repo_list_rules_filters_on_agent_config_id() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.list_rules("cfg-1")

    assert ("agent_config_id", "cfg-1") in client.tables["agent.agent_rules"].eq_calls
    assert ("member_id", "cfg-1") not in client.tables["agent.agent_rules"].eq_calls


def test_supabase_agent_config_repo_save_sub_agent_uses_tools_json() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.save_sub_agent("cfg-1", "Scout", tools=["search"])

    table = client.tables["agent.agent_sub_agents"]
    assert table.upsert_payload is not None
    assert table.upsert_payload["agent_config_id"] == "cfg-1"
    assert table.upsert_payload["tools_json"] == ["search"]


def test_supabase_agent_config_repo_uses_agent_schema_tables() -> None:
    tables: dict[str, list[dict]] = {
        "agent.agent_configs": [
            {
                "id": "cfg-1",
                "agent_user_id": "user-agent-1",
                "name": "Toad",
                "description": "target schema config",
            }
        ],
        "agent.agent_rules": [{"id": "rule-1", "agent_config_id": "cfg-1", "filename": "RULE.md", "content": "rule"}],
    }
    repo = SupabaseAgentConfigRepo(FakeSupabaseClient(tables))

    config = repo.get_config("cfg-1")
    repo.save_skill("cfg-1", "Search", "skill")
    repo.save_sub_agent("cfg-1", "Scout")

    assert config is not None
    assert config["id"] == "cfg-1"
    assert repo.list_rules("cfg-1")[0]["id"] == "rule-1"
    assert "agent.agent_skills" in tables
    assert "agent.agent_sub_agents" in tables
    assert "agent_configs" not in tables
    assert "agent_rules" not in tables
    assert "agent_skills" not in tables
    assert "agent_sub_agents" not in tables
