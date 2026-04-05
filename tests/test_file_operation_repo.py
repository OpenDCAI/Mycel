from storage.providers.sqlite.file_operation_repo import SQLiteFileOperationRepo
import pytest

from storage.providers.supabase.file_operation_repo import SupabaseFileOperationRepo


def test_record_and_query_file_operations(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteFileOperationRepo(db_path)

    op1 = repo.record("t-1", "cp-1", "write", "/tmp/a.txt", None, "hello")
    op2 = repo.record("t-1", "cp-2", "edit", "/tmp/a.txt", "hello", "world", [{"old": "hello", "new": "world"}])

    assert op1 != op2

    rows = repo.get_operations_for_thread("t-1")
    assert len(rows) == 2
    assert rows[0].checkpoint_id == "cp-1"
    assert rows[1].changes == [{"old": "hello", "new": "world"}]


def test_mark_reverted_and_status_filter(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteFileOperationRepo(db_path)

    op1 = repo.record("t-2", "cp-1", "write", "/tmp/a.txt", None, "a")
    repo.record("t-2", "cp-1", "write", "/tmp/b.txt", None, "b")

    repo.mark_reverted([op1])

    applied = repo.get_operations_for_thread("t-2", status="applied")
    reverted = repo.get_operations_for_thread("t-2", status="reverted")

    assert len(applied) == 1
    assert len(reverted) == 1
    assert reverted[0].id == op1


def test_delete_thread_operations(tmp_path):
    db_path = tmp_path / "leon.db"
    repo = SQLiteFileOperationRepo(db_path)

    repo.record("t-3", "cp-1", "write", "/tmp/a.txt", None, "a")
    repo.record("t-3", "cp-2", "write", "/tmp/b.txt", None, "b")
    repo.record("t-x", "cp-x", "write", "/tmp/c.txt", None, "c")

    deleted = repo.delete_thread_operations("t-3")
    assert deleted == 2
    assert repo.get_operations_for_thread("t-3") == []
    assert len(repo.get_operations_for_thread("t-x")) == 1


from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_file_operation_repo_record_and_query():
    tables: dict[str, list[dict]] = {"file_operations": []}
    repo = SupabaseFileOperationRepo(client=FakeSupabaseClient(tables=tables))

    op1 = repo.record("t-1", "cp-1", "write", "/tmp/a.txt", None, "hello")
    op2 = repo.record("t-1", "cp-2", "edit", "/tmp/a.txt", "hello", "world", [{"old": "hello", "new": "world"}])

    rows = repo.get_operations_for_thread("t-1")
    assert [row.id for row in rows] == [op1, op2]
    assert rows[1].changes == [{"old": "hello", "new": "world"}]

    for_checkpoint = repo.get_operations_for_checkpoint("t-1", "cp-2")
    assert len(for_checkpoint) == 1
    assert for_checkpoint[0].id == op2
    assert repo.count_operations_for_checkpoint("t-1", "cp-2") == 1

    after_cp2 = repo.get_operations_after_checkpoint("t-1", "cp-2")
    assert [row.id for row in after_cp2] == [op2]


def test_supabase_file_operation_repo_mark_reverted_and_delete_thread():
    tables: dict[str, list[dict]] = {"file_operations": []}
    repo = SupabaseFileOperationRepo(client=FakeSupabaseClient(tables=tables))

    op1 = repo.record("t-2", "cp-1", "write", "/tmp/a.txt", None, "a")
    repo.record("t-2", "cp-1", "write", "/tmp/b.txt", None, "b")
    repo.record("t-x", "cp-x", "write", "/tmp/c.txt", None, "c")

    repo.mark_reverted([op1])

    applied = repo.get_operations_for_thread("t-2", status="applied")
    reverted = repo.get_operations_for_thread("t-2", status="reverted")
    assert len(applied) == 1
    assert len(reverted) == 1
    assert reverted[0].id == op1

    deleted = repo.delete_thread_operations("t-2")
    assert deleted == 2
    assert repo.get_operations_for_thread("t-2") == []
    assert len(repo.get_operations_for_thread("t-x")) == 1


def test_supabase_file_operation_repo_requires_compatible_client():
    with pytest.raises(RuntimeError, match="table\\(name\\)"):
        SupabaseFileOperationRepo(client=object())
