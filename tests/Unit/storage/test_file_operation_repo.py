from storage.providers.supabase.file_operation_repo import SupabaseFileOperationRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_file_operation_repo_uses_agent_schema() -> None:
    tables: dict[str, list[dict]] = {"agent.file_operations": []}
    repo = SupabaseFileOperationRepo(client=FakeSupabaseClient(tables=tables))

    op_id = repo.record(
        thread_id="thread-1",
        checkpoint_id="checkpoint-1",
        operation_type="write",
        file_path="/tmp/example.txt",
        before_content=None,
        after_content="hello",
        changes=[{"line": 1}],
    )

    assert tables["agent.file_operations"][0]["id"] == op_id
    assert tables["agent.file_operations"][0]["thread_id"] == "thread-1"
    assert repo.delete_thread_operations("thread-1") == 1
    assert tables["agent.file_operations"] == []
    assert "file_operations" not in tables
