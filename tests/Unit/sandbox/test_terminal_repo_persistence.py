from __future__ import annotations

from sandbox.terminal import TerminalState, terminal_from_row


class _Repo:
    def __init__(self) -> None:
        self.persisted: list[dict] = []

    def persist_state(self, **payload) -> None:
        self.persisted.append(payload)


def test_terminal_from_row_can_persist_through_injected_repo() -> None:
    repo = _Repo()

    terminal = terminal_from_row(
        {
            "terminal_id": "term-1",
            "thread_id": "thread-1",
            "sandbox_runtime_id": "runtime-1",
            "cwd": "/workspace",
            "env_delta_json": "{}",
            "state_version": 0,
        },
        terminal_repo=repo,
    )

    terminal.update_state(TerminalState(cwd="/workspace/app", env_delta={"A": "1"}))

    assert repo.persisted == [
        {
            "terminal_id": "term-1",
            "cwd": "/workspace/app",
            "env_delta_json": '{"A": "1"}',
            "state_version": 1,
        }
    ]
