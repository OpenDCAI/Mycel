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
                get_main_thread=lambda member_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0}
                    if member_id == "a-main"
                    else {"id": "thread-child", "is_main": False, "branch_index": 1}
                )
            ),
        )
    )

    result = await entities_router.list_entities(user_id="u1", app=app)

    # Current user (u1) is excluded; all other members are returned.
    ids = [item["id"] for item in result]
    assert ids == ["u2", "a-main", "a-child"]

    # Human entry has no thread metadata.
    human_item = next(i for i in result if i["id"] == "u2")
    assert human_item["type"] == "human"
    assert human_item["thread_id"] is None

    # Main agent: thread metadata from thread_repo.
    main_item = next(i for i in result if i["id"] == "a-main")
    assert main_item["thread_id"] == "thread-main"
    assert main_item["is_main"] is True
    assert main_item["branch_index"] == 0

    # Child agent: also returned (frontend decides whether to hide it).
    child_item = next(i for i in result if i["id"] == "a-child")
    assert child_item["thread_id"] == "thread-child"
    assert child_item["is_main"] is False
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
                get_main_thread=lambda member_id: (
                    {"id": "thread-main", "is_main": True, "branch_index": 0} if member_id == "a-main" else None
                )
            ),
        )
    )

    result = await entities_router.get_agent_thread("a-main", current_user_id="u2", app=app)

    assert result == {"user_id": "a-main", "thread_id": "thread-main"}
