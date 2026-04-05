from storage.providers.supabase.chat_repo import SupabaseChatMessageRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_chat_message_repo_has_unread_mention_tracks_mentions_after_last_read():
    tables = {
        "chat_entities": [
            {
                "chat_id": "chat-1",
                "user_id": "entity-target",
                "joined_at": 1.0,
                "last_read_at": 5.0,
            }
        ],
        "chat_messages": [
            {
                "id": "msg-old",
                "chat_id": "chat-1",
                "sender_id": "entity-other",
                "content": "old mention",
                "mentions": '["entity-target"]',
                "created_at": 4.0,
            },
            {
                "id": "msg-self",
                "chat_id": "chat-1",
                "sender_id": "entity-target",
                "content": "self mention",
                "mentions": '["entity-target"]',
                "created_at": 6.0,
            },
            {
                "id": "msg-unread",
                "chat_id": "chat-1",
                "sender_id": "entity-other",
                "content": "new mention",
                "mentions": '["entity-target"]',
                "created_at": 7.0,
            },
            {
                "id": "msg-unread-no-mention",
                "chat_id": "chat-1",
                "sender_id": "entity-other",
                "content": "plain unread",
                "mentions": "[]",
                "created_at": 8.0,
            },
        ],
    }
    repo = SupabaseChatMessageRepo(FakeSupabaseClient(tables))

    assert repo.has_unread_mention("chat-1", "entity-target") is True


def test_supabase_chat_message_repo_has_unread_mention_false_without_matching_unread_mentions():
    tables = {
        "chat_entities": [
            {
                "chat_id": "chat-1",
                "user_id": "entity-target",
                "joined_at": 1.0,
                "last_read_at": 5.0,
            }
        ],
        "chat_messages": [
            {
                "id": "msg-unread",
                "chat_id": "chat-1",
                "sender_id": "entity-other",
                "content": "plain unread",
                "mentions": "[]",
                "created_at": 7.0,
            }
        ],
    }
    repo = SupabaseChatMessageRepo(FakeSupabaseClient(tables))

    assert repo.has_unread_mention("chat-1", "entity-target") is False


def test_supabase_chat_message_repo_has_unread_mention_false_without_membership_row():
    tables = {
        "chat_entities": [],
        "chat_messages": [
            {
                "id": "msg-unread",
                "chat_id": "chat-1",
                "sender_id": "entity-other",
                "content": "new mention",
                "mentions": '["entity-target"]',
                "created_at": 7.0,
            }
        ],
    }
    repo = SupabaseChatMessageRepo(FakeSupabaseClient(tables))

    assert repo.count_unread("chat-1", "entity-target") == 0
    assert repo.has_unread_mention("chat-1", "entity-target") is False
