from storage import contracts
from storage.providers.supabase.member_repo import SupabaseMemberRepo
from storage.providers.supabase.thread_repo import SupabaseThreadRepo


def test_member_row_uses_next_thread_seq_not_next_entity_seq() -> None:
    fields = contracts.MemberRow.model_fields
    assert "next_thread_seq" in fields
    assert "next_entity_seq" not in fields


def test_thread_repo_exposes_get_default_thread_not_get_main_thread() -> None:
    assert hasattr(contracts.ThreadRepo, "get_default_thread")
    assert not hasattr(contracts.ThreadRepo, "get_main_thread")


def test_thread_repo_exposes_get_by_user_id() -> None:
    assert hasattr(contracts.ThreadRepo, "get_by_user_id")


def test_member_repo_exposes_increment_thread_seq_not_increment_entity_seq() -> None:
    assert hasattr(contracts.MemberRepo, "increment_thread_seq")
    assert not hasattr(contracts.MemberRepo, "increment_entity_seq")


def test_supabase_member_repo_exposes_increment_thread_seq() -> None:
    assert hasattr(SupabaseMemberRepo, "increment_thread_seq")
    assert not hasattr(SupabaseMemberRepo, "increment_entity_seq")


def test_supabase_thread_repo_exposes_get_default_thread() -> None:
    assert hasattr(SupabaseThreadRepo, "get_default_thread")
    assert not hasattr(SupabaseThreadRepo, "get_main_thread")


def test_supabase_thread_repo_exposes_get_by_user_id() -> None:
    assert hasattr(SupabaseThreadRepo, "get_by_user_id")
