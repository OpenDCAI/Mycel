from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "_assert_lease_provider",
    "def _ensure_bound_instance(self, lease)",
    "Thread {thread_id} is bound to provider {lease.provider_name}",
)


def test_sandbox_manager_tail_avoids_remaining_lease_helper_names() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found remaining sandbox.manager lease tail residue:\n" + "\n".join(offenders)
