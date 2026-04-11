"""Zsh executor for macOS systems."""

from __future__ import annotations

from typing import ClassVar

from core.tools.command.posix_executor import PosixShellExecutor
from sandbox.interfaces.executor import AsyncCommand


class ZshExecutor(PosixShellExecutor):
    shell_name = "zsh"
    shell_command = ("/bin/zsh",)
    _running_commands: ClassVar[dict[str, AsyncCommand]] = {}
