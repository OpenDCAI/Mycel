from __future__ import annotations

from pathlib import Path

import pytest

from backend.sandboxes.resources.common import resolve_console_url, resolve_provider_name


def test_local_provider_display_contract_does_not_require_config_dir() -> None:
    assert resolve_provider_name("local", sandboxes_dir=None) == "local"
    assert resolve_console_url("local", "local", sandboxes_dir=None) is None


def test_non_local_provider_display_contract_requires_config_dir() -> None:
    with pytest.raises(RuntimeError, match="LEON_SANDBOXES_DIR"):
        resolve_provider_name("daytona", sandboxes_dir=None)


def test_provider_display_contract_reads_explicit_config_dir(tmp_path: Path) -> None:
    (tmp_path / "daytona.json").write_text('{"provider": "daytona", "daytona": {"target": "cloud", "api_url": "https://example.test/api"}}')

    assert resolve_provider_name("daytona", sandboxes_dir=tmp_path) == "daytona"
    assert resolve_console_url("daytona", "daytona", sandboxes_dir=tmp_path) == "https://app.daytona.io"
