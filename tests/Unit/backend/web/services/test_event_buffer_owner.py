from __future__ import annotations

import importlib

import pytest


def test_thread_history_shell_is_deleted() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.thread_history")


def test_thread_projection_shell_is_deleted() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("backend.thread_projection")
