from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "@@@subagent-lea" "se-reuse",
    "@@@thread-single-lea" "se-invariant",
    "@@@paused-lea" "se-rehydrate",
    "@@@idle-reaper-shared-lea" "se",
    "@@@shared-lea" "se-destroy-boundary",
    "Pause expired lea" "ses and close chat sessions.",
    "pause physical lea" "se instance",
    "expired lea" "se ",
    "terminal/lea" "se records",
    "Re-resolve through lea" "se",
)


def test_sandbox_manager_comment_wording_avoids_lease_phrasing() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager lea" "se comment/message residue:\n" + "\n".join(offenders)
