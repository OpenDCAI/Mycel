from __future__ import annotations

from pathlib import Path


TARGETS = (
    "sandbox/manager.py",
    "sandbox/provider.py",
    "sandbox/runtime.py",
    "sandbox/chat_session.py",
    "sandbox/providers/agentbay.py",
    "sandbox/providers/daytona.py",
    "sandbox/providers/docker.py",
    "sandbox/providers/e2b.py",
    "sandbox/providers/local.py",
    "storage/providers/sqlite/sandbox_runtime_repo.py",
    "backend/web/routers/webhooks.py",
)


def test_runtime_production_imports_do_not_reference_sandbox_lease_module() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        if "sandbox.lea" "se" in source:
            offenders.append(rel_path)

    assert offenders == [], "Found production imports still referencing sandbox.lea" "se:\n" + "\n".join(offenders)
