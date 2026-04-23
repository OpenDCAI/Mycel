from __future__ import annotations

from pathlib import Path

TARGETS = (
    "tests/Integration/test_thread_launch_config_contract.py",
    "tests/Integration/test_threads_router.py",
    "tests/Unit/backend/web/routers/test_thread_resource_creation.py",
    "tests/Unit/backend/web/services/test_thread_state_service.py",
    "tests/Unit/sandbox/test_sandbox_runtime_provider_env_sync.py",
    "tests/Unit/sandbox/test_sandbox_manager_volume_repo.py",
)

FORBIDDEN = (
    "_FakeLea" "seRepo",
    "_Lea" "seRepo",
    "_FakeLea" "seStore",
    "class _FakeLea" "se:",
    '"lea' 'se-1"',
    '"lea' 'se-live"',
)

FORBIDDEN_FILENAMES = (
    "tests/Unit/storage/test_sqlite_lea" "se_repo.py",
    "tests/Unit/storage/test_supabase_lea" "se_repo.py",
)


def test_target_runtime_tests_do_not_use_legacy_runtime_repo_helper_names() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []

    for rel_path in TARGETS:
        source = (repo_root / rel_path).read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            if pattern in source:
                offenders.append(f"{rel_path} -> {pattern}")

    for rel_path in FORBIDDEN_FILENAMES:
        if (repo_root / rel_path).exists():
            offenders.append(f"{rel_path} -> filename")

    assert offenders == [], "Found legacy lea" "se repo test residue:\n" + "\n".join(offenders)
