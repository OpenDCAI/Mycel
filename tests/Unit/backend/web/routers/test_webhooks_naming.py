from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "make_" "lower_" "runtime_repo",
    "lower_" "runtime_from_row",
    "lower_" "runtime = ",
    "matched lower" "-runtime state",
    "lower" "-runtime state",
)


def test_webhooks_router_avoids_runtime_transition_wording() -> None:
    repo_root = Path(__file__).resolve().parents[5]
    source = (repo_root / "backend/web/routers/webhooks.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found webhook runtime-transition residue:\n" + "\n".join(offenders)
