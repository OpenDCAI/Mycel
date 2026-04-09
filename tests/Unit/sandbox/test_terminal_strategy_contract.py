from __future__ import annotations

from sandbox.terminal import TerminalState, terminal_from_row


class _FakeTerminalRepo:
    def __init__(self) -> None:
        self.persist_calls: list[dict[str, object]] = []

    def persist_state(
        self,
        *,
        terminal_id: str,
        cwd: str,
        env_delta_json: str,
        state_version: int,
    ) -> None:
        self.persist_calls.append(
            {
                "terminal_id": terminal_id,
                "cwd": cwd,
                "env_delta_json": env_delta_json,
                "state_version": state_version,
            }
        )


def test_terminal_from_row_uses_strategy_repo_for_default_sandbox_db_under_supabase(monkeypatch, tmp_path) -> None:
    import sandbox.terminal as terminal_module

    default_db = tmp_path / "sandbox.db"
    fake_repo = _FakeTerminalRepo()

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(terminal_module, "resolve_role_db_path", lambda role: default_db)
    monkeypatch.setattr(terminal_module, "build_terminal_repo", lambda **_kwargs: fake_repo)
    monkeypatch.setattr(terminal_module, "_connect", lambda _db_path: (_ for _ in ()).throw(AssertionError("should not touch sqlite")))

    terminal = terminal_from_row(
        {
            "terminal_id": "term-1",
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "cwd": "/workspace",
            "env_delta_json": "{}",
            "state_version": 0,
        },
        default_db,
    )

    terminal.update_state(TerminalState(cwd="/workspace/next", env_delta={"PWD": "/workspace/next"}))

    assert fake_repo.persist_calls == [
        {
            "terminal_id": "term-1",
            "cwd": "/workspace/next",
            "env_delta_json": '{"PWD": "/workspace/next"}',
            "state_version": 1,
        }
    ]


def test_terminal_from_row_explicit_db_path_keeps_sqlite_under_supabase(monkeypatch, tmp_path) -> None:
    import sandbox.terminal as terminal_module

    default_db = tmp_path / "default-sandbox.db"
    explicit_db = tmp_path / "custom-sandbox.db"

    monkeypatch.setenv("LEON_STORAGE_STRATEGY", "supabase")
    monkeypatch.setattr(terminal_module, "resolve_role_db_path", lambda role: default_db)
    monkeypatch.setattr(
        terminal_module,
        "build_terminal_repo",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("strategy repo should not be used")),
    )

    terminal = terminal_from_row(
        {
            "terminal_id": "term-1",
            "thread_id": "thread-1",
            "lease_id": "lease-1",
            "cwd": "/workspace",
            "env_delta_json": "{}",
            "state_version": 0,
        },
        explicit_db,
    )

    assert terminal.__class__.__name__ == "SQLiteTerminal"
