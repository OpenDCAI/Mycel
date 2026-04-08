from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.web.services import member_service
from backend.web.services.auth_service import AuthService
from storage.contracts import UserRow, UserType


class _FakeInviteCodes:
    def __init__(self) -> None:
        self.used: list[tuple[str, str]] = []

    def is_valid(self, code: str) -> bool:
        return code == "invite-1"

    def use(self, code: str, user_id: str) -> None:
        self.used.append((code, user_id))


class _FakeSupabaseClient:
    def rpc(self, name: str):
        assert name == "next_mycel_id"
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=10001))


class _FakeUserRepo:
    def __init__(self) -> None:
        self.rows: dict[str, UserRow] = {}
        self.created: list[UserRow] = []

    def create(self, row: UserRow) -> None:
        self.created.append(row)
        self.rows[row.id] = row

    def get_by_id(self, user_id: str) -> UserRow | None:
        return self.rows.get(user_id)

    def list_by_owner_user_id(self, owner_user_id: str) -> list[UserRow]:
        return [row for row in self.rows.values() if row.owner_user_id == owner_user_id]

    def update(self, user_id: str, **fields) -> None:
        row = self.rows[user_id]
        self.rows[user_id] = row.model_copy(update=fields)


class _FakeAgentConfigRepo:
    def __init__(self) -> None:
        self.saved: list[tuple[str, dict[str, object]]] = []

    def save_config(self, agent_config_id: str, data: dict[str, object]) -> None:
        self.saved.append((agent_config_id, data))


def _service(
    *,
    user_repo: _FakeUserRepo | None = None,
    agent_config_repo: _FakeAgentConfigRepo | None = None,
    invite_codes: _FakeInviteCodes | None = None,
) -> AuthService:
    return AuthService(
        users=user_repo or _FakeUserRepo(),
        agent_configs=agent_config_repo,
        supabase_client=_FakeSupabaseClient(),
        invite_codes=invite_codes or _FakeInviteCodes(),
    )


def test_complete_register_creates_human_and_owned_agent_users(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    monkeypatch.setattr(
        "backend.web.services.auth_service.jwt.decode",
        lambda *_args, **_kwargs: {"sub": "user-1", "email": "fresh@example.com"},
    )
    monkeypatch.setattr(
        "backend.web.routers.entities.process_and_save_avatar",
        lambda _src, agent_id: f"avatars/{agent_id}.png",
    )
    user_repo = _FakeUserRepo()
    agent_config_repo = _FakeAgentConfigRepo()
    invite_codes = _FakeInviteCodes()
    service = _service(user_repo=user_repo, agent_config_repo=agent_config_repo, invite_codes=invite_codes)

    result = service.complete_register("temp-1", "invite-1")

    assert result["user"]["id"] == "user-1"
    assert len(user_repo.created) == 3
    human = user_repo.rows["user-1"]
    assert human.type is UserType.HUMAN
    assert human.email == "fresh@example.com"
    owned_agents = user_repo.list_by_owner_user_id("user-1")
    assert len(owned_agents) == 2
    assert all(agent.type is UserType.AGENT for agent in owned_agents)
    assert all(agent.agent_config_id for agent in owned_agents)
    assert [saved[0] for saved in agent_config_repo.saved] == [agent.agent_config_id for agent in owned_agents]
    assert [saved[1]["agent_user_id"] for saved in agent_config_repo.saved] == [agent.id for agent in owned_agents]
    assert invite_codes.used == [("invite-1", "user-1")]


def test_complete_register_does_not_write_member_shell_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    monkeypatch.setattr(member_service, "MEMBERS_DIR", tmp_path)
    monkeypatch.setattr(
        "backend.web.services.auth_service.jwt.decode",
        lambda *_args, **_kwargs: {"sub": "user-1", "email": "fresh@example.com"},
    )
    monkeypatch.setattr(
        "backend.web.routers.entities.process_and_save_avatar",
        lambda _src, agent_id: f"avatars/{agent_id}.png",
    )
    service = _service(
        user_repo=_FakeUserRepo(),
        agent_config_repo=_FakeAgentConfigRepo(),
        invite_codes=_FakeInviteCodes(),
    )

    service.complete_register("temp-1", "invite-1")

    assert list(tmp_path.iterdir()) == []


def test_complete_register_existing_user_path_uses_user_repo_not_member_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "secret-1")
    monkeypatch.setattr(
        "backend.web.services.auth_service.jwt.decode",
        lambda *_args, **_kwargs: {"sub": "user-1", "email": "fresh@example.com"},
    )
    user_repo = _FakeUserRepo()
    user_repo.create(
        UserRow(
            id="user-1",
            type=UserType.HUMAN,
            display_name="fresh",
            email="fresh@example.com",
            mycel_id=10001,
            created_at=1.0,
        )
    )
    user_repo.create(
        UserRow(
            id="agent-1",
            type=UserType.AGENT,
            display_name="Toad",
            owner_user_id="user-1",
            agent_config_id="cfg-1",
            created_at=2.0,
        )
    )
    invite_codes = _FakeInviteCodes()
    service = _service(
        user_repo=user_repo,
        agent_config_repo=_FakeAgentConfigRepo(),
        invite_codes=invite_codes,
    )

    result = service.complete_register("temp-1", "invite-1")

    assert result["user"]["id"] == "user-1"
    assert result["agent"]["id"] == "agent-1"
    assert invite_codes.used == [("invite-1", "user-1")]
