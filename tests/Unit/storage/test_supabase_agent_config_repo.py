import pytest

from config.agent_config_types import AgentConfig, AgentRule, AgentSkill, AgentSubAgent, McpServerConfig
from storage.providers.supabase.agent_config_repo import SupabaseAgentConfigRepo


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, table_name: str, tables: dict[str, list[dict]]) -> None:
        self.table_name = table_name
        self.tables = tables
        self.eq_calls: list[tuple[str, object]] = []
        self._delete = False

    def select(self, _columns: str):
        return self

    def eq(self, column: str, value: object):
        self.eq_calls.append((column, value))
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        rows = self.tables.setdefault(self.table_name, [])
        matching = [row for row in rows if all(row.get(column) == value for column, value in self.eq_calls)]
        if self._delete:
            self.tables[self.table_name] = [row for row in rows if row not in matching]
        return _FakeResponse([dict(row) for row in matching])


class _FakeRpc:
    def __init__(self, client: "_FakeClient", name: str, params: dict) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self):
        self.client.root.rpc_calls.append((self.client.schema_name, self.name, self.params))
        return _FakeResponse([])


class _FakeClient:
    def __init__(
        self, tables: dict[str, list[dict]] | None = None, schema_name: str | None = None, root: "_FakeClient | None" = None
    ) -> None:
        self.root = root or self
        self.tables = self.root.tables if root else (tables if tables is not None else {})
        self.rpc_calls = self.root.rpc_calls if root else []
        self.table_queries = self.root.table_queries if root else {}
        self.schema_name = schema_name

    def table(self, name: str):
        resolved = f"{self.schema_name}.{name}" if self.schema_name else name
        query = _FakeQuery(resolved, self.tables)
        self.root.table_queries.setdefault(resolved, []).append(query)
        return query

    def schema(self, name: str):
        return _FakeClient(schema_name=name, root=self.root)

    def rpc(self, name: str, params: dict):
        return _FakeRpc(self, name, params)


def _tables() -> dict[str, list[dict]]:
    return {
        "agent.agent_configs": [
            {
                "id": "cfg-1",
                "owner_user_id": "owner-1",
                "agent_user_id": "agent-1",
                "name": "Researcher",
                "description": "Research agent",
                "model": "gpt-test",
                "tools_json": ["read", "shell"],
                "system_prompt": "Base prompt",
                "status": "active",
                "version": "1.0.0",
                "runtime_json": {"shell": {"enabled": False}},
                "compact_json": {"trigger_tokens": 1000},
                "mcp_json": [
                    {
                        "id": "mcp-1",
                        "name": "filesystem",
                        "transport": "stdio",
                        "command": "fs",
                        "args": ["--root", "."],
                        "env": {"A": "B"},
                        "url": None,
                        "instructions": "Use narrowly.",
                        "allowed_tools": ["read"],
                        "enabled": True,
                    }
                ],
                "meta_json": {"source": "unit"},
            }
        ],
        "agent.skill_bindings": [
            {
                "id": "agent-skill-1",
                "agent_config_id": "cfg-1",
                "skill_id": "skill-1",
                "package_id": "package-1",
                "enabled": True,
            }
        ],
        "library.skills": [
            {
                "id": "skill-1",
                "owner_user_id": "owner-1",
                "name": "github",
                "description": "GitHub guidance",
                "package_id": "package-1",
                "source_json": {"source_version": "1.0.0"},
                "created_at": "2026-04-24T00:00:00+00:00",
                "updated_at": "2026-04-24T00:00:01+00:00",
            }
        ],
        "library.skill_packages": [
            {
                "id": "package-1",
                "owner_user_id": "owner-1",
                "skill_id": "skill-1",
                "version": "1.0.0",
                "hash": "sha256:abc",
                "manifest_json": {"files": [{"path": "references/query.md"}]},
                "skill_md": "---\nname: github\n---\n",
                "files_json": {"references/query.md": "Prefer precise queries."},
                "source_json": {"source_version": "1.0.0"},
                "created_at": "2026-04-24T00:00:00+00:00",
            }
        ],
        "agent.agent_rules": [{"id": "rule-1", "agent_config_id": "cfg-1", "name": "Cite", "content": "Always cite.", "enabled": True}],
        "agent.agent_sub_agents": [
            {
                "id": "sub-1",
                "agent_config_id": "cfg-1",
                "name": "Planner",
                "description": "Plans work",
                "model": "gpt-planner",
                "tools_json": ["read"],
                "system_prompt": "Plan carefully.",
                "enabled": True,
            }
        ],
    }


def test_get_agent_config_reads_full_aggregate_from_final_tables() -> None:
    client = _FakeClient(_tables())
    repo = SupabaseAgentConfigRepo(client)

    config = repo.get_agent_config("cfg-1")

    assert config == AgentConfig(
        id="cfg-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        name="Researcher",
        description="Research agent",
        model="gpt-test",
        tools=["read", "shell"],
        system_prompt="Base prompt",
        status="active",
        version="1.0.0",
        runtime_settings={"shell": {"enabled": False}},
        compact={"trigger_tokens": 1000},
        meta={"source": "unit"},
        skills=[
            AgentSkill(
                id="agent-skill-1",
                skill_id="skill-1",
                package_id="package-1",
                name="github",
                description="GitHub guidance",
                version="1.0.0",
                source={"source_version": "1.0.0"},
            )
        ],
        rules=[AgentRule(id="rule-1", name="Cite", content="Always cite.")],
        sub_agents=[
            AgentSubAgent(
                id="sub-1",
                name="Planner",
                description="Plans work",
                model="gpt-planner",
                tools=["read"],
                system_prompt="Plan carefully.",
            )
        ],
        mcp_servers=[
            McpServerConfig(
                id="mcp-1",
                name="filesystem",
                transport="stdio",
                command="fs",
                args=["--root", "."],
                env={"A": "B"},
                instructions="Use narrowly.",
                allowed_tools=["read"],
            )
        ],
    )
    assert ("id", "cfg-1") in client.table_queries["agent.agent_configs"][0].eq_calls


def test_get_agent_config_returns_none_when_root_missing() -> None:
    repo = SupabaseAgentConfigRepo(_FakeClient({"agent.agent_configs": []}))

    assert repo.get_agent_config("missing") is None


def test_get_agent_config_fails_loudly_when_mcp_json_is_not_an_array() -> None:
    tables = _tables()
    tables["agent.agent_configs"][0]["mcp_json"] = {"filesystem": {"command": "fs"}}
    repo = SupabaseAgentConfigRepo(_FakeClient(tables))

    with pytest.raises(RuntimeError, match="mcp_json must be a JSON array"):
        repo.get_agent_config("cfg-1")


def test_save_agent_config_calls_single_rpc_with_full_payload() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)

    repo.save_agent_config(
        AgentConfig(
            id="cfg-1",
            owner_user_id="owner-1",
            agent_user_id="agent-1",
            name="Researcher",
            tools=["read"],
            runtime_settings={"shell": {"enabled": False}},
            compact={"trigger_tokens": 1000},
            skills=[
                AgentSkill(
                    id="agent-skill-1",
                    skill_id="skill-1",
                    package_id="package-1",
                    name="github",
                )
            ],
            rules=[AgentRule(id="rule-1", name="Cite", content="Always cite.")],
        )
    )

    assert len(client.rpc_calls) == 1
    schema_name, function_name, params = client.rpc_calls[0]
    assert schema_name == "agent"
    assert function_name == "save_agent_config"
    payload = params["payload"]
    assert payload["id"] == "cfg-1"
    assert payload["owner_user_id"] == "owner-1"
    assert payload["agent_user_id"] == "agent-1"
    assert payload["runtime_settings"] == {"shell": {"enabled": False}}
    assert payload["compact"] == {"trigger_tokens": 1000}
    assert payload["skills"][0]["skill_id"] == "skill-1"
    assert "content" not in payload["skills"][0]
    assert "files" not in payload["skills"][0]
    assert "runtime_" + "settings_json" not in payload


def test_save_agent_config_rejects_duplicate_skill_names_before_rpc() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)
    config = AgentConfig(
        id="cfg-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        name="Researcher",
        skills=[
            AgentSkill(skill_id="github", package_id="package-1", name="github"),
            AgentSkill(skill_id="github-two", package_id="package-2", name="github"),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate Skill name in AgentConfig: github"):
        repo.save_agent_config(config)

    assert client.rpc_calls == []


def test_save_agent_config_rejects_duplicate_mcp_server_names_before_rpc() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)
    config = AgentConfig(
        id="cfg-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        name="Researcher",
        mcp_servers=[
            McpServerConfig(name="filesystem", transport="stdio", command="fs-one"),
            McpServerConfig(name="filesystem", transport="stdio", command="fs-two"),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate MCP server name in AgentConfig: filesystem"):
        repo.save_agent_config(config)

    assert client.rpc_calls == []


def test_save_agent_config_rejects_duplicate_disabled_child_names_before_rpc() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)
    config = AgentConfig(
        id="cfg-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        name="Researcher",
        skills=[
            AgentSkill(skill_id="github", package_id="package-1", name="github", enabled=False),
            AgentSkill(skill_id="github-two", package_id="package-2", name="github", enabled=False),
        ],
        mcp_servers=[
            McpServerConfig(name="filesystem", transport="stdio", command="fs-one", enabled=False),
            McpServerConfig(name="filesystem", transport="stdio", command="fs-two", enabled=False),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate Skill name in AgentConfig: github"):
        repo.save_agent_config(config)

    assert client.rpc_calls == []


def test_save_agent_config_rejects_duplicate_rule_and_sub_agent_names_before_rpc() -> None:
    client = _FakeClient()
    repo = SupabaseAgentConfigRepo(client)
    config = AgentConfig(
        id="cfg-1",
        owner_user_id="owner-1",
        agent_user_id="agent-1",
        name="Researcher",
        rules=[
            AgentRule(name="coding", content="one"),
            AgentRule(name="coding", content="two"),
        ],
        sub_agents=[
            AgentSubAgent(name="Scout"),
            AgentSubAgent(name="Scout"),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate Rule name in AgentConfig: coding"):
        repo.save_agent_config(config)

    assert client.rpc_calls == []


def test_delete_agent_config_deletes_root_aggregate() -> None:
    tables = _tables()
    repo = SupabaseAgentConfigRepo(_FakeClient(tables))

    repo.delete_agent_config("cfg-1")

    assert tables["agent.agent_configs"] == []
    assert tables["agent.skill_bindings"] == []
    assert tables["agent.agent_rules"] == []
    assert tables["agent.agent_sub_agents"] == []
