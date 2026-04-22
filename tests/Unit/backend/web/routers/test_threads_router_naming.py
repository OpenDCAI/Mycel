from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "_resolve_owned_existing_sandbox_request_lease",
    "resolved_lease",
    "bound_lease",
    "Create lease and terminal resources",
    "lower lease identity",
)


def test_threads_router_avoids_lease_wording_in_existing_sandbox_helpers() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    source = (repo_root / "backend/web/routers/threads.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found threads router lease wording residue:\n" + "\n".join(offenders)
