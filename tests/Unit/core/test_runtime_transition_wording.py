from __future__ import annotations

from pathlib import Path


TARGETS = (
    "sandbox/__init__.py",
    "sandbox/sync/strategy.py",
    "core/runtime/agent.py",
    "core/runtime/middleware/memory/middleware.py",
    "backend/threads/launch_config.py",
    "backend/monitor/application/use_cases/thread_workbench.py",
)

FORBIDDEN = (
    "Fallback working dir",
    "Fallback: upload via tar+base64+execute",
    "Fallback: download via tar+base64+execute",
    "Fallback for edge cases where __init__ did not complete fully",
    "Fallback to asyncio.run() if no loop exists",
    "Fallback: try request.config",
    "@@@stale-existing-default-fallback",
    "@@@owner-thread-candidate-fallback",
)


def test_runtime_transition_comments_avoid_fallback_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found transition/fallback wording residue:\n" + "\n".join(offenders)
