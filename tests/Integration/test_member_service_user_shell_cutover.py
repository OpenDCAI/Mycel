from __future__ import annotations

from pathlib import Path

import pytest

from backend.web.services import member_service
from storage.contracts import UserRow, UserType


class _FakeUserRepo:
    def __init__(self, rows: dict[str, UserRow] | None = None) -> None:
        self.rows = rows or {}
        self.created: list[UserRow] = []
        self.updated: list[tuple[str, dict[str, object]]] = []
        self.deleted: list[str] = []
        self.owner_queries: list[str] = []

    def create(self, row: UserRow) -> None:
        self.created.append(row)
        self.rows[row.id] = row

    def get_by_id(self, user_id: str) -> UserRow | None:
        return self.rows.get(user_id)

    def list_by_owner_user_id(self, owner_user_id: str) -> list[UserRow]:
        self.owner_queries.append(owner_user_id)
        return [row for row in self.rows.values() if row.owner_user_id == owner_user_id]

    def update(self, user_id: str, **fields: object) -> None:
        self.updated.append((user_id, fields))

    def delete(self, user_id: str) -> None:
        self.deleted.append(user_id)


class _FakeAgentConfigRepo:
    def __init__(self) -> None:
        self.saved_configs: list[tuple[str, dict[str, object]]] = []
        self.saved_rules: list[tuple[str, str, str]] = []
        self.saved_skills: list[tuple[str, str, str]] = []
        self.saved_sub_agents: list[tuple[str, str, dict[str, object]]] = []
        self.get_calls: list[str] = []
        self.deleted: list[str] = []
        self.configs: dict[str, dict[str, object]] = {}
        self.rules: dict[str, list[dict[str, object]]] = {}
        self.skills: dict[str, list[dict[str, object]]] = {}
        self.sub_agents: dict[str, list[dict[str, object]]] = {}

    def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
        self.saved_configs.append((agent_config_id, data))
        self.configs[agent_config_id] = {"id": agent_config_id, **data}

    def save_rule(self, agent_config_id: str, filename: str, content: str, rule_id: str | None = None) -> dict[str, object]:
        self.saved_rules.append((agent_config_id, filename, content))
        payload = {"id": rule_id or "rule-1", "agent_config_id": agent_config_id, "filename": filename, "content": content}
        self.rules.setdefault(agent_config_id, []).append(payload)
        return payload

    def save_skill(
        self,
        agent_config_id: str,
        name: str,
        content: str,
        meta: dict | None = None,
        skill_id: str | None = None,
    ) -> dict[str, object]:
        self.saved_skills.append((agent_config_id, name, content))
        payload = {"id": skill_id or "skill-1", "agent_config_id": agent_config_id, "name": name, "content": content}
        self.skills.setdefault(agent_config_id, []).append(payload)
        return payload

    def save_sub_agent(
        self,
        agent_config_id: str,
        name: str,
        **fields: object,
    ) -> dict[str, object]:
        self.saved_sub_agents.append((agent_config_id, name, fields))
        payload = {"id": "sub-1", "agent_config_id": agent_config_id, "name": name, **fields}
        self.sub_agents.setdefault(agent_config_id, []).append(payload)
        return payload

    def get_config(self, agent_config_id: str) -> dict[str, object] | None:
        self.get_calls.append(agent_config_id)
        return self.configs.get(agent_config_id) or {"id": agent_config_id, "name": "Toad", "version": "0.1.0", "status": "draft"}

    def list_rules(self, agent_config_id: str) -> list[dict[str, object]]:
        return list(self.rules.get(agent_config_id, []))

    def list_skills(self, agent_config_id: str) -> list[dict[str, object]]:
        return list(self.skills.get(agent_config_id, []))

    def list_sub_agents(self, agent_config_id: str) -> list[dict[str, object]]:
        return list(self.sub_agents.get(agent_config_id, []))

    def delete_config(self, agent_config_id: str) -> None:
        self.deleted.append(agent_config_id)

    def delete_rule(self, rule_id: str) -> None:
        for agent_config_id, rows in list(self.rules.items()):
            self.rules[agent_config_id] = [row for row in rows if row["id"] != rule_id]

    def delete_skill(self, skill_id: str) -> None:
        for agent_config_id, rows in list(self.skills.items()):
            self.skills[agent_config_id] = [row for row in rows if row["id"] != skill_id]

    def delete_sub_agent(self, sub_agent_id: str) -> None:
        for agent_config_id, rows in list(self.sub_agents.items()):
            self.sub_agents[agent_config_id] = [row for row in rows if row["id"] != sub_agent_id]


class _OrderCheckingAgentConfigRepo(_FakeAgentConfigRepo):
    def __init__(self, user_repo: _FakeUserRepo) -> None:
        super().__init__()
        self._user_repo = user_repo

    def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
        owner_rows = [row for row in self._user_repo.created if row.agent_config_id == agent_config_id]
        assert owner_rows, "agent user must exist before agent_config save"
        super().save_config(agent_config_id, data)


class _FailingAgentConfigRepo(_FakeAgentConfigRepo):
    def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
        raise RuntimeError("boom")


def _agent_user(*, user_id: str = "agent-1", owner_user_id: str = "owner-1", agent_config_id: str = "cfg-1") -> UserRow:
    return UserRow(
        id=user_id,
        type=UserType.AGENT,
        display_name="Toad",
        owner_user_id=owner_user_id,
        agent_config_id=agent_config_id,
        created_at=1.0,
        updated_at=2.0,
    )


def _write_member_shell(member_dir: Path, *, name: str = "Toad", description: str = "helper") -> None:
    member_dir.mkdir(parents=True, exist_ok=True)
    member_service._write_agent_md(member_dir / "agent.md", name=name, description=description, system_prompt="hello")
    member_service._write_json(
        member_dir / "meta.json",
        {"status": "draft", "version": "0.1.0", "created_at": 1, "updated_at": 2},
    )


def test_list_members_uses_user_repo_owner_scope(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["*"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {},
            "mcp": {},
            "created_at": 1,
            "updated_at": 2,
        },
    )

    items = member_service.list_members("owner-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert user_repo.owner_queries == ["owner-1"]
    assert [item["id"] for item in items] == ["agent-1"]
    assert items[0]["name"] == "Toad"
    assert items[0]["config"]["prompt"] == "hello"


def test_get_member_reads_agent_shell_from_repos_not_filesystem(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["send_message"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {"skills:search": {"enabled": True, "desc": "Search skill"}},
            "mcp": {"filesystem": {"command": "npx", "args": ["-y"], "env": {}, "disabled": False}},
            "created_at": 1,
            "updated_at": 2,
        },
    )
    agent_config_repo.save_rule("cfg-1", "guard.md", "be careful")
    agent_config_repo.save_skill("cfg-1", "search", "# Search")
    agent_config_repo.save_sub_agent("cfg-1", "Scout", description="helper", tools=["send_message"], system_prompt="go")

    item = member_service.get_member("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert item is not None
    assert item["id"] == "agent-1"
    assert item["name"] == "Toad"
    assert item["config"]["prompt"] == "hello"
    assert item["config"]["rules"] == [{"name": "guard", "content": "be careful"}]
    assert item["config"]["skills"][0]["name"] == "search"
    assert item["config"]["mcps"][0]["name"] == "filesystem"
    assert item["config"]["subAgents"][0]["name"] == "Scout"


def test_create_member_creates_agent_user_and_saves_config_by_agent_config_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo()
    agent_config_repo = _FakeAgentConfigRepo()

    created = member_service.create_member(
        "Toad",
        "helper",
        owner_user_id="owner-1",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert len(user_repo.created) == 1
    agent_user = user_repo.created[0]
    assert agent_user.type is UserType.AGENT
    assert agent_user.owner_user_id == "owner-1"
    assert agent_user.agent_config_id is not None
    assert created is not None
    assert created["id"] == agent_user.id
    assert agent_config_repo.saved_configs[0][0] == agent_user.agent_config_id
    assert agent_config_repo.saved_configs[0][1]["agent_user_id"] == agent_user.id


def test_create_member_does_not_write_member_shell_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo()
    agent_config_repo = _FakeAgentConfigRepo()

    created = member_service.create_member(
        "Toad",
        "helper",
        owner_user_id="owner-1",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert created is not None
    assert list(tmp_path.iterdir()) == []


def test_get_member_builtin_does_not_require_member_shell_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)

    item = member_service.get_member("__leon__")

    assert item is not None
    assert item["id"] == "__leon__"
    assert item["builtin"] is True
    assert not (tmp_path / "__leon__").exists()


def test_list_members_unscoped_returns_builtin_without_scanning_member_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "legacy-agent", name="LegacyAgent", description="legacy shell")

    items = member_service.list_members()

    assert [item["id"] for item in items] == ["__leon__"]
    assert items[0]["builtin"] is True


def test_update_member_builtin_is_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="Builtin agent is read-only"):
        member_service.update_member("__leon__", name="Nope")


def test_update_member_config_builtin_is_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="Builtin agent is read-only"):
        member_service.update_member_config("__leon__", {"prompt": "nope"})


def test_create_member_persists_agent_user_before_agent_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo()
    agent_config_repo = _OrderCheckingAgentConfigRepo(user_repo)

    created = member_service.create_member(
        "Morel",
        "analyst",
        owner_user_id="owner-1",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert created is not None
    assert len(user_repo.created) == 1
    assert len(agent_config_repo.saved_configs) == 1


def test_create_member_raises_when_agent_config_sync_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo()
    agent_config_repo = _FailingAgentConfigRepo()

    with pytest.raises(RuntimeError, match="boom"):
        member_service.create_member(
            "Morel",
            "analyst",
            owner_user_id="owner-1",
            user_repo=user_repo,
            agent_config_repo=agent_config_repo,
        )


def test_update_member_config_syncs_repo_by_agent_config_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "agent-1")
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()

    member_service.update_member_config(
        "agent-1",
        {"prompt": "updated prompt"},
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert agent_config_repo.saved_configs[0][0] == "cfg-1"


def test_update_member_uses_repo_even_when_member_dir_is_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["*"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {},
            "mcp": {},
            "created_at": 1,
            "updated_at": 2,
        },
    )

    result = member_service.update_member(
        "agent-1",
        name="Dryad",
        description="analyst",
        status="active",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert result is not None
    assert result["name"] == "Dryad"
    assert result["description"] == "analyst"
    assert result["status"] == "active"
    assert user_repo.updated == [("agent-1", {"display_name": "Dryad"})]
    assert agent_config_repo.saved_configs[-1][0] == "cfg-1"


def test_update_member_prefers_repo_even_when_legacy_member_dir_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "agent-1", name="LegacyShell", description="legacy shell")
    legacy_before = (tmp_path / "agent-1" / "agent.md").read_text(encoding="utf-8")

    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["*"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {},
            "mcp": {},
            "created_at": 1,
            "updated_at": 2,
        },
    )

    result = member_service.update_member(
        "agent-1",
        name="Dryad",
        description="analyst",
        status="active",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert result is not None
    assert result["name"] == "Dryad"
    assert result["description"] == "analyst"
    assert result["status"] == "active"
    assert user_repo.updated == [("agent-1", {"display_name": "Dryad"})]
    assert agent_config_repo.saved_configs[-1][0] == "cfg-1"
    assert (tmp_path / "agent-1" / "agent.md").read_text(encoding="utf-8") == legacy_before


def test_update_member_config_uses_repo_even_when_member_dir_is_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["search"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {"tools:search": {"enabled": True, "desc": "Search"}},
            "mcp": {"filesystem": {"command": "npx", "args": ["-y"], "env": {}, "disabled": False}},
            "created_at": 1,
            "updated_at": 2,
        },
    )
    agent_config_repo.save_rule("cfg-1", "old.md", "old")
    agent_config_repo.save_skill("cfg-1", "search", "# Search")
    agent_config_repo.save_sub_agent("cfg-1", "Scout", description="helper", tools=["search"], system_prompt="go")

    result = member_service.update_member_config(
        "agent-1",
        {
            "prompt": "updated prompt",
            "rules": [{"name": "guard", "content": "be careful"}],
            "tools": [{"name": "send_message", "enabled": True, "desc": "Send"}],
            "skills": [{"name": "lookup", "enabled": True, "desc": "Lookup"}],
            "mcps": [{"name": "filesystem", "command": "uvx", "args": ["mcp"], "env": {"A": "1"}, "disabled": False}],
            "subAgents": [{"name": "Guide", "desc": "helper", "tools": [], "system_prompt": "guide"}],
        },
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert result is not None
    assert result["config"]["prompt"] == "updated prompt"
    assert result["config"]["rules"] == [{"name": "guard", "content": "be careful"}]
    assert [row["name"] for row in agent_config_repo.list_skills("cfg-1")] == ["lookup"]
    assert [row["name"] for row in agent_config_repo.list_sub_agents("cfg-1")] == ["Guide"]
    saved_config = agent_config_repo.saved_configs[-1][1]
    assert saved_config["runtime"] == {
        "tools:send_message": {"enabled": True, "desc": "Send"},
        "skills:lookup": {"enabled": True, "desc": "Lookup"},
    }
    assert saved_config["mcp"] == {"filesystem": {"command": "uvx", "args": ["mcp"], "env": {"A": "1"}, "disabled": False}}


def test_update_member_config_prefers_repo_even_when_legacy_member_dir_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "agent-1", name="LegacyShell", description="legacy shell")
    legacy_before = (tmp_path / "agent-1" / "agent.md").read_text(encoding="utf-8")

    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["search"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {"tools:search": {"enabled": True, "desc": "Search"}},
            "mcp": {"filesystem": {"command": "npx", "args": ["-y"], "env": {}, "disabled": False}},
            "created_at": 1,
            "updated_at": 2,
        },
    )

    result = member_service.update_member_config(
        "agent-1",
        {
            "prompt": "updated prompt",
            "rules": [{"name": "guard", "content": "be careful"}],
            "tools": [{"name": "send_message", "enabled": True, "desc": "Send"}],
            "skills": [{"name": "lookup", "enabled": True, "desc": "Lookup"}],
            "mcps": [{"name": "filesystem", "command": "uvx", "args": ["mcp"], "env": {"A": "1"}, "disabled": False}],
            "subAgents": [{"name": "Guide", "desc": "helper", "tools": [], "system_prompt": "guide"}],
        },
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert result is not None
    assert result["config"]["prompt"] == "updated prompt"
    assert result["config"]["rules"] == [{"name": "guard", "content": "be careful"}]
    assert [row["name"] for row in agent_config_repo.list_skills("cfg-1")] == ["lookup"]
    assert [row["name"] for row in agent_config_repo.list_sub_agents("cfg-1")] == ["Guide"]
    assert (tmp_path / "agent-1" / "agent.md").read_text(encoding="utf-8") == legacy_before


def test_publish_member_reads_and_writes_repo_by_agent_config_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "agent-1")
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()

    member_service.publish_member("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert agent_config_repo.get_calls == ["cfg-1", "cfg-1"]
    assert agent_config_repo.saved_configs[-1][0] == "cfg-1"


def test_publish_member_uses_repo_even_when_member_dir_is_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()
    agent_config_repo.save_config(
        "cfg-1",
        {
            "agent_user_id": "agent-1",
            "name": "Toad",
            "description": "helper",
            "tools": ["*"],
            "system_prompt": "hello",
            "status": "draft",
            "version": "0.1.0",
            "runtime": {},
            "mcp": {},
            "created_at": 1,
            "updated_at": 2,
        },
    )

    result = member_service.publish_member("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert result is not None
    assert result["status"] == "active"
    assert result["version"] == "0.1.1"
    assert agent_config_repo.saved_configs[-1][0] == "cfg-1"


def test_delete_member_deletes_user_and_agent_config_by_agent_config_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "agent-1")
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()

    ok = member_service.delete_member("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert ok is True
    assert agent_config_repo.deleted == ["cfg-1"]
    assert user_repo.deleted == ["agent-1"]


def test_delete_member_deletes_db_shell_even_when_member_dir_is_absent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()

    ok = member_service.delete_member("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert ok is True
    assert agent_config_repo.deleted == ["cfg-1"]
    assert user_repo.deleted == ["agent-1"]


def test_install_from_snapshot_creates_agent_user_before_syncing_agent_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    user_repo = _FakeUserRepo()
    agent_config_repo = _OrderCheckingAgentConfigRepo(user_repo)

    installed_user_id = member_service.install_from_snapshot(
        snapshot={"agent_md": "---\nname: Toad\n---\n\nhello\n"},
        name="Toad",
        description="helper",
        marketplace_item_id="item-1",
        installed_version="1.2.3",
        owner_user_id="owner-1",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert installed_user_id == user_repo.created[0].id
    assert agent_config_repo.saved_configs[0][0] == user_repo.created[0].agent_config_id
    assert agent_config_repo.saved_configs[0][1]["agent_user_id"] == installed_user_id
    assert list(tmp_path.iterdir()) == []


def test_install_from_snapshot_updates_existing_user_via_existing_user_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    existing_user = _agent_user(user_id="agent-1", agent_config_id="cfg-1")
    _write_member_shell(tmp_path / "agent-1")
    legacy_agent_md = (tmp_path / "agent-1" / "agent.md").read_text(encoding="utf-8")
    user_repo = _FakeUserRepo(rows={"agent-1": existing_user})
    agent_config_repo = _FakeAgentConfigRepo()

    installed_user_id = member_service.install_from_snapshot(
        snapshot={"agent_md": "---\nname: Toad\n---\n\nupdated\n"},
        name="Toad",
        description="helper",
        marketplace_item_id="item-1",
        installed_version="1.2.3",
        owner_user_id="owner-1",
        existing_user_id="agent-1",
        user_repo=user_repo,
        agent_config_repo=agent_config_repo,
    )

    assert installed_user_id == "agent-1"
    assert agent_config_repo.saved_configs[0][0] == "cfg-1"
    assert agent_config_repo.saved_configs[0][1]["agent_user_id"] == "agent-1"
    assert (tmp_path / "agent-1" / "agent.md").read_text(encoding="utf-8") == legacy_agent_md
