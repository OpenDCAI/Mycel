from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "_sandbox_id_for_lease(",
    "_lease_id(",
    "_sandbox_by_lease_id(",
    "_require_lease(",
    "lease_id is required",
)


def test_supabase_sandbox_runtime_repo_avoids_lease_helper_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "storage/providers/supabase/sandbox_runtime_repo.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found Supabase sandbox runtime repo lease helper residue:\n" + "\n".join(offenders)
