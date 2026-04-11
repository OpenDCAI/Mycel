"""File operation recorder."""


class FileOperationRecorder:
    """Records file operations."""

    def __init__(self, repo=None):
        self._repo = repo

    def record(
        self,
        thread_id: str,
        checkpoint_id: str,
        operation_type: str,
        file_path: str,
        before_content: str | None,
        after_content: str,
        changes: list[dict] | None = None,
    ) -> str:
        """Record a file operation. Noop if no repo configured."""
        if self._repo is None:
            return ""
        return self._repo.record(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            operation_type=operation_type,
            file_path=file_path,
            before_content=before_content,
            after_content=after_content,
            changes=changes,
        )


# Global recorder instance (initialized lazily)
_recorder: FileOperationRecorder | None = None


def get_recorder() -> FileOperationRecorder:
    """Get or create the global recorder instance"""
    global _recorder
    if _recorder is None:
        _recorder = FileOperationRecorder()
    return _recorder


def set_recorder(recorder: FileOperationRecorder) -> None:
    """Set the global recorder instance"""
    global _recorder
    _recorder = recorder
