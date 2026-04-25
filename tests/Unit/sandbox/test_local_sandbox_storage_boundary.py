from __future__ import annotations

from sandbox.base import LocalSandbox


def test_local_sandbox_defers_manager_creation_until_control_plane_use(monkeypatch, tmp_path):
    captured: list[dict[str, object]] = []

    class _SandboxManagerProbe:
        def __init__(self, *, provider, db_path=None):
            captured.append({"provider": provider, "db_path": db_path})

    monkeypatch.setattr("sandbox.manager.SandboxManager", _SandboxManagerProbe)

    sandbox = LocalSandbox(str(tmp_path))

    assert captured == []
    assert sandbox.manager is sandbox.manager
    assert captured[0]["db_path"] is None
    assert len(captured) == 1
