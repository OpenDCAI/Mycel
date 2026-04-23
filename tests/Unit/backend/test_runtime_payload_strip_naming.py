from __future__ import annotations

from pathlib import Path

TARGETS = (
    "backend/sandboxes/user_reads.py",
    "backend/web/routers/sandbox.py",
    "backend/monitor/mutations/sandbox_mutations.py",
)


def test_runtime_payload_strippers_do_not_carry_legacy_runtime_id_filters() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        if '"lea' 'se_id"' in source:
            offenders.append(rel_path)

    assert offenders == [], "Found legacy runtime-id strip residue:\n" + "\n".join(offenders)
