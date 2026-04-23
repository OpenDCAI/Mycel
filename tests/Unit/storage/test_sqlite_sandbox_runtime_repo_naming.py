from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "_require_lea" "se(",
    "lea" "se_cols",
    "missing_lea" "se",
    "per-lea" "se locks",
)


def test_sqlite_sandbox_runtime_repo_avoids_lease_helper_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "storage/providers/sqlite/sandbox_runtime_repo.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sqlite sandbox runtime repo lea" "se helper residue:\n" + "\n".join(offenders)
