from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "def _get_thread_lea" "se(",
    "def _lea" "se_is_busy(",
    "def _skip_volume_sync_for_local_lea" "se(",
    "def resolve_existing_sandbox_runtime_cwd(\n    lea" "se_id: str,",
    "def bind_thread_to_existing_sandbox_runtime(\n    thread_id: str,\n    lea" "se_id: str,",
    "def _get_sandbox_runtime(self, lea" "se_id: str):",
    "def _create_sandbox_runtime(self, lea" "se_id: str, provider_name: str):",
    "def get_sandbox_runtime(self, lea" "se_id: str):",
    "def _destroy_daytona_managed_volume(self, lea" "se_id: str) -> None:",
    "def _upgrade_to_daytona_volume(self, thread_id: str, lea" "se_id: str, remote_path: str):",
    "def _sandbox_runtime_is_busy(self, lea" "se_id: str) -> bool:",
    "lea" "se = _sandbox_runtime_repo.find_by_instance(",
    "lea" "se = resolve_existing_sandbox_runtime(",
    'lea' 'se_id = str(lea' 'se.get("sandbox_runtime_id") or "").strip()',
    "lea" "se_ids = {terminal.sandbox_runtime_id for terminal in terminals}",
    "threads_by_lea" "se",
    'lea' 'se_id = f"runtime-',
    "lea" "se = self._create_sandbox_runtime(",
    "lea" "se = self._get_sandbox_runtime(",
    "return lea" "se",
    "lea" "se = self._get_thread_sandbox_runtime(thread_id)",
    "if not lea" "se:",
    'if lea' 'se and lea' 'se.observed_state == "running":',
    "def destroy_sandbox_runtime_resources(self, lea" "se_id: str) -> bool:",
    'lea' 'se_id = lea' 'se_row["sandbox_runtime_id"]',
    "self.lea" "se_store.delete(",
)


def test_sandbox_manager_internal_helpers_use_sandbox_runtime_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager internal lea" "se helper names:\n" + "\n".join(offenders)
