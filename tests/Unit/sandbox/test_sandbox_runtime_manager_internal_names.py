from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "def _get_thread_lease(",
    "def _lease_is_busy(",
    "def _skip_volume_sync_for_local_lease(",
)


def test_sandbox_manager_internal_helpers_use_sandbox_runtime_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager internal lease helper names:\n" + "\n".join(offenders)
