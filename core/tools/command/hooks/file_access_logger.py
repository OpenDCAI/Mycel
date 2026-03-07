"""File access logger hook - logs all file operations for audit purposes."""

from datetime import datetime
from pathlib import Path

from .base import HookResult


class FileAccessLoggerHook:
    """File access logger hook - logs all file operations with timestamps."""

    def __init__(self, workspace_root: Path | str | None = None, log_file: str = "file_access.log", **kwargs):
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.config = kwargs
        self.log_path = (Path(workspace_root) / log_file) if workspace_root else Path(log_file)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def check_file_operation(self, file_path: str, operation: str) -> HookResult:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {operation.upper()}: {file_path}\n")
        return HookResult.allow_command(metadata={"logged_at": timestamp})

    def log_operation_result(self, file_path: str, operation: str, success: bool, message: str = ""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if success else "FAILED"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {status}: {operation.upper()} {file_path}\n")
            if message:
                f.write(f"[{timestamp}] MESSAGE: {message[:200]}\n")


__all__ = ["FileAccessLoggerHook"]
