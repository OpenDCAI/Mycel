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

    def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
        self.saved_configs.append((agent_config_id, data))

    def save_rule(self, agent_config_id: str, filename: str, content: str, rule_id: str | None = None) -> dict[str, object]:
        self.saved_rules.append((agent_config_id, filename, content))
        return {"id": rule_id or "rule-1", "agent_config_id": agent_config_id, "filename": filename, "content": content}

    def save_skill(
        self,
        agent_config_id: str,
        name: str,
        content: str,
        meta: dict | None = None,
        skill_id: str | None = None,
    ) -> dict[str, object]:
        self.saved_skills.append((agent_config_id, name, content))
        return {"id": skill_id or "skill-1", "agent_config_id": agent_config_id, "name": name, "content": content}

    def save_sub_agent(
        self,
        agent_config_id: str,
        name: str,
        **fields: object,
    ) -> dict[str, object]:
        self.saved_sub_agents.append((agent_config_id, name, fields))
        return {"id": "sub-1", "agent_config_id": agent_config_id, "name": name, **fields}

    def get_config(self, agent_config_id: str) -> dict[str, object] | None:
        self.get_calls.append(agent_config_id)
        return {"id": agent_config_id, "name": "Toad", "version": "0.1.0", "status": "draft"}

    def delete_config(self, agent_config_id: str) -> None:
        self.deleted.append(agent_config_id)


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
    _write_member_shell(tmp_path / "agent-1")
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})

    items = member_service.list_members("owner-1", user_repo=user_repo)

    assert user_repo.owner_queries == ["owner-1"]
    assert [item["id"] for item in items] == ["agent-1"]


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


def test_publish_member_reads_and_writes_repo_by_agent_config_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    _write_member_shell(tmp_path / "agent-1")
    user_repo = _FakeUserRepo(rows={"agent-1": _agent_user()})
    agent_config_repo = _FakeAgentConfigRepo()

    member_service.publish_member("agent-1", user_repo=user_repo, agent_config_repo=agent_config_repo)

    assert agent_config_repo.get_calls == ["cfg-1"]
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
