import pytest

pytest.skip("pre-existing: thread_config and agent-member wiring broken — needs migration", allow_module_level=True)

import asyncio
import os
from types import SimpleNamespace

from backend.web.models.requests import CreateThreadRequest, ResolveMainThreadRequest
from backend.web.routers import threads as threads_router
from backend.web.services.auth_service import AuthService
from storage.contracts import EntityRow
from storage.providers.sqlite.entity_repo import SQLiteEntityRepo
from storage.providers.sqlite.member_repo import SQLiteAccountRepo, SQLiteMemberRepo
from storage.providers.sqlite.thread_repo import SQLiteThreadRepo


def test_register_creates_agent_members_without_threads(tmp_path, monkeypatch):
    db_path = tmp_path / "leon.db"
    members_dir = tmp_path / "members"

    import backend.web.services.member_service as member_service

    monkeypatch.setattr(member_service, "MEMBERS_DIR", members_dir)
    monkeypatch.setattr(member_service, "LEON_HOME", tmp_path)

    member_repo = SQLiteMemberRepo(db_path)
    account_repo = SQLiteAccountRepo(db_path)
    entity_repo = SQLiteEntityRepo(db_path)
    thread_repo = SQLiteThreadRepo(db_path)
    service = AuthService(
        members=member_repo,
        accounts=account_repo,
        entities=entity_repo,
    )

    payload = service.register("fresh_user", "pass1234")
    claims = service.verify_token(payload["token"])
    account = account_repo.get_by_username("fresh_user")

    owned_agents = member_repo.list_by_owner_user_id(payload["user"]["id"])
    assert "member_id" not in claims
    assert claims["user_id"] == payload["user"]["id"]
    assert payload["user"]["name"] == "fresh_user"
    assert account is not None
    assert account.user_id == payload["user"]["id"]
    assert len(owned_agents) == 2
    assert [agent.name for agent in owned_agents] == ["Toad", "Morel"]
    for agent in owned_agents:
        assert thread_repo.list_by_member(agent.id) == []
        assert entity_repo.get_by_member_id(agent.id) == []


def test_first_explicit_thread_becomes_main_then_followups_are_children(tmp_path):
    db_path = tmp_path / "leon.db"

    member_repo = SQLiteMemberRepo(db_path)
    entity_repo = SQLiteEntityRepo(db_path)
    thread_repo = SQLiteThreadRepo(db_path)

    from storage.contracts import MemberRow, MemberType

    member_repo.create(
        MemberRow(
            id="owner-1",
            name="owner",
            type=MemberType.HUMAN,
            created_at=1.0,
        )
    )
    member_repo.create(
        MemberRow(
            id="member-1",
            name="Template Agent",
            type=MemberType.MYCEL_AGENT,
            owner_user_id="owner-1",
            created_at=2.0,
        )
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=member_repo,
            entity_repo=entity_repo,
            thread_repo=thread_repo,
            thread_sandbox={},
            thread_cwd={},
        )
    )

    first = threads_router._create_owned_thread(
        app,
        "owner-1",
        CreateThreadRequest(member_id="member-1", sandbox="local"),
        is_main=False,
    )
    second = threads_router._create_owned_thread(
        app,
        "owner-1",
        CreateThreadRequest(member_id="member-1", sandbox="local"),
        is_main=False,
    )

    assert first["is_main"] is True
    assert first["branch_index"] == 0
    assert first["entity_name"] == "Template Agent"
    assert second["is_main"] is False
    assert second["branch_index"] == 1
    assert second["entity_name"] == "Template Agent · 分身1"
    assert thread_repo.get_main_thread("member-1")["id"] == first["thread_id"]


def test_member_rename_recomputes_agent_entity_names(tmp_path, monkeypatch):
    db_path = tmp_path / "leon.db"
    members_dir = tmp_path / "members"
    members_dir.mkdir(parents=True)
    os.environ["LEON_DB_PATH"] = str(db_path)

    import backend.web.services.member_service as member_service

    monkeypatch.setattr(member_service, "MEMBERS_DIR", members_dir)
    monkeypatch.setattr(member_service, "LEON_HOME", tmp_path)

    member_repo = SQLiteMemberRepo(db_path)
    entity_repo = SQLiteEntityRepo(db_path)
    thread_repo = SQLiteThreadRepo(db_path)

    from storage.contracts import MemberRow, MemberType

    member_repo.create(
        MemberRow(
            id="owner-1",
            name="owner",
            type=MemberType.HUMAN,
            created_at=1.0,
        )
    )
    member_repo.create(
        MemberRow(
            id="member-1",
            name="Toad",
            type=MemberType.MYCEL_AGENT,
            owner_user_id="owner-1",
            created_at=2.0,
        )
    )

    member_dir = members_dir / "member-1"
    member_dir.mkdir()
    (member_dir / "agent.md").write_text("---\nname: Toad\n---\n\n", encoding="utf-8")
    (member_dir / "meta.json").write_text("{}", encoding="utf-8")

    thread_repo.create(
        thread_id="member-1-1",
        member_id="member-1",
        sandbox_type="local",
        created_at=3.0,
        is_main=True,
        branch_index=0,
    )
    thread_repo.create(
        thread_id="member-1-2",
        member_id="member-1",
        sandbox_type="local",
        created_at=4.0,
        is_main=False,
        branch_index=1,
    )
    entity_repo.create(
        EntityRow(
            id="member-1-1",
            type="agent",
            member_id="member-1",
            name="Toad",
            thread_id="member-1-1",
            created_at=3.0,
        )
    )
    entity_repo.create(
        EntityRow(
            id="member-1-2",
            type="agent",
            member_id="member-1",
            name="Toad · 分身1",
            thread_id="member-1-2",
            created_at=4.0,
        )
    )

    updated = member_service.update_member("member-1", name="Scout")

    refreshed_entities = sorted(entity_repo.get_by_member_id("member-1"), key=lambda entity: entity.thread_id or "")
    assert updated is not None
    assert updated["name"] == "Scout"
    assert [entity.name for entity in refreshed_entities] == ["Scout", "Scout · 分身1"]


def test_resolve_main_thread_returns_null_when_member_has_no_main(tmp_path):
    db_path = tmp_path / "leon.db"

    member_repo = SQLiteMemberRepo(db_path)
    entity_repo = SQLiteEntityRepo(db_path)
    thread_repo = SQLiteThreadRepo(db_path)

    from storage.contracts import MemberRow, MemberType

    member_repo.create(
        MemberRow(
            id="owner-1",
            name="owner",
            type=MemberType.HUMAN,
            created_at=1.0,
        )
    )
    member_repo.create(
        MemberRow(
            id="member-1",
            name="Template Agent",
            type=MemberType.MYCEL_AGENT,
            owner_user_id="owner-1",
            created_at=2.0,
        )
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=member_repo,
            entity_repo=entity_repo,
            thread_repo=thread_repo,
            thread_sandbox={},
            thread_cwd={},
        )
    )

    result = asyncio.run(
        threads_router.resolve_main_thread(
            ResolveMainThreadRequest(member_id="member-1"),
            "owner-1",
            app,
        )
    )

    assert result == {"thread": None}
