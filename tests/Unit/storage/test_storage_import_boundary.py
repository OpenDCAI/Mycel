from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "from core.runtime.middleware.memory.checkpoint_repo import",
    "from core.runtime.middleware.memory.run_event_repo import",
    "from core.runtime.middleware.memory.file_operation_repo import",
    "from core.runtime.middleware.memory.summary_repo import",
)


def test_runtime_layers_do_not_import_memory_repo_modules_directly() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    scan_dirs = ("core", "backend", "eval")
    offenders: list[str] = []

    for scan_dir in scan_dirs:
        for path in (repo_root / scan_dir).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN:
                if pattern in text:
                    offenders.append(f"{path.relative_to(repo_root)} -> {pattern}")

    assert not offenders, "Found forbidden memory repo imports:\n" + "\n".join(offenders)
