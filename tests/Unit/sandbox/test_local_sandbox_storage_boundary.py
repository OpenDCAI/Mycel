from __future__ import annotations

from sandbox.base import LocalSandbox


def test_local_sandbox_keeps_missing_db_path_unset(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class _SandboxManagerProbe:
        def __init__(self, *, provider, db_path=None):
            captured["provider"] = provider
            captured["db_path"] = db_path

    monkeypatch.setattr("sandbox.manager.SandboxManager", _SandboxManagerProbe)

    LocalSandbox(str(tmp_path))

    assert captured["db_path"] is None
