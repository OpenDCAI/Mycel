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
            else:
                logger.warning("_pack_tar: skipping missing file %s", full)
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
        cmd = f"mkdir -p {workspace_root} && printf '%s' '{b64}' | base64 -d | tar xzmf - -C {workspace_root}"
    else:
        # Large payload — heredoc to avoid shell arg limits
        cmd = f"mkdir -p {workspace_root} && base64 -d <<'__TAR_EOF__' | tar xzmf - -C {workspace_root}\n{b64}\n__TAR_EOF__"

    result = provider.execute(session_id, cmd, timeout_ms=60000)
    exit_code = getattr(result, 'exit_code', None)
    if exit_code is not None and exit_code != 0:
        error_msg = getattr(result, 'error', '') or getattr(result, 'output', '')
        raise RuntimeError(f"Batch upload failed (exit {exit_code}): {error_msg}")
    logger.info("[SYNC-PERF] batch_upload_tar: %d files, %d bytes tar, %.3fs", len(files), len(tar_bytes), time.time()-t0)


def _batch_download_tar(session_id: str, provider, workspace: Path, workspace_root: str):
    """Download all files from sandbox in a single network call via tar."""
    t0 = time.time()
    # @@@download-check-dir - skip if remote dir doesn't exist (nothing to download)
    check = provider.execute(session_id, f"test -d {workspace_root} && echo EXISTS", timeout_ms=10000)
    check_out = (getattr(check, 'output', '') or '').strip()
    if check_out != "EXISTS":
        logger.info("[SYNC] download skipped: %s does not exist in sandbox", workspace_root)
        return

    cmd = f"cd {workspace_root} && tar czf - . | base64"
    result = provider.execute(session_id, cmd, timeout_ms=60000)

    exit_code = getattr(result, 'exit_code', None)
    if exit_code is not None and exit_code != 0:
        error_msg = getattr(result, 'error', '') or getattr(result, 'output', '')
        raise RuntimeError(f"Batch download failed (exit {exit_code}): {error_msg}")

    output = getattr(result, 'output', '') or ''
    output = output.strip()
    if not output:
        return

    tar_bytes = base64.b64decode(output)
    workspace.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(tar_bytes)
    with tarfile.open(fileobj=buf, mode='r:gz') as tar:
        tar.extractall(path=str(workspace), filter='data')
    logger.info("[SYNC-PERF] batch_download_tar: %d bytes, %.3fs", len(tar_bytes), time.time()-t0)


class SyncStrategy(ABC):
    @abstractmethod
    def upload(self, source_path: Path, remote_path: str, session_id: str, provider,
               files: list[str] | None = None, state_key: str | None = None):
        pass

    @abstractmethod
    def download(self, source_path: Path, remote_path: str, session_id: str, provider,
                 state_key: str | None = None):
        pass

    def clear_state(self, state_key: str):
        """Remove all sync state for a key. Default no-op."""
        pass


class NoOpStrategy(SyncStrategy):
    def upload(self, source_path: Path, remote_path: str, session_id: str, provider,
               files: list[str] | None = None, state_key: str | None = None):
        pass

    def download(self, source_path: Path, remote_path: str, session_id: str, provider,
                 state_key: str | None = None):
        pass


class IncrementalSyncStrategy(SyncStrategy):
    def __init__(self, state):
        self.state = state

    @retry_with_backoff(max_retries=3, backoff_factor=1)
    def upload(self, source_path: Path, remote_path: str, session_id: str, provider,
               files: list[str] | None = None, state_key: str | None = None):
        if not source_path.exists():
            return

        if files:
            to_upload = files
        else:
            to_upload = self.state.detect_changes(state_key, source_path)

        if not to_upload:
            return

        _batch_upload_tar(session_id, provider, source_path, remote_path, to_upload)

        # @@@batch-track - single DB transaction for all files
        now = int(time.time())
        records = []
        for rel_path in to_upload:
            file_path = source_path / rel_path
            if file_path.exists():
                from sandbox.sync.state import _calculate_checksum
                checksum = _calculate_checksum(file_path)
                records.append((rel_path, checksum, now))
        self.state.track_files_batch(state_key, records)

    def download(self, source_path: Path, remote_path: str, session_id: str, provider,
                 state_key: str | None = None):
        _batch_download_tar(session_id, provider, source_path, remote_path)
        self._update_checksums_after_download(state_key, source_path)

    def clear_state(self, state_key: str):
        self.state.clear_thread(state_key)

    def _update_checksums_after_download(self, state_key: str, source_path: Path):
        """Update checksum DB to match downloaded files, preventing redundant re-uploads on resume."""
        if not source_path.exists():
            return
        from sandbox.sync.state import _calculate_checksum
        now = int(time.time())
        records = []
        for file_path in source_path.rglob("*"):
            if not file_path.is_file():
                continue
            relative = str(file_path.relative_to(source_path))
            checksum = _calculate_checksum(file_path)
            records.append((relative, checksum, now))
        self.state.track_files_batch(state_key, records)
