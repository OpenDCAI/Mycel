from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_windows_main_sets_db_path_defaults(monkeypatch, tmp_path: Path):
    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    for key in (
        "LEON_DB_PATH",
        "LEON_RUN_EVENT_DB_PATH",
        "LEON_QUEUE_DB_PATH",
        "LEON_CHAT_DB_PATH",
        "LEON_SANDBOX_DB_PATH",
        "LEON_SUBAGENT_DB_PATH",
        "LEON_EVAL_DB_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    import backend.web.main as main_module

    main_module = importlib.reload(main_module)
    leon_root = local_appdata / "Leon"
    assert os.environ["LEON_DB_PATH"] == str(leon_root / "leon.db")
    assert os.environ["LEON_RUN_EVENT_DB_PATH"] == str(leon_root / "events.db")


def test_windows_web_modules_read_db_path_defaults(monkeypatch, tmp_path: Path):
    override = tmp_path / "LocalAppData" / "Leon" / "leon.db"
    monkeypatch.setenv("LEON_DB_PATH", str(override))

    import backend.web.core.config as config_module
    import backend.web.services.event_store as event_store_module

    config_module = importlib.reload(config_module)
    event_store_module = importlib.reload(event_store_module)
    assert config_module.DB_PATH == override
    assert event_store_module._DB_PATH == override


def test_windows_member_service_uses_runtime_db_root(monkeypatch, tmp_path: Path):
    runtime_root = tmp_path / "runtime-root"
    db_path = runtime_root / "leon.db"
    monkeypatch.setenv("LEON_DB_PATH", str(db_path))

    import backend.web.services.member_service as member_service_module
    member_service_module = importlib.reload(member_service_module)

    created = member_service_module.create_member("Windows Scoped Member", "desc", owner_user_id="owner-1")
    member_dir = runtime_root / "members" / created["id"]

    assert member_dir.is_dir()
