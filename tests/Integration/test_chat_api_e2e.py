"""End-to-end integration tests for chat API.

Requires real Supabase connection (SUPABASE_URL).
Calls route functions directly with real repos — no HTTP overhead, no mocked
business logic.  All created chats are deleted in finally-blocks.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from backend.web.routers import messaging as messaging_router

ALICE_ID = "8b71de74-4007-4acf-a223-e47d8cf87455"
BOB_ID = "c113d5d0-2381-4a9a-bc88-2208f42912b1"

pytestmark = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_INTERNAL_URL") or os.getenv("SUPABASE_PUBLIC_URL")),
    reason="SUPABASE_URL not set — skipping e2e tests",
)


@pytest.fixture(scope="module")
def real_app():
    from backend.web.core.supabase_factory import (
        create_messaging_supabase_client,
        create_supabase_client,
    )
    from messaging.service import MessagingService
    from storage.container import StorageContainer
    from storage.providers.supabase.messaging_repo import (
        SupabaseChatMemberRepo,
        SupabaseMessageReadRepo,
        SupabaseMessagesRepo,
    )

    _supabase = create_supabase_client()
    _msg_supabase = create_messaging_supabase_client()
    container = StorageContainer(supabase_client=_supabase)

    chat_member_repo = SupabaseChatMemberRepo(_msg_supabase)
    messages_repo = SupabaseMessagesRepo(_msg_supabase)
    message_read_repo = SupabaseMessageReadRepo(_msg_supabase)
    member_repo = container.member_repo()
    thread_repo = container.thread_repo()
    chat_repo = container.chat_repo()

    messaging_svc = MessagingService(
        chat_repo=chat_repo,
        chat_member_repo=chat_member_repo,
        messages_repo=messages_repo,
        message_read_repo=message_read_repo,
        member_repo=member_repo,
        thread_repo=thread_repo,
    )

    return SimpleNamespace(
        state=SimpleNamespace(
            messaging_service=messaging_svc,
            chat_repo=chat_repo,
            member_repo=member_repo,
            thread_repo=thread_repo,
            chat_member_repo=chat_member_repo,
        )
    )


@pytest.mark.asyncio
async def test_chat_lifecycle(real_app):
    """Alice creates DM with Bob, sends message, Bob marks read, check read_status."""
    result = await messaging_router.create_chat(
        messaging_router.CreateChatBody(user_ids=[ALICE_ID, BOB_ID]),
        user_id=ALICE_ID,
        app=real_app,
    )
    chat_id = result["id"]

    try:
        # Alice sends message
        msg = await messaging_router.send_message(
            chat_id,
            messaging_router.SendMessageBody(content="你好 Bob — e2e test", sender_id=ALICE_ID),
            user_id=ALICE_ID,
            app=real_app,
        )
        assert msg["content"] == "你好 Bob — e2e test"
        assert msg["sender_id"] == ALICE_ID
        msg_id = msg["id"]

        # Bob lists messages — can see Alice's message
        bob_msgs = await messaging_router.list_messages(chat_id, user_id=BOB_ID, app=real_app, limit=50, before=None)
        assert any(m["id"] == msg_id for m in bob_msgs)

        # Bob marks chat read
        read_result = await messaging_router.mark_read(chat_id, user_id=BOB_ID, app=real_app)
        assert read_result["status"] == "ok"

        # Alice checks chat detail — Bob appears in read_status
        chat_detail = await messaging_router.get_chat(chat_id, user_id=ALICE_ID, app=real_app)
        assert BOB_ID in chat_detail["read_status"]

        # Alice's chat list includes this chat
        alice_chats = await messaging_router.list_chats(user_id=ALICE_ID, app=real_app)
        assert any(c["id"] == chat_id for c in alice_chats)

    finally:
        await messaging_router.delete_chat(chat_id, user_id=ALICE_ID, app=real_app)


@pytest.mark.asyncio
async def test_pin_rename(real_app):
    """Pin and rename a chat."""
    result = await messaging_router.create_chat(
        messaging_router.CreateChatBody(user_ids=[ALICE_ID, BOB_ID]),
        user_id=ALICE_ID,
        app=real_app,
    )
    chat_id = result["id"]

    try:
        # Pin
        pin_result = await messaging_router.pin_chat(
            chat_id,
            messaging_router.PinChatBody(pinned=True),
            user_id=ALICE_ID,
            app=real_app,
        )
        assert pin_result == {"status": "ok", "pinned": True}

        # Rename
        rename_result = await messaging_router.update_chat(
            chat_id,
            messaging_router.PatchChatBody(title="测试群-e2e"),
            user_id=ALICE_ID,
            app=real_app,
        )
        assert rename_result["title"] == "测试群-e2e"

    finally:
        await messaging_router.delete_chat(chat_id, user_id=ALICE_ID, app=real_app)


@pytest.mark.asyncio
async def test_search_messages(real_app):
    """Send a unique message then verify it appears in search results."""
    result = await messaging_router.create_chat(
        messaging_router.CreateChatBody(user_ids=[ALICE_ID, BOB_ID]),
        user_id=ALICE_ID,
        app=real_app,
    )
    chat_id = result["id"]
    unique_term = "e2e-search-xq7z9"

    try:
        await messaging_router.send_message(
            chat_id,
            messaging_router.SendMessageBody(content=f"Q3环比下滑分析 {unique_term}", sender_id=ALICE_ID),
            user_id=ALICE_ID,
            app=real_app,
        )

        search_result = await messaging_router.search_messages(
            q=unique_term,
            user_id=ALICE_ID,
            app=real_app,
        )
        assert len(search_result) > 0
        assert any(unique_term in m["content"] for m in search_result)

    finally:
        await messaging_router.delete_chat(chat_id, user_id=ALICE_ID, app=real_app)


@pytest.mark.asyncio
async def test_concurrent_sends(real_app):
    """10 concurrent sends produce distinct messages with no data loss."""
    result = await messaging_router.create_chat(
        messaging_router.CreateChatBody(user_ids=[ALICE_ID, BOB_ID]),
        user_id=ALICE_ID,
        app=real_app,
    )
    chat_id = result["id"]

    try:
        tasks = [
            messaging_router.send_message(
                chat_id,
                messaging_router.SendMessageBody(content=f"concurrent-msg-{i}", sender_id=ALICE_ID),
                user_id=ALICE_ID,
                app=real_app,
            )
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)

        # All belong to the same chat, all have unique IDs
        assert all(r["chat_id"] == chat_id for r in results)
        assert len({r["id"] for r in results}) == 10

        # All 10 messages are persisted
        msgs = await messaging_router.list_messages(chat_id, user_id=ALICE_ID, app=real_app, limit=50, before=None)
        contents = {m["content"] for m in msgs}
        for i in range(10):
            assert f"concurrent-msg-{i}" in contents

    finally:
        await messaging_router.delete_chat(chat_id, user_id=ALICE_ID, app=real_app)
