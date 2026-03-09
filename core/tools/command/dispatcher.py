"""Dispatcher to select appropriate executor based on OS."""

from __future__ import annotations

import os
import platform

from .base import BaseExecutor
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


def get_shell_info() -> dict[str, str]:
    """Get information about the current shell environment."""
    system = platform.system()
    shell_env = os.environ.get("SHELL", "")

    if system == "Darwin":
        shell_name = "zsh"
        shell_path = "/bin/zsh"
    elif system == "Windows":
        shell_name = "powershell"
        shell_path = "powershell.exe"
    else:
        shell_name = "bash"
        shell_path = "/bin/bash"

    return {
        "os": system,
        "shell_name": shell_name,
        "shell_path": shell_path,
        "shell_env": shell_env,
    }
