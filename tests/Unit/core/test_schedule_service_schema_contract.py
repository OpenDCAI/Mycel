from __future__ import annotations

import importlib

import pytest


def test_schedule_service_shell_is_deleted() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.web.services.schedule_service")
