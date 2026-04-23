from __future__ import annotations

from pathlib import Path

TARGETS = (
    "sandbox/runtime_handle.py",
    "sandbox/chat_session.py",
    "sandbox/manager.py",
)

FORBIDDEN = (
    "_persist_lease_metadata",
    "_lease_row",
    "for lease_row in ",
)


def test_runtime_tail_surfaces_do_not_keep_lease_local_residue() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found runtime tail lease residue:\n" + "\n".join(offenders)
