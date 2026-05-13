from __future__ import annotations

import json
from pathlib import Path

import pytest

from sandbox.config import SANDBOX_CONFIG_DIR_ENV, SandboxConfig, sandbox_config_dir


def test_sandbox_config_dir_is_empty_when_env_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SANDBOX_CONFIG_DIR_ENV, raising=False)

    assert sandbox_config_dir() is None


def test_sandbox_config_dir_uses_explicit_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "sandbox-configs"
    monkeypatch.setenv(SANDBOX_CONFIG_DIR_ENV, str(config_dir))

    assert sandbox_config_dir() == config_dir.resolve()


def test_non_local_sandbox_load_requires_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SANDBOX_CONFIG_DIR_ENV, raising=False)

    with pytest.raises(RuntimeError, match=SANDBOX_CONFIG_DIR_ENV):
        SandboxConfig.load("daytona")


def test_non_local_sandbox_load_reads_explicit_config_dir(tmp_path: Path) -> None:
    (tmp_path / "docker.json").write_text('{"provider": "docker", "allowed_paths": ["/shared"]}')

    config = SandboxConfig.load("docker", sandboxes_dir=tmp_path)

    assert config.name == "docker"
    assert config.provider == "docker"
    assert config.allowed_paths == ["/shared"]


def test_sandbox_config_save_requires_config_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SANDBOX_CONFIG_DIR_ENV, raising=False)

    with pytest.raises(RuntimeError, match=SANDBOX_CONFIG_DIR_ENV):
        SandboxConfig(provider="docker").save("docker")


def test_sandbox_config_save_writes_explicit_config_dir(tmp_path: Path) -> None:
    path = SandboxConfig(provider="docker", allowed_paths=["/shared"]).save("docker", sandboxes_dir=tmp_path)

    assert path == tmp_path / "docker.json"
    assert json.loads(path.read_text()) == {
        "provider": "docker",
        "on_exit": "pause",
        "allowed_paths": ["/shared"],
        "docker": {
            "image": "python:3.12-slim",
            "mount_path": "/workspace",
            "docker_host": None,
            "cwd": "/workspace",
            "bind_mounts": [],
        },
    }
