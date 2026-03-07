"""Path security hook - restricts bash commands to workspace directory only."""

import re
from pathlib import Path
from typing import Any

from .base import BashHook, HookResult


class PathSecurityHook(BashHook):
    """Path security hook - prevents directory traversal and access outside workspace."""

    priority = 10
    name = "PathSecurity"
    description = "Restrict bash commands to workspace directory only"

    def __init__(self, workspace_root: Path | str | None = None, strict_mode: bool = True, **kwargs):
        super().__init__(workspace_root, **kwargs)

        if workspace_root is None:
            raise ValueError("PathSecurityHook requires workspace_root")

        self.strict_mode = strict_mode

    def check_command(self, command: str, context: dict[str, Any]) -> HookResult:
        command = command.strip()

        cd_match = re.search(r"\bcd\s+(/[^\s;|&]*)", command)
        if cd_match:
            target = Path(cd_match.group(1)).resolve()
            if not self._is_within_workspace(target):
                return HookResult.block_command(
                    error_message=(
                        f"❌ SECURITY ERROR: Cannot cd to '{cd_match.group(1)}'\n"
                        f"   Reason: Path is outside workspace\n"
                        f"   Workspace: {self.workspace_root}\n"
                        f"   Attempted: {target}\n"
                        f"   💡 You can only execute commands within the workspace directory."
                    )
                )

        if self.strict_mode and ".." in command and re.search(r"\.\./|/\.\.|cd\s+\.\.", command):
            return HookResult.block_command(
                error_message=(
                    f"❌ SECURITY ERROR: Path traversal detected in command\n"
                    f"   Command: {command[:100]}\n"
                    f"   Reason: '../' is not allowed (may escape workspace)\n"
                    f"   Workspace: {self.workspace_root}\n"
                    f"   💡 Use relative paths within workspace or ask user for permission."
                )
            )

        for abs_path in re.findall(r"\s(/[^\s;|&]+)", command):
            if abs_path.startswith(("/bin/", "/usr/", "/etc/bash", "/dev/", "/tmp/")):
                continue

            try:
                resolved = Path(abs_path).resolve()
                if not self._is_within_workspace(resolved):
                    return HookResult.block_command(
                        error_message=(
                            f"❌ SECURITY ERROR: Cannot access '{abs_path}'\n"
                            f"   Reason: Path is outside workspace\n"
                            f"   Workspace: {self.workspace_root}\n"
                            f"   Attempted: {resolved}\n"
                            f"   💡 You can only access files within the workspace directory."
                        )
                    )
            except Exception:
                pass

        return HookResult.allow_command()

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.workspace_root)
            return True
        except ValueError:
            return False
