from __future__ import annotations

from storage.container import StorageContainer
from storage.runtime import build_storage_container
from tests.fakes.supabase import FakeSupabaseClient


def test_storage_container_exposes_messaging_repos() -> None:
    container = StorageContainer(supabase_client=FakeSupabaseClient())

    assert container.chat_member_repo().__class__.__name__ == "SupabaseChatMemberRepo"
    assert container.messages_repo().__class__.__name__ == "SupabaseMessagesRepo"
    assert container.relationship_repo().__class__.__name__ == "SupabaseRelationshipRepo"


def test_build_storage_container_exposes_messaging_repos() -> None:
    container = build_storage_container(supabase_client=FakeSupabaseClient())

    assert container.chat_member_repo().__class__.__name__ == "SupabaseChatMemberRepo"
    assert container.messages_repo().__class__.__name__ == "SupabaseMessagesRepo"
    assert container.relationship_repo().__class__.__name__ == "SupabaseRelationshipRepo"
