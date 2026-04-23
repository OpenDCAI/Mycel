from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "_resolve_owned_existing_sandbox_request_lea" "se",
    "resolved_lea" "se",
    "bound_lea" "se",
    "Create lea" "se and terminal resources",
    "lower lea" "se identity",
    "created_lea" "se",
    "lower lea" "se_id remains terminal/runtime internals",
)


def test_threads_router_avoids_runtime_wording_drift_in_existing_sandbox_helpers() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    source = (repo_root / "backend/web/routers/threads.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found threads router lea" "se wording residue:\n" + "\n".join(offenders)
