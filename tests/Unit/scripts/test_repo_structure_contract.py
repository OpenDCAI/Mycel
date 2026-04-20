from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_repo_has_no_shadow_database_or_dev_replay_residue() -> None:
    forbidden_paths = [
        REPO_ROOT / "database",
        REPO_ROOT / "docs" / "database-refactor",
    ]

    offenders = [str(path.relative_to(REPO_ROOT)) for path in forbidden_paths if path.exists()]

    # @@@repo-structure-taste - shipping repo should not carry shadow schema trees or replay residue.
    assert offenders == [], f"forbidden repo structure residue present: {offenders}"
