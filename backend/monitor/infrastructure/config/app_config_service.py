"""Monitor-local access to app config values."""

from __future__ import annotations

from pathlib import Path

from backend.web.core import config as web_config


def local_workspace_root() -> Path:
    return web_config.LOCAL_WORKSPACE_ROOT
