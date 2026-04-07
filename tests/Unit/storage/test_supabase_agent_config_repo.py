from storage.providers.supabase.agent_config_repo import SupabaseAgentConfigRepo


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
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {}

    def table(self, name):
        table = self.tables.get(name)
        if table is None:
            table = _FakeTable()
            self.tables[name] = table
        return table


def test_supabase_agent_config_repo_get_config_filters_on_agent_config_id() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    row = repo.get_config("cfg-1")

    assert row is not None
    assert ("id", "cfg-1") in client.tables["agent_configs"].eq_calls
    assert ("member_id", "cfg-1") not in client.tables["agent_configs"].eq_calls


def test_supabase_agent_config_repo_save_config_uses_agent_config_id_payload() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.save_config(
        "cfg-1",
        {
            "id": "cfg-1",
            "agent_user_id": "user-agent-1",
            "name": "Toad",
        },
    )

    payload = client.tables["agent_configs"].upsert_payload
    assert payload is not None
    assert payload["id"] == "cfg-1"
    assert "member_id" not in payload


def test_supabase_agent_config_repo_save_skill_conflicts_on_agent_config_id_and_name() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.save_skill("cfg-1", "Search", "search skill")

    table = client.tables["agent_skills"]
    assert table.upsert_payload is not None
    assert table.upsert_payload["agent_config_id"] == "cfg-1"
    assert table.upsert_conflict == "agent_config_id,name"


def test_supabase_agent_config_repo_list_rules_filters_on_agent_config_id() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.list_rules("cfg-1")

    assert ("agent_config_id", "cfg-1") in client.tables["agent_rules"].eq_calls
    assert ("member_id", "cfg-1") not in client.tables["agent_rules"].eq_calls
