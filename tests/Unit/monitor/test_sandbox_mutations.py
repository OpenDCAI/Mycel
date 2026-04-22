from __future__ import annotations

from backend.monitor.mutations import sandbox_mutations
from backend.monitor.mutations.contracts import SandboxCleanupRequest


def test_cleanup_sandbox_prunes_workspace_rows_after_runtime_destroy(monkeypatch) -> None:
    destroyed: list[tuple[str, str, bool]] = []
    deleted_sandbox_ids: list[str] = []

    class _FakeWorkspaceRepo:
        def delete_by_sandbox_id(self, sandbox_id: str) -> None:
            deleted_sandbox_ids.append(sandbox_id)

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        sandbox_mutations,
        "destroy_sandbox_runtime",
        lambda *, lower_runtime_handle, provider_name, detach_thread_bindings: (
            destroyed.append((lower_runtime_handle, provider_name, detach_thread_bindings))
            or {"ok": True, "action": "destroy", "provider": provider_name, "sandbox_runtime_handle": lower_runtime_handle}
        ),
    )
    monkeypatch.setattr(sandbox_mutations, "build_workspace_repo", lambda: _FakeWorkspaceRepo())

    payload = sandbox_mutations.cleanup_sandbox(
        SandboxCleanupRequest(
            sandbox_id="sandbox-1",
            sandbox_runtime_handle="lease-1",
            provider_name="local",
            detach_thread_bindings=False,
        )
    )

    assert payload.destroy_result == {"ok": True, "action": "destroy", "provider": "local"}
    assert destroyed == [("lease-1", "local", False)]
    assert deleted_sandbox_ids == ["sandbox-1"]
