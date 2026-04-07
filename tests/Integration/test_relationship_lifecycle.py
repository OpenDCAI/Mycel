"""Integration tests for relationship state machine.

Requires real Supabase connection (SUPABASE_PUBLIC_URL or SUPABASE_INTERNAL_URL).
Uses the existing Alice↔Bob visit relationship (ID is stable across test runs).
State is always restored: upgrade → hire, then downgrade → visit.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from messaging.relationships import router as rel_router

ALICE_ID = "8b71de74-4007-4acf-a223-e47d8cf87455"
BOB_ID = "c113d5d0-2381-4a9a-bc88-2208f42912b1"
# Stable Alice↔Bob visit relationship created during initial DB seed
ALICE_BOB_REL_ID = "31c683f8-33b3-43ae-bfc9-3d632fb022f7"

pytestmark = pytest.mark.skipif(
    not (os.getenv("SUPABASE_PUBLIC_URL") or os.getenv("SUPABASE_INTERNAL_URL")),
    reason="Supabase env vars not set — skipping e2e tests",
)


@pytest.fixture(scope="module")
def rel_app():
    from backend.web.core.supabase_factory import (
        create_messaging_supabase_client,
        create_supabase_client,
    )
    from messaging.relationships.service import RelationshipService
    from storage.container import StorageContainer
    from storage.providers.supabase.messaging_repo import SupabaseRelationshipRepo

    _supabase = create_supabase_client()
    _msg_supabase = create_messaging_supabase_client()
    container = StorageContainer(supabase_client=_supabase)

    relationship_repo = SupabaseRelationshipRepo(_msg_supabase)
    member_repo = container.member_repo()
    thread_repo = container.thread_repo()

    relationship_svc = RelationshipService(
        relationship_repo,
        member_repo=member_repo,
        thread_repo=thread_repo,
    )

    return SimpleNamespace(
        state=SimpleNamespace(
            relationship_service=relationship_svc,
            member_repo=member_repo,
        )
    )


@pytest.mark.asyncio
async def test_upgrade_downgrade_visit(rel_app):
    """visit → hire (upgrade) → visit (downgrade): state is fully restored."""
    # Upgrade: Alice promotes Bob to hire
    hire_row = await rel_router.upgrade_relationship(
        ALICE_BOB_REL_ID,
        rel_router.RelationshipActionBody(),
        user_id=ALICE_ID,
        app=rel_app,
    )
    assert hire_row["state"] == "hire"

    # Downgrade: Alice reverts Bob to visit
    visit_row = await rel_router.downgrade_relationship(
        ALICE_BOB_REL_ID,
        user_id=ALICE_ID,
        app=rel_app,
    )
    assert visit_row["state"] == "visit"


@pytest.mark.asyncio
async def test_duplicate_request_rejected(rel_app):
    """Requesting someone already in visit state raises 409."""
    with pytest.raises(HTTPException) as exc:
        await rel_router.request_relationship(
            rel_router.RelationshipRequestBody(target_user_id=BOB_ID),
            user_id=ALICE_ID,
            app=rel_app,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_list_relationships_includes_member_info(rel_app):
    """list_relationships returns enriched other_name / other_mycel_id / other_avatar_url."""
    rows = await rel_router.list_relationships(user_id=ALICE_ID, app=rel_app)
    assert len(rows) > 0

    bob_rel = next((r for r in rows if r["other_user_id"] == BOB_ID), None)
    assert bob_rel is not None, "Alice should have Bob in her relationship list"
    assert bob_rel["other_name"] == "bob"
    assert "other_mycel_id" in bob_rel
    assert "other_avatar_url" in bob_rel
