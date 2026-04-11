from storage.providers.supabase.eval_repo import SupabaseEvalRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_eval_repo_updates_same_row_across_run_lifecycle() -> None:
    client = FakeSupabaseClient(tables={})
    repo = SupabaseEvalRepo(client)

    repo.upsert_run_header(
        run_id="run-1",
        thread_id="thread-1",
        started_at="2026-04-08T12:00:00Z",
        user_message="hello",
        status="running",
    )

    runs = repo.list_runs(thread_id="thread-1")
    assert runs == [
        {
            "id": "run-1",
            "thread_id": "thread-1",
            "started_at": "2026-04-08T12:00:00Z",
            "finished_at": None,
            "status": "running",
            "user_message": "hello",
        }
    ]

    repo.finalize_run(
        run_id="run-1",
        finished_at="2026-04-08T12:01:00Z",
        final_response="done",
        status="completed",
        run_tree_json="{}",
        trajectory_json='{"id":"run-1"}',
    )

    runs = repo.list_runs(thread_id="thread-1")
    assert runs[0]["id"] == "run-1"
    assert runs[0]["status"] == "completed"
    assert runs[0]["finished_at"] == "2026-04-08T12:01:00Z"
    assert repo.get_trajectory_json("run-1") == '{"id":"run-1"}'
