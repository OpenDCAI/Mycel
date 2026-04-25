import pytest

from backend.sandboxes.local_workspace import local_workspace_root


def test_local_workspace_root_requires_explicit_env(monkeypatch) -> None:
    monkeypatch.delenv("LEON_LOCAL_WORKSPACE_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="LEON_LOCAL_WORKSPACE_ROOT is required"):
        local_workspace_root()


def test_local_workspace_root_uses_explicit_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_LOCAL_WORKSPACE_ROOT", str(tmp_path))

    assert local_workspace_root() == tmp_path.resolve()
