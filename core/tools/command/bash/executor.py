"""Bash executor for Linux systems."""

from __future__ import annotations

from typing import ClassVar

from core.tools.command.posix_executor import PosixShellExecutor
from sandbox.interfaces.executor import AsyncCommand


class BashExecutor(PosixShellExecutor):
    shell_name = "bash"
    shell_command = ("/bin/bash",)
    _running_commands: ClassVar[dict[str, AsyncCommand]] = {}
