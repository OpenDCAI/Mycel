"""Dispatcher to select appropriate executor based on OS."""

from __future__ import annotations

import platform

from sandbox.interfaces.executor import BaseExecutor
from .bash import BashExecutor
from .powershell import PowerShellExecutor
from .zsh import ZshExecutor


def get_executor(default_cwd: str | None = None) -> BaseExecutor:
    """
    Get the appropriate executor for the current OS.

    - macOS → ZshExecutor
    - Windows → PowerShellExecutor
    - Linux/other → BashExecutor

    Args:
        default_cwd: Default working directory for commands

    Returns:
        Appropriate executor instance
    """
    system = platform.system()

    if system == "Darwin":
        return ZshExecutor(default_cwd=default_cwd)
    elif system == "Windows":
        return PowerShellExecutor(default_cwd=default_cwd)
    else:
        return BashExecutor(default_cwd=default_cwd)
