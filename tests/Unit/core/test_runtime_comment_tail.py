from __future__ import annotations

from pathlib import Path

TARGETS = (
    "backend/sandboxes/__init__.py",
    "backend/threads/__init__.py",
    "sandbox/manager.py",
    "sandbox/runtime.py",
    "sandbox/resource_snapshot.py",
    "core/runtime/agent.py",
    "core/agents/service.py",
)

FORBIDDEN = (
    "sandbox_lea" "se",
    "which lea" "se binds",
    "managed by lea" "se",
    "lea" "se/session creation",
    "shared lea" "se",
    "Lea" "se state machine",
    "lea" "se identity directly",
)


def test_runtime_comment_tail_avoids_runtime_drift_phrasing() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found runtime comment tail lea" "se residue:\n" + "\n".join(offenders)
