"""Tests for PathSecurityHook extra_allowed_paths support."""

from pathlib import Path

import pytest

from core.command.hooks.path_security import PathSecurityHook


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def extra_dir(tmp_path: Path) -> Path:
    d = tmp_path / "extra_storage"
    d.mkdir()
    return d


def test_extra_allowed_path_permits_access(workspace: Path, extra_dir: Path):
    hook = PathSecurityHook(workspace_root=workspace, extra_allowed_paths=[extra_dir])
    target = extra_dir / "somefile.txt"
    assert hook._is_within_workspace(target) is True


def test_extra_allowed_path_blocks_unrelated(workspace: Path, extra_dir: Path, tmp_path: Path):
    hook = PathSecurityHook(workspace_root=workspace, extra_allowed_paths=[extra_dir])
    unrelated = tmp_path / "elsewhere" / "secret.txt"
    assert hook._is_within_workspace(unrelated) is False


def test_no_extra_paths_preserves_existing_behavior(workspace: Path, tmp_path: Path):
    hook = PathSecurityHook(workspace_root=workspace)
    inside = workspace / "file.py"
    outside = tmp_path / "other" / "file.py"
    assert hook._is_within_workspace(inside) is True
    assert hook._is_within_workspace(outside) is False
