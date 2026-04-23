from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "_lease_row_from_sandbox(",
    " lease = self._",
)


def test_supabase_monitor_repo_avoids_runtime_helper_drift() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "storage/providers/supabase/sandbox_monitor_repo.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found Supabase monitor repo lease helper residue:\n" + "\n".join(offenders)
