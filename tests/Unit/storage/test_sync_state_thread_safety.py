from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sandbox.sync.state import SyncState


def test_sync_state_shared_instance_survives_cross_thread_access(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("hello")

    state = SyncState()
    try:

        def _detect() -> list[str]:
            return state.detect_changes("thread-a", workspace)

        with ThreadPoolExecutor(max_workers=1) as pool:
            changed = pool.submit(_detect).result(timeout=10)
    finally:
        state.clear_thread("thread-a")
        state.close()

    assert changed == ["hello.txt"]
