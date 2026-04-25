from __future__ import annotations

from storage.providers.supabase.chat_session_repo import SupabaseChatSessionRepo
from storage.providers.supabase.terminal_repo import SupabaseTerminalRepo
from tests.fakes.supabase import FakeSupabaseClient


def _client(tables: dict[str, list[dict]] | None = None) -> FakeSupabaseClient:
    return FakeSupabaseClient(
        tables={} if tables is None else tables,
        auto_seq_tables={"container.terminal_command_chunks"},
    )


def test_supabase_terminal_repo_tracks_active_and_default_terminal() -> None:
    tables: dict[str, list[dict]] = {}
    repo = SupabaseTerminalRepo(client=_client(tables))

    first = repo.create("term-1", "thread-1", "runtime-1", initial_cwd="/workspace")
    second = repo.create("term-2", "thread-1", "runtime-1", initial_cwd="/workspace/app")
    repo.set_active("thread-1", "term-2")
    repo.persist_state(terminal_id="term-2", cwd="/workspace/pkg", env_delta_json='{"A":"1"}', state_version=1)

    assert first["terminal_id"] == "term-1"
    assert second["terminal_id"] == "term-2"
    assert repo.get_default("thread-1")["terminal_id"] == "term-1"
    assert repo.get_active("thread-1")["terminal_id"] == "term-2"
    assert repo.get_by_id("term-2")["cwd"] == "/workspace/pkg"
    assert repo.summarize_threads(["thread-1"]) == {"thread-1": {"active_terminal_id": "term-2", "latest_terminal_id": "term-2"}}


def test_supabase_chat_session_repo_tracks_sessions_and_commands() -> None:
    tables = {
        "container.abstract_terminals": [
            {
                "terminal_id": "term-1",
                "thread_id": "thread-1",
                "sandbox_runtime_id": "runtime-1",
                "cwd": "/workspace",
                "env_delta_json": "{}",
                "state_version": 0,
                "created_at": "2026-04-25T00:00:00+00:00",
                "updated_at": "2026-04-25T00:00:00+00:00",
            }
        ]
    }
    repo = SupabaseChatSessionRepo(client=_client(tables))

    session = repo.create_session(
        "session-1",
        "thread-1",
        "term-1",
        "runtime-1",
        runtime_id="provider-session-1",
        started_at="2026-04-25T00:00:01+00:00",
        last_active_at="2026-04-25T00:00:01+00:00",
    )
    repo.upsert_command(
        command_id="cmd-1",
        terminal_id="term-1",
        chat_session_id="session-1",
        command_line="pwd",
        cwd="/workspace",
        status="running",
        stdout="",
        stderr="",
        exit_code=None,
        updated_at="2026-04-25T00:00:02+00:00",
        finished_at=None,
    )
    repo.append_command_chunks(command_id="cmd-1", stdout_chunks=["/workspace\n"], stderr_chunks=[], created_at="2026-04-25T00:00:03+00:00")

    assert session["session_id"] == "session-1"
    assert repo.get_session("thread-1", "term-1")["runtime_id"] == "provider-session-1"
    assert repo.terminal_has_running_command("term-1") is True
    assert repo.sandbox_runtime_has_running_command("runtime-1") is True
    assert repo.get_command(command_id="cmd-1", terminal_id="term-1")["status"] == "running"
    assert repo.list_command_chunks(command_id="cmd-1") == [{"stream": "stdout", "content": "/workspace\n"}]

    repo.delete_by_thread("thread-1")

    assert repo.get_session("thread-1", "term-1") is None
    assert tables["container.terminal_commands"] == []
    assert tables["container.terminal_command_chunks"] == []
