from __future__ import annotations

from pathlib import Path


TARGETS = (
    "backend/sandboxes/__init__.py",
    "backend/threads/__init__.py",
    "sandbox/runtime.py",
    "sandbox/resource_snapshot.py",
    "core/runtime/agent.py",
)

FORBIDDEN = (
    "sandbox_lease",
    "which lease binds",
    "managed by lease",
    "lease/session creation",
    "shared lease",
)


def test_runtime_comment_tail_avoids_lease_phrasing() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found runtime comment tail lease residue:\n" + "\n".join(offenders)
