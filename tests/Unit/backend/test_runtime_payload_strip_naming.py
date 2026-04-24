from __future__ import annotations

from pathlib import Path

TARGETS = (
    "backend/sandboxes/user_reads.py",
    "backend/web/routers/sandbox.py",
    "backend/monitor/mutations/sandbox_mutations.py",
)


def test_runtime_payload_strippers_do_not_carry_runtime_id_filters() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        assert '"lease_id"' not in source, rel_path
