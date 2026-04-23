from __future__ import annotations

from pathlib import Path

TARGETS = (
    "sandbox/runtime_handle.py",
    "sandbox/capability.py",
    "sandbox/providers/local.py",
    "sandbox/runtime.py",
    "storage/providers/sqlite/sandbox_runtime_repo.py",
    "storage/providers/supabase/sandbox_runtime_repo.py",
)

FORBIDDEN = (
    "SQLiteLea" "se",
    "REQUIRED_LEA" "SE_COLUMNS",
    "LEA" "SE_FRESHNESS_TTL_SEC",
    "_lea" "se_locks",
    "lea" "se-level state machine",
    "Lea" "se snapshot stores",
    "Lea" "se provider mismatch",
    "Unsupported lea" "se event type",
    "Sandbox lea" "se ",
    "Failed to destroy lea" "se ",
    "Failed to pause lea" "se ",
    "Failed to resume lea" "se ",
    "Failed to load adopted lea" "se",
    " delegates to provider via lea" "se",
    "session's lea" "se",
    "Failed to resume paused lea" "se ",
    "Lea" "se ",
    "lea" "se-bound local sessions",
    "via lea" "se_id",
)


def test_runtime_core_surfaces_avoid_lease_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found runtime core lea" "se wording residue:\n" + "\n".join(offenders)
