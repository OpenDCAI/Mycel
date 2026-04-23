from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "def _get_thread_lease(",
    "def _lease_is_busy(",
    "def _skip_volume_sync_for_local_lease(",
    "def resolve_existing_sandbox_runtime_cwd(\n    lease_id: str,",
    "def bind_thread_to_existing_sandbox_runtime(\n    thread_id: str,\n    lease_id: str,",
    "def _get_sandbox_runtime(self, lease_id: str):",
    "def _create_sandbox_runtime(self, lease_id: str, provider_name: str):",
    "def get_sandbox_runtime(self, lease_id: str):",
    "def _destroy_daytona_managed_volume(self, lease_id: str) -> None:",
    "def _upgrade_to_daytona_volume(self, thread_id: str, lease_id: str, remote_path: str):",
    "def _sandbox_runtime_is_busy(self, lease_id: str) -> bool:",
    "lease = _sandbox_runtime_repo.find_by_instance(",
    "lease = resolve_existing_sandbox_runtime(",
    'lease_id = str(lease.get("sandbox_runtime_id") or "").strip()',
    "lease_ids = {terminal.sandbox_runtime_id for terminal in terminals}",
    "threads_by_lease",
    'lease_id = f"runtime-',
    "lease = self._create_sandbox_runtime(",
    "lease = self._get_sandbox_runtime(",
    "return lease",
    "lease = self._get_thread_sandbox_runtime(thread_id)",
    "if not lease:",
    'if lease and lease.observed_state == "running":',
    "def destroy_sandbox_runtime_resources(self, lease_id: str) -> bool:",
    'lease_id = lease_row["sandbox_runtime_id"]',
    "self.lease_store.delete(",
)


def test_sandbox_manager_internal_helpers_use_sandbox_runtime_wording() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    source = (repo_root / "sandbox/manager.py").read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN if pattern in source]
    assert offenders == [], "Found sandbox.manager internal lease helper names:\n" + "\n".join(offenders)
