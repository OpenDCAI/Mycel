"""Dangerous commands hook - blocks commands that may harm the system."""

import re
from pathlib import Path
from typing import Any

from .base import BashHook, HookResult


class DangerousCommandsHook(BashHook):
    """Dangerous commands hook - blocks destructive system commands."""

    priority = 5
    name = "DangerousCommands"
    description = "Block dangerous commands that may harm the system"
    enabled = True

    DEFAULT_BLOCKED_COMMANDS = [
        r"\brm\s+-rf",
        r"\brm\s+.*-.*r.*f",
        r"\brmdir\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bsudo\b",
        r"\bsu\b",
        r"\bkill\b",
        r"\bpkill\b",
        r"\breboot\b",
        r"\bshutdown\b",
        r"\bmkfs\b",
        r"\bdd\b",
    ]

    NETWORK_COMMANDS = [
        r"\bcurl\b",
        r"\bwget\b",
        r"\bscp\b",
        r"\bsftp\b",
        r"\brsync\b",
        r"\bssh\b",
    ]

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        block_network: bool = False,
        custom_blocked: list[str] | None = None,
        verbose: bool = True,
        **kwargs,
    ):
        super().__init__(workspace_root, **kwargs)
        self.verbose = verbose

        patterns = self.DEFAULT_BLOCKED_COMMANDS.copy()
        if block_network:
            patterns.extend(self.NETWORK_COMMANDS)
        if custom_blocked:
            patterns.extend(custom_blocked)

        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

        if verbose:
            print(f"[DangerousCommands] Loaded {len(self.compiled_patterns)} blocked command patterns")

    def check_command(self, command: str, context: dict[str, Any]) -> HookResult:
        for pattern in self.compiled_patterns:
            if pattern.search(command.strip()):
                return HookResult.block_command(
                    error_message=(
                        f"❌ SECURITY ERROR: Dangerous command detected\n"
                        f"   Command: {command[:100]}\n"
                        f"   Reason: This command is blocked for security reasons\n"
                        f"   Pattern: {pattern.pattern}\n"
                        f"   💡 If you need to perform this operation, ask the user for permission."
                    )
                )
        return HookResult.allow_command()


__all__ = ["DangerousCommandsHook"]
