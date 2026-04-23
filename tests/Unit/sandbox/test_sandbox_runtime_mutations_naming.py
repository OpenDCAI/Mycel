from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    'lea' 'se_id = runtime.get("sandbox_runtime_id")',
    'mode = "lea' 'se_enforced"',
    "lea" "se = manager.get_sandbox_runtime(",
    'row.get("lea' 'se_id")',
)


def test_sandbox_runtime_mutations_avoid_lease_wording_tail() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "backend/sandboxes/runtime/mutations.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found backend sandbox runtime mutation lea" "se wording residue:\n" + "\n".join(offenders)
