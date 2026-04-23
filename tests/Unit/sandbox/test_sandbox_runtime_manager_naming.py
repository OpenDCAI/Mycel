from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "def resolve_existing_lea" "se_cwd(",
    "def bind_thread_to_existing_lea" "se(",
    "def resolve_existing_sandbox_lea" "se(",
    "def bind_thread_to_existing_thread_lea" "se(",
    "No lea" "se for thread",
    "Missing lea" "se ",
    "Lea" "se disappeared after resume",
    "Lea" "se ",
)


def test_sandbox_manager_runtime_surface_avoids_lease_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager lea" "se wording residue:\n" + "\n".join(offenders)
