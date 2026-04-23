from __future__ import annotations

from pathlib import Path

TARGETS = (
    "storage/providers/sqlite/sandbox_runtime_repo.py",
    "storage/providers/supabase/sandbox_runtime_repo.py",
)


def test_provider_runtime_repo_modules_do_not_use_lease_repo_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        if "lease repo" in source:
            offenders.append(rel_path)

    assert offenders == [], "Found lease repo wording in provider runtime repos:\n" + "\n".join(offenders)
