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
    "SQLiteLease",
    "REQUIRED_LEASE_COLUMNS",
    "LEASE_FRESHNESS_TTL_SEC",
    "_lease_locks",
    "lease-level state machine",
    "Lease snapshot stores",
    "Lease provider mismatch",
    "Unsupported lease event type",
    "Sandbox lease ",
    "Failed to destroy lease ",
    "Failed to pause lease ",
    "Failed to resume lease ",
    "Failed to load adopted lease",
    " delegates to provider via lease",
    "session's lease",
    "Failed to resume paused lease ",
    "Lease ",
    "lease-bound local sessions",
    "via lease_id",
)


def test_runtime_core_surfaces_avoid_lease_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    assert offenders == [], "Found runtime core lease wording residue:\n" + "\n".join(offenders)
