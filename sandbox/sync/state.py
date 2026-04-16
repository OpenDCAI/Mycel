import hashlib
from pathlib import Path


def _calculate_checksum(file_path: Path) -> str:
    """Calculate SHA256 checksum of file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class SyncState:
    def __init__(self, repo=None):
        self._repo = repo or ProcessLocalSyncFileBacking()

    def close(self) -> None:
        self._repo.close()

    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]):
        """Batch insert/update multiple files in a single transaction.
        file_records: list of (relative_path, checksum, timestamp)
        """
        self._repo.track_files_batch(thread_id, file_records)

    def get_all_files(self, thread_id: str) -> dict[str, str]:
        """Batch fetch all tracked files for a thread. Returns {relative_path: checksum}."""
        return self._repo.get_all_files(thread_id)

    def clear_thread(self, thread_id: str) -> int:
        """Delete all sync records for a thread."""
        return self._repo.clear_thread(thread_id)

    def detect_changes(self, thread_id: str, workspace_path: Path) -> list[str]:
        """Detect files that changed since last sync. Uses batch DB query + mtime heuristic."""
        known = self.get_all_files(thread_id)
        changed = []
        for file_path in workspace_path.rglob("*"):
            if not file_path.is_file():
                continue
            relative = str(file_path.relative_to(workspace_path))
            if relative not in known:
                # New file — must upload
                changed.append(relative)
                continue
            # @@@checksum-change-detection - compare SHA256 against tracked checksum
            current_checksum = _calculate_checksum(file_path)
            if current_checksum != known[relative]:
                changed.append(relative)
        return changed


class ProcessLocalSyncFileBacking:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, tuple[str, int]]] = {}

    def close(self) -> None:
        return None

    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]) -> None:
        for relative_path, checksum, timestamp in file_records:
            self._rows.setdefault(thread_id, {})[relative_path] = (checksum, timestamp)

    def get_all_files(self, thread_id: str) -> dict[str, str]:
        return {path: checksum for path, (checksum, _timestamp) in self._rows.get(thread_id, {}).items()}

    def clear_thread(self, thread_id: str) -> int:
        removed = len(self._rows.get(thread_id, {}))
        self._rows.pop(thread_id, None)
        return removed
