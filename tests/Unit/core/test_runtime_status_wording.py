from __future__ import annotations

from pathlib import Path

TARGETS = (
    "storage/providers/supabase/sandbox_runtime_repo.py",
    "backend/threads/run/lifecycle.py",
)


def test_runtime_status_wording_avoids_lease_status_name() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        if "lease_status" in source:
            offenders.append(rel_path)

    assert offenders == [], "Found lease_status residue:\n" + "\n".join(offenders)
