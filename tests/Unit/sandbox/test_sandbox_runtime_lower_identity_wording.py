from __future__ import annotations

from pathlib import Path

TARGETS = (
    "sandbox/capability.py",
    "backend/web/routers/threads.py",
    "backend/sandboxes/runtime/reads.py",
)

FORBIDDEN = (
    "lower runtime",
    "lower-runtime",
)


def test_runtime_surfaces_avoid_runtime_transition_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found old runtime-transition wording residue:\n" + "\n".join(offenders)
