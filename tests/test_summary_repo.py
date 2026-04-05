import pytest

from storage.providers.supabase.summary_repo import SupabaseSummaryRepo


from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_summary_repo_save_list_get_and_delete():
    tables: dict[str, list[dict]] = {"summaries": []}
    repo = SupabaseSummaryRepo(client=FakeSupabaseClient(tables=tables))

    repo.ensure_tables()
    repo.save_summary(
        summary_id="s-1",
        thread_id="t-1",
        summary_text="first",
        compact_up_to_index=10,
        compacted_at=20,
        is_split_turn=False,
        split_turn_prefix=None,
        created_at="2025-01-01T00:00:00",
    )
    repo.save_summary(
        summary_id="s-2",
        thread_id="t-1",
        summary_text="second",
        compact_up_to_index=30,
        compacted_at=40,
        is_split_turn=True,
        split_turn_prefix="prefix",
        created_at="2025-01-01T00:01:00",
    )

    latest = repo.get_latest_summary_row("t-1")
    assert latest is not None
    assert latest["summary_id"] == "s-2"
    assert latest["summary_text"] == "second"
    assert latest["is_split_turn"] is True
    assert latest["split_turn_prefix"] == "prefix"
    assert latest["is_active"] is True

    listed = repo.list_summaries("t-1")
    assert [row["summary_id"] for row in listed] == ["s-2", "s-1"]

    active_count = sum(1 for row in tables["summaries"] if row["is_active"])
    assert active_count == 1

    repo.delete_thread_summaries("t-1")
    assert repo.list_summaries("t-1") == []
    assert repo.get_latest_summary_row("t-1") is None


def test_supabase_summary_repo_requires_compatible_client():
    with pytest.raises(RuntimeError, match="table\\(name\\)"):
        SupabaseSummaryRepo(client=object())
