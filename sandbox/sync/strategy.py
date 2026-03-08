from abc import ABC, abstractmethod
from pathlib import Path
import base64
import io
import logging
import tarfile
import time

from sandbox.sync.retry import retry_with_backoff

logger = logging.getLogger(__name__)


def _pack_tar(workspace: Path, files: list[str]) -> bytes:
    """Pack files into an in-memory tar.gz archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for rel_path in files:
            full = workspace / rel_path
            if full.exists() and full.is_file():
                tar.add(str(full), arcname=rel_path)
    return buf.getvalue()


def _batch_upload_tar(session_id: str, provider, workspace: Path, workspace_root: str, files: list[str]):
    """Upload multiple files in a single network call via tar.

    1. Pack files into tar.gz in memory
    2. Base64-encode
    3. Single execute(): decode + extract on remote
    """
    t0 = time.time()
    tar_bytes = _pack_tar(workspace, files)
    if not tar_bytes or len(tar_bytes) < 10:
        return

    b64 = base64.b64encode(tar_bytes).decode('ascii')

    # @@@single-call-upload - one execute() replaces N write_file() calls
    if len(b64) < 100_000:
        cmd = f"mkdir -p {workspace_root} && printf '%s' '{b64}' | base64 -d | tar xzf - -C {workspace_root}"
    else:
        # Large payload — heredoc to avoid shell arg limits
        cmd = f"mkdir -p {workspace_root} && base64 -d <<'__TAR_EOF__' | tar xzf - -C {workspace_root}\n{b64}\n__TAR_EOF__"

    result = provider.execute(session_id, cmd, timeout_ms=60000)
    if hasattr(result, 'exit_code') and result.exit_code and result.exit_code != 0:
        error_msg = getattr(result, 'error', '') or getattr(result, 'output', '')
        raise RuntimeError(f"Batch upload failed (exit {result.exit_code}): {error_msg}")
    logger.info(f"[SYNC-PERF] batch_upload_tar: {len(files)} files, {len(tar_bytes)} bytes tar, {time.time()-t0:.3f}s")


def _batch_download_tar(session_id: str, provider, workspace: Path, workspace_root: str):
    """Download all files from sandbox in a single network call via tar."""
    t0 = time.time()
    cmd = f"cd {workspace_root} 2>/dev/null && tar czf - . 2>/dev/null | base64 || echo ''"
    result = provider.execute(session_id, cmd, timeout_ms=60000)

    output = getattr(result, 'output', '') or ''
    output = output.strip()
    if not output:
        return

    tar_bytes = base64.b64decode(output)
    workspace.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(tar_bytes)
    with tarfile.open(fileobj=buf, mode='r:gz') as tar:
        tar.extractall(path=str(workspace), filter='data')
    logger.info(f"[SYNC-PERF] batch_download_tar: {len(tar_bytes)} bytes, {time.time()-t0:.3f}s")


class SyncStrategy(ABC):
    @abstractmethod
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        pass

    @abstractmethod
    def download(self, thread_id: str, session_id: str, provider):
        pass


class NoOpStrategy(SyncStrategy):
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        pass

    def download(self, thread_id: str, session_id: str, provider):
        pass


class IncrementalSyncStrategy(SyncStrategy):
    def __init__(self, workspace_root: Path, state, manager=None):
        self.workspace_root = workspace_root
        self.state = state
        self.manager = manager

    @retry_with_backoff(max_retries=3, backoff_factor=1)
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        workspace = self.manager.get_thread_workspace_path(thread_id) if self.manager else self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return

        if files:
            to_upload = files
        else:
            to_upload = self.state.detect_changes(thread_id, workspace)

        if not to_upload:
            return

        remote_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'
        _batch_upload_tar(session_id, provider, workspace, remote_root, to_upload)

        # @@@batch-track - single DB transaction for all files
        now = int(time.time())
        records = []
        for rel_path in to_upload:
            file_path = workspace / rel_path
            if file_path.exists():
                from sandbox.sync.state import _calculate_checksum
                checksum = _calculate_checksum(file_path)
                records.append((rel_path, checksum, now))
        self.state.track_files_batch(thread_id, records)

    def download(self, thread_id: str, session_id: str, provider):
        workspace = self.manager.get_thread_workspace_path(thread_id) if self.manager else self.workspace_root / thread_id / "files"
        remote_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'
        _batch_download_tar(session_id, provider, workspace, remote_root)
        self._update_checksums_after_download(thread_id)

    def _update_checksums_after_download(self, thread_id: str):
        """Update checksum DB to match downloaded files, preventing redundant re-uploads on resume."""
        workspace = self.manager.get_thread_workspace_path(thread_id) if self.manager else self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return
        from sandbox.sync.state import _calculate_checksum
        now = int(time.time())
        records = []
        for file_path in workspace.rglob("*"):
            if not file_path.is_file():
                continue
            relative = str(file_path.relative_to(workspace))
            checksum = _calculate_checksum(file_path)
            records.append((relative, checksum, now))
        self.state.track_files_batch(thread_id, records)
