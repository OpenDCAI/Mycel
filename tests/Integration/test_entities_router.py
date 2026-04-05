from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.web.routers import entities as entities_router
from storage.contracts import EntityRow, MemberRow


@pytest.mark.asyncio
async def test_list_entities_excludes_child_agent_branches_from_chat_discovery():
    now = 1_775_223_756.0
    user = MemberRow(id="u1", name="owner", type="human", created_at=now)
    other_human = MemberRow(id="u2", name="other", type="human", created_at=now)
    main_agent_member = MemberRow(
        id="a-main",
        name="Toad",
        type="mycel_agent",
        owner_user_id="u2",
        created_at=now,
    )
    child_agent_member = MemberRow(
        id="a-child",
        name="Toad Branch",
        type="mycel_agent",
        owner_user_id="u2",
        created_at=now,
    )

    app = SimpleNamespace(
        state=SimpleNamespace(
            entity_repo=SimpleNamespace(
                list_by_type=lambda entity_type: (
                    [
                        EntityRow(id="a-main-1", type="agent", member_id="a-main", name="Toad", thread_id="thread-main", created_at=now),
                        EntityRow(
                            id="a-child-1",
                            type="agent",
                            member_id="a-child",
                            name="Toad · 分身1",
                            thread_id="thread-child",
                            created_at=now,
                        ),
                    ]
                    if entity_type == "agent"
                    else []
                )
            ),
            member_repo=SimpleNamespace(list_all=lambda: [user, other_human, main_agent_member, child_agent_member]),
            thread_repo=SimpleNamespace(
                get_by_id=lambda thread_id: (
                    {"is_main": True, "branch_index": 0} if thread_id == "thread-main" else {"is_main": False, "branch_index": 1}
                )
            ),
        )
    )

    result = await entities_router.list_entities(user_id="u1", app=app)

    assert [item["id"] for item in result] == ["u2", "a-main-1"]
