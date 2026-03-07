"""Command logger hook - logs all executed bash commands."""

from datetime import datetime
from pathlib import Path
from typing import Any

from .base import BashHook, HookResult


class CommandLoggerHook(BashHook):
    """Command logger hook - logs all commands with timestamps and results."""

    priority = 50
    name = "CommandLogger"
    description = "Log all bash commands to file"
    enabled = True

    def __init__(self, workspace_root: Path | str | None = None, log_file: str = "bash_commands.log", **kwargs):
        super().__init__(workspace_root, **kwargs)

        # 日志文件路径
        if workspace_root:
            self.log_path = Path(workspace_root) / log_file
        else:
            self.log_path = Path(log_file)

        # 确保日志文件存在
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def check_command(self, command: str, context: dict[str, Any]) -> HookResult:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] COMMAND: {command}\n")
        return HookResult.allow_command(metadata={"logged_at": timestamp})

    def on_command_success(self, command: str, output: str, context: dict[str, Any]) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] SUCCESS: {command}\n")
            if output:
                f.write(f"[{timestamp}] OUTPUT: {output[:200].replace('\n', ' ')}\n")

    def on_command_error(self, command: str, error: str, context: dict[str, Any]) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] ERROR: {command}\n")
            if error:
                f.write(f"[{timestamp}] ERROR_MSG: {error[:200].replace('\n', ' ')}\n")
