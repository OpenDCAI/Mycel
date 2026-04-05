"""File permission control hook - supports file type restrictions and path blacklists."""

from pathlib import Path

from .base import HookResult


class FilePermissionHook:
    """File permission control hook with extension whitelist and path blacklist."""

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        allowed_extensions: list[str] | None = None,
        blocked_paths: list[str] | None = None,
        **kwargs,
    ):
        self.workspace_root = Path(workspace_root) if workspace_root else None
        self.allowed_extensions = allowed_extensions
        self.blocked_paths = [Path(p) for p in (blocked_paths or [])]
        self.config = kwargs

    def check_file_operation(self, file_path: str, operation: str) -> HookResult:
        path = Path(file_path)

        if self.allowed_extensions and path.suffix:
            ext = path.suffix.lstrip(".")
            if ext not in self.allowed_extensions:
                return HookResult.block_command(
                    error_message=(
                        f"❌ PERMISSION DENIED: File type not allowed\n"
                        f"   File: {file_path}\n"
                        f"   Extension: {path.suffix}\n"
                        f"   Allowed: {', '.join(self.allowed_extensions)}"
                    )
                )

        for blocked in self.blocked_paths:
            try:
                path.resolve().relative_to(blocked.resolve())
                return HookResult.block_command(
                    error_message=(
                        f"❌ PERMISSION DENIED: Access to this path is blocked\n"
                        f"   File: {file_path}\n"
                        f"   Blocked path: {blocked}"
                    )
                )
            except ValueError:
                continue

        return HookResult.allow_command()


__all__ = ["FilePermissionHook"]
