from __future__ import annotations

from pathlib import Path

TARGETS = (
    "sandbox/chat_session.py",
    "sandbox/manager.py",
    "backend/threads/state.py",
    "backend/web/routers/threads.py",
)


def test_target_runtime_surfaces_do_not_use_lease_repo_local_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        path = repo_root / rel_path
        source = path.read_text(encoding="utf-8")
        if "lease_repo" in source:
            offenders.append(rel_path)

    assert offenders == [], "Found lease_repo residue in runtime surfaces:\n" + "\n".join(offenders)
