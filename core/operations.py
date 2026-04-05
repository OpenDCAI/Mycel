"""File operation recorder for time travel functionality"""

from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from storage.models import FileOperationRow
from storage.providers.sqlite.file_operation_repo import SQLiteFileOperationRepo

# Context variable for tracking current thread (TUI only; web uses sandbox.thread_context)
current_thread_id: ContextVar[str] = ContextVar("current_thread_id", default="")
# current_checkpoint_id removed — now lives in sandbox.thread_context as current_run_id


@dataclass
class FileOperation:
    """Represents a single file operation"""

    id: str
    thread_id: str
    checkpoint_id: str
    timestamp: float
    operation_type: str  # 'write', 'edit', 'multi_edit'
    file_path: str
    before_content: str | None
    after_content: str
    changes: list[dict] | None  # For edit operations: [{old_string, new_string}]
    status: str = "applied"  # 'applied', 'reverted'


class FileOperationRecorder:
    """Records file operations for time travel rollback"""

    def __init__(self, db_path: Path | str | None = None, repo=None):
        # @@@repo-injection - web path injects Supabase repo; TUI falls back to SQLite via db_path.
        if repo is not None:
            self._repo = repo
            return
        if db_path is None:
            db_path = Path.home() / ".leon" / "leon.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._repo = SQLiteFileOperationRepo(self.db_path)

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
        """Record a file operation"""
        return self._repo.record(
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
            operation_type=operation_type,
            file_path=file_path,
            before_content=before_content,
            after_content=after_content,
            changes=changes,
        )

    def get_operations_for_thread(self, thread_id: str, status: str = "applied") -> list[FileOperation]:
        """Get all operations for a thread"""
        rows = self._repo.get_operations_for_thread(thread_id, status=status)
        return [self._to_file_operation(row) for row in rows]

    def get_operations_after_checkpoint(self, thread_id: str, checkpoint_id: str) -> list[FileOperation]:
        """Get operations after a specific checkpoint (for rollback)"""
        rows = self._repo.get_operations_after_checkpoint(thread_id, checkpoint_id)
        return [self._to_file_operation(row) for row in rows]

    def get_operations_between_checkpoints(
        self, thread_id: str, from_checkpoint_id: str, to_checkpoint_id: str
    ) -> list[FileOperation]:
        """Get operations between two checkpoints (exclusive of from, inclusive of to)"""
        rows = self._repo.get_operations_between_checkpoints(thread_id, from_checkpoint_id, to_checkpoint_id)
        return [self._to_file_operation(row) for row in rows]

    def get_operations_for_checkpoint(self, thread_id: str, checkpoint_id: str) -> list[FileOperation]:
        """Get all operations for a specific checkpoint"""
        rows = self._repo.get_operations_for_checkpoint(thread_id, checkpoint_id)
        return [self._to_file_operation(row) for row in rows]

    def count_operations_for_checkpoint(self, thread_id: str, checkpoint_id: str) -> int:
        """Count operations for a specific checkpoint"""
        return self._repo.count_operations_for_checkpoint(thread_id, checkpoint_id)

    def mark_reverted(self, operation_ids: list[str]) -> None:
        """Mark operations as reverted"""
        self._repo.mark_reverted(operation_ids)

    def delete_thread_operations(self, thread_id: str) -> int:
        """Delete all operations for a thread"""
        return self._repo.delete_thread_operations(thread_id)

    def _to_file_operation(self, row: FileOperationRow) -> FileOperation:
        return FileOperation(
            id=row.id,
            thread_id=row.thread_id,
            checkpoint_id=row.checkpoint_id,
            timestamp=row.timestamp,
            operation_type=row.operation_type,
            file_path=row.file_path,
            before_content=row.before_content,
            after_content=row.after_content,
            changes=row.changes,
            status=row.status,
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
