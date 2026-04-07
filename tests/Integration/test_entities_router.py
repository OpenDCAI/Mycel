from __future__ import annotations

# NOTE: EntityRow was deleted from storage/contracts.py in the entity→member
# refactor (commit cc156856). The old test asserted that child agent branches
# were filtered out on the backend; that filtering was removed along with the
# entity layer — it is now the frontend's responsibility. The test below
# verifies the current production behaviour of list_entities:
#   • current user is excluded
#   • other humans and agents are all included (no branch filtering)
#   • thread metadata (is_main, branch_index) is attached from thread_repo
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.web.routers import entities as entities_router
from storage.contracts import MemberRow, MemberType


@pytest.mark.asyncio
async def test_list_entities_excludes_current_user_and_returns_all_others():
    now = 1_775_223_756.0
    current_user = MemberRow(id="u1", name="owner", type=MemberType.HUMAN, created_at=now)
    other_human = MemberRow(id="u2", name="other", type=MemberType.HUMAN, created_at=now)
    main_agent = MemberRow(
        id="a-main",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u2",
        created_at=now,
    )
    child_agent = MemberRow(
        id="a-child",
        name="Toad Branch",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u2",
        created_at=now,
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=SimpleNamespace(list_all=lambda: [current_user, other_human, main_agent, child_agent]),
            thread_repo=SimpleNamespace(
                get_default_thread=lambda member_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0}
                    if member_id == "a-main"
                    else {"id": "thread-child", "is_main": False, "branch_index": 1}
                )
            ),
        )
    )

    result = await entities_router.list_entities(user_id="u1", app=app)

    # Current user (u1) is excluded; all other members are returned.
    identities = [(item["type"], item.get("user_id"), item.get("member_id")) for item in result]
    assert identities == [
        ("human", "u2", None),
        ("mycel_agent", None, "a-main"),
        ("mycel_agent", None, "a-child"),
    ]

    # Human entry is keyed by social user identity, not a generic mixed id.
    human_item = next(i for i in result if i["user_id"] == "u2")
    assert human_item["type"] == "human"
    assert "id" not in human_item
    assert human_item["default_thread_id"] is None

    # Agent entry is keyed by member template plus explicit default thread.
    main_item = next(i for i in result if i.get("member_id") == "a-main")
    assert "id" not in main_item
    assert main_item["default_thread_id"] == "thread-main"
    assert main_item["is_default_thread"] is True
    assert main_item["branch_index"] == 0

    # Child agent: also returned (frontend decides whether to hide it).
    child_item = next(i for i in result if i.get("member_id") == "a-child")
    assert child_item["default_thread_id"] == "thread-child"
    assert child_item["is_default_thread"] is False
    assert child_item["branch_index"] == 1


@pytest.mark.asyncio
async def test_get_agent_thread_reads_main_thread_from_thread_repo():
    now = 1_775_223_756.0
    agent = MemberRow(
        id="a-main",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u2",
        created_at=now,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=SimpleNamespace(get_by_id=lambda member_id: agent if member_id == "a-main" else None),
            thread_repo=SimpleNamespace(
                get_default_thread=lambda member_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0} if member_id == "a-main" else None
                )
            ),
        )
    )

    result = await entities_router.get_agent_thread("a-main", current_user_id="u2", app=app)

    assert result == {"member_id": "a-main", "default_thread_id": "thread-main"}


def test_get_member_or_404_returns_member():
    now = 1_775_223_756.0
    agent = MemberRow(
        id="a-main",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u2",
        created_at=now,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=SimpleNamespace(get_by_id=lambda member_id: agent if member_id == "a-main" else None),
        )
    )

    result = entities_router._get_member_or_404(app, "a-main")

    assert result is agent


def test_get_member_or_404_raises_for_missing_member():
    app = SimpleNamespace(
        state=SimpleNamespace(
            member_repo=SimpleNamespace(get_by_id=lambda _member_id: None),
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        entities_router._get_member_or_404(app, "missing")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Member not found"


@pytest.mark.asyncio
async def test_get_entity_profile_uses_member_lookup_helper(monkeypatch: pytest.MonkeyPatch):
    now = 1_775_223_756.0
    agent = MemberRow(
        id="a-main",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u2",
        created_at=now,
    )
    app = SimpleNamespace(state=SimpleNamespace())
    calls: list[tuple[object, str]] = []

    def _fake_get_member_or_404(app_obj, member_id: str):
        calls.append((app_obj, member_id))
        return agent

    monkeypatch.setattr(entities_router, "_get_member_or_404", _fake_get_member_or_404)

    result = await entities_router.get_entity_profile("a-main", app)

    assert result["id"] == "a-main"
    assert calls == [(app, "a-main")]


@pytest.mark.asyncio
async def test_get_agent_thread_uses_member_lookup_helper(monkeypatch: pytest.MonkeyPatch):
    now = 1_775_223_756.0
    agent = MemberRow(
        id="a-main",
        name="Toad",
        type=MemberType.MYCEL_AGENT,
        owner_user_id="u2",
        created_at=now,
    )
    app = SimpleNamespace(
        state=SimpleNamespace(
            thread_repo=SimpleNamespace(
                get_default_thread=lambda member_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0} if member_id == "a-main" else None
                )
            ),
        )
    )
    calls: list[tuple[object, str]] = []

    def _fake_get_member_or_404(app_obj, member_id: str):
        calls.append((app_obj, member_id))
        return agent

    monkeypatch.setattr(entities_router, "_get_member_or_404", _fake_get_member_or_404)

    result = await entities_router.get_agent_thread("a-main", current_user_id="u2", app=app)

    assert result == {"member_id": "a-main", "default_thread_id": "thread-main"}
    assert calls == [(app, "a-main")]
