from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "@@@subagent-lease-reuse",
    "@@@thread-single-lease-invariant",
    "@@@paused-lease-rehydrate",
    "@@@idle-reaper-shared-lease",
    "Pause expired leases and close chat sessions.",
    "expired lease ",
    "terminal/lease records",
)


def test_sandbox_manager_comment_wording_avoids_lease_phrasing() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager lease comment/message residue:\n" + "\n".join(offenders)
