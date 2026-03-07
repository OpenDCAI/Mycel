from abc import ABC, abstractmethod
from pathlib import Path
import base64
import io
import logging
import tarfile
import time

from sandbox.sync.retry import retry_with_backoff

logger = logging.getLogger(__name__)

# @@@tar-batch-limit - files beyond this size (total bytes) fall back to individual writes
_TAR_BATCH_MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _ensure_remote_dir(session_id: str, provider, remote_dir: str):
    """Create remote directory if provider supports execute."""
    if hasattr(provider, 'execute'):
        provider.execute(session_id, f"mkdir -p {remote_dir}")


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
    # Use printf to avoid echo interpretation issues; pipe through base64 -d | tar xzf
    # For very large payloads, chunk into heredoc to avoid arg length limits
    if len(b64) < 100_000:
        # Small payload — single printf
        cmd = f"mkdir -p {workspace_root} && printf '%s' '{b64}' | base64 -d | tar xzf - -C {workspace_root}"
    else:
        # Large payload — use heredoc to avoid shell arg limits
        cmd = f"mkdir -p {workspace_root} && base64 -d <<'__TAR_EOF__' | tar xzf - -C {workspace_root}\n{b64}\n__TAR_EOF__"

    result = provider.execute(session_id, cmd, timeout_ms=60000)
    if hasattr(result, 'exit_code') and result.exit_code and result.exit_code != 0:
        error_msg = getattr(result, 'error', '') or getattr(result, 'output', '')
        raise RuntimeError(f"Batch upload failed (exit {result.exit_code}): {error_msg}")
    logger.info(f"[SYNC-PERF] batch_upload_tar: {len(files)} files, {len(tar_bytes)} bytes tar, {time.time()-t0:.3f}s")


def _batch_download_tar(session_id: str, provider, workspace: Path, workspace_root: str):
    """Download all files from sandbox in a single network call via tar.

    1. Single execute(): tar czf on remote, base64 encode
    2. Decode base64 locally, extract to workspace
    """
    t0 = time.time()
    cmd = f"cd {workspace_root} 2>/dev/null && tar czf - . 2>/dev/null | base64 || echo ''"
    result = provider.execute(session_id, cmd, timeout_ms=60000)

    output = getattr(result, 'output', '') or ''
    output = output.strip()
    if not output:
        return

    try:
        tar_bytes = base64.b64decode(output)
    except Exception:
        logger.warning("Failed to decode tar from sandbox, falling back to empty")
        return

    workspace.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(tar_bytes)
    with tarfile.open(fileobj=buf, mode='r:gz') as tar:
        tar.extractall(path=str(workspace), filter='data')
    logger.info(f"[SYNC-PERF] batch_download_tar: {len(tar_bytes)} bytes, {time.time()-t0:.3f}s")


def _fallback_upload_sequential(session_id: str, provider, workspace: Path, workspace_root: str, files: list[str]):
    """Fallback: upload files one by one (for when tar isn't available)."""
    t0 = time.time()
    _ensure_remote_dir(session_id, provider, workspace_root)
    for rel_path in files:
        file_path = workspace / rel_path
        if file_path.exists():
            remote_path = f"{workspace_root}/{rel_path}"
            content = file_path.read_text()
            provider.write_file(session_id, remote_path, content)
    logger.info(f"[SYNC-PERF] fallback_upload_sequential: {len(files)} files, {time.time()-t0:.3f}s")


def _fallback_download_sequential(session_id: str, provider, workspace: Path, workspace_root: str):
    """Fallback: download files one by one."""
    workspace.mkdir(parents=True, exist_ok=True)

    def _recurse(remote_path: str, local_path: Path):
        items = provider.list_dir(session_id, remote_path)
        for item in items:
            remote_item = f"{remote_path}/{item['name']}".replace("//", "/")
            local_item = local_path / item["name"]
            if item["type"] == "directory":
                local_item.mkdir(parents=True, exist_ok=True)
                _recurse(remote_item, local_item)
            else:
                content = provider.read_file(session_id, remote_item)
                local_item.write_text(content)

    _recurse(workspace_root, workspace)


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


class FullSyncStrategy(SyncStrategy):
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root

    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        workspace = self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return

        remote_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'

        all_files = files or [
            str(fp.relative_to(workspace))
            for fp in workspace.rglob("*") if fp.is_file()
        ]
        if not all_files:
            return

        if hasattr(provider, 'execute'):
            try:
                _batch_upload_tar(session_id, provider, workspace, remote_root, all_files)
                return
            except Exception:
                logger.warning("Batch tar upload failed, falling back to sequential", exc_info=True)

        _fallback_upload_sequential(session_id, provider, workspace, remote_root, all_files)

    def download(self, thread_id: str, session_id: str, provider):
        workspace = self.workspace_root / thread_id / "files"
        remote_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'

        if hasattr(provider, 'execute'):
            try:
                _batch_download_tar(session_id, provider, workspace, remote_root)
                return
            except Exception:
                logger.warning("Batch tar download failed, falling back to sequential", exc_info=True)

        _fallback_download_sequential(session_id, provider, workspace, remote_root)


class IncrementalSyncStrategy(SyncStrategy):
    def __init__(self, workspace_root: Path, state):
        self.workspace_root = workspace_root
        self.state = state

    @retry_with_backoff(max_retries=3, backoff_factor=1)
    def upload(self, thread_id: str, session_id: str, provider, files: list[str] | None = None):
        workspace = self.workspace_root / thread_id / "files"
        if not workspace.exists():
            return

        if files:
            to_upload = files
        else:
            to_upload = self.state.detect_changes(thread_id, workspace)

        if not to_upload:
            return

        remote_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'

        # @@@batch-upload - single tar call for all files
        if hasattr(provider, 'execute'):
            try:
                _batch_upload_tar(session_id, provider, workspace, remote_root, to_upload)
            except Exception:
                logger.warning("Batch tar upload failed, falling back to sequential", exc_info=True)
                _fallback_upload_sequential(session_id, provider, workspace, remote_root, to_upload)
        else:
            _fallback_upload_sequential(session_id, provider, workspace, remote_root, to_upload)

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
        workspace = self.workspace_root / thread_id / "files"
        remote_root = getattr(provider, 'WORKSPACE_ROOT', '/workspace') + '/files'

        if hasattr(provider, 'execute'):
            try:
                _batch_download_tar(session_id, provider, workspace, remote_root)
                return
            except Exception:
                logger.warning("Batch tar download failed, falling back to sequential", exc_info=True)

        _fallback_download_sequential(session_id, provider, workspace, remote_root)
