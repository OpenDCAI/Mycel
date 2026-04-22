from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "def resolve_existing_lease_cwd(",
    "def bind_thread_to_existing_lease(",
    "def resolve_existing_sandbox_lease(",
    "def bind_thread_to_existing_thread_lease(",
    "No lease for thread",
    "Missing lease ",
    "Lease disappeared after resume",
    "Lease ",
)


def test_sandbox_manager_runtime_surface_avoids_lease_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager lease wording residue:\n" + "\n".join(offenders)
