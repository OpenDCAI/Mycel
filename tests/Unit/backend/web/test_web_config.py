import importlib

import pytest

from backend.sandboxes.local_workspace import local_workspace_root


def test_local_workspace_root_requires_explicit_env(monkeypatch) -> None:
    monkeypatch.delenv("LEON_LOCAL_WORKSPACE_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="LEON_LOCAL_WORKSPACE_ROOT is required"):
        local_workspace_root()


def test_local_workspace_root_uses_explicit_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_LOCAL_WORKSPACE_ROOT", str(tmp_path))

    assert local_workspace_root() == tmp_path.resolve()


def test_sandbox_modules_do_not_resolve_workspace_root_at_import(monkeypatch) -> None:
    monkeypatch.delenv("LEON_LOCAL_WORKSPACE_ROOT", raising=False)

    import backend.sandboxes.inventory as inventory
    import backend.sandboxes.service as service

    importlib.reload(inventory)
    importlib.reload(service)


def test_web_config_requires_explicit_local_workspace_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEON_LOCAL_WORKSPACE_ROOT", str(tmp_path))
    from backend.web.core import config

    importlib.reload(config)
    monkeypatch.delenv("LEON_LOCAL_WORKSPACE_ROOT", raising=False)
    try:
        with pytest.raises(RuntimeError, match="LEON_LOCAL_WORKSPACE_ROOT is required"):
            importlib.reload(config)
    finally:
        monkeypatch.setenv("LEON_LOCAL_WORKSPACE_ROOT", str(tmp_path))
        importlib.reload(config)
