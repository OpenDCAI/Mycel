import base64
import io
import logging
import tarfile
import time
from abc import ABC, abstractmethod
from pathlib import Path

from sandbox.sync.retry import retry_with_backoff

logger = logging.getLogger(__name__)


def _native_upload(session_id: str, provider, workspace: Path, workspace_root: str, files: list[str]):
    """Upload files using provider's native file API (upload_bytes).

    Each file is uploaded individually via the SDK's binary upload endpoint.
    No shell commands, no base64, no size limits from execute().
    """
    t0 = time.time()
    total_bytes = 0
    # @@@mkdir-batch - collect all needed dirs, create in one command
    dirs_needed = {workspace_root}
    upload_items: list[tuple[str, bytes]] = []
    for rel_path in files:
        local = workspace / rel_path
        if not local.exists() or not local.is_file():
            logger.warning("[SYNC] native_upload: skipping missing file %s", local)
            continue
        remote = f"{workspace_root}/{rel_path}"
        parent = str(Path(remote).parent)
        if parent != workspace_root:
            dirs_needed.add(parent)
        upload_items.append((remote, local.read_bytes()))
    if not upload_items:
        return
    provider.execute(session_id, "mkdir -p " + " ".join(sorted(dirs_needed)), timeout_ms=10000)
    for remote, data in upload_items:
        provider.upload_bytes(session_id, remote, data)
        total_bytes += len(data)
    logger.info("[SYNC-PERF] native_upload: %d files, %d bytes, %.3fs", len(files), total_bytes, time.time() - t0)


def _native_download(session_id: str, provider, workspace: Path, workspace_root: str):
    """Download files from sandbox using provider's native file API.

    Lists remote dir, downloads each file individually.
    """
    t0 = time.time()
    try:
        entries = provider.list_dir(session_id, workspace_root)
    except Exception:
        logger.info("[SYNC] native_download skipped: cannot list %s", workspace_root)
        return

    workspace.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    stack = [(workspace_root, entries)]
    while stack:
        current_remote, items = stack.pop()
        for item in items:
            name = item.get("name", "")
            item_type = item.get("type", "file")
            remote_path = f"{current_remote}/{name}"
            if item_type == "directory":
                try:
                    sub_entries = provider.list_dir(session_id, remote_path)
                    stack.append((remote_path, sub_entries))
                except Exception:
                    continue
            else:
                rel = remote_path.removeprefix(workspace_root + "/")
                local = workspace / rel
                local.parent.mkdir(parents=True, exist_ok=True)
                try:
                    data = provider.download_bytes(session_id, remote_path)
                    local.write_bytes(data)
                    total_bytes += len(data)
                except Exception:
                    logger.warning("[SYNC] native_download: failed to download %s", remote_path, exc_info=True)
    logger.info("[SYNC-PERF] native_download: %d bytes, %.3fs", total_bytes, time.time() - t0)


def _pack_tar(workspace: Path, files: list[str]) -> bytes:
    """Pack files into an in-memory tar.gz archive."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for rel_path in files:
            full = workspace / rel_path
            if full.exists() and full.is_file():
                tar.add(str(full), arcname=rel_path)
            else:
                logger.warning("_pack_tar: skipping missing file %s", full)
    return buf.getvalue()


def _batch_upload_tar(session_id: str, provider, workspace: Path, workspace_root: str, files: list[str]):
    """Fallback: upload via tar+base64+execute for providers without native file API."""
    t0 = time.time()
    tar_bytes = _pack_tar(workspace, files)
    if not tar_bytes or len(tar_bytes) < 10:
        return

    b64 = base64.b64encode(tar_bytes).decode("ascii")

    if len(b64) < 100_000:
        cmd = f"mkdir -p {workspace_root} && printf '%s' '{b64}' | base64 -d | tar xzmf - -C {workspace_root}"
    else:
        cmd = f"mkdir -p {workspace_root} && base64 -d <<'__TAR_EOF__' | tar xzmf - -C {workspace_root}\n{b64}\n__TAR_EOF__"  # noqa: E501

    result = provider.execute(session_id, cmd, timeout_ms=60000)
    exit_code = getattr(result, "exit_code", None)
    if exit_code is not None and exit_code != 0:
        error_msg = getattr(result, "error", "") or getattr(result, "output", "")
        raise RuntimeError(f"Batch upload failed (exit {exit_code}): {error_msg}")
    logger.info("[SYNC-PERF] batch_upload_tar: %d files, %d bytes tar, %.3fs", len(files), len(tar_bytes), time.time() - t0)


def _batch_download_tar(session_id: str, provider, workspace: Path, workspace_root: str):
    """Fallback: download via tar+base64+execute for providers without native file API."""
    t0 = time.time()
    check = provider.execute(session_id, f"test -d {workspace_root} && echo EXISTS", timeout_ms=10000)
    check_out = (getattr(check, "output", "") or "").strip()
    if check_out != "EXISTS":
        logger.info("[SYNC] download skipped: %s does not exist in sandbox", workspace_root)
        return

    cmd = f"cd {workspace_root} && tar czf - . | base64"
    result = provider.execute(session_id, cmd, timeout_ms=60000)

    exit_code = getattr(result, "exit_code", None)
    if exit_code is not None and exit_code != 0:
        error_msg = getattr(result, "error", "") or getattr(result, "output", "")
        raise RuntimeError(f"Batch download failed (exit {exit_code}): {error_msg}")

    output = getattr(result, "output", "") or ""
    output = output.strip()
    if not output:
        return

    tar_bytes = base64.b64decode(output)
    workspace.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO(tar_bytes)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(path=str(workspace), filter="data")
    logger.info("[SYNC-PERF] batch_download_tar: %d bytes, %.3fs", len(tar_bytes), time.time() - t0)


class SyncStrategy(ABC):
    @abstractmethod
    def upload(
        self,
        source_path: Path,
        remote_path: str,
        session_id: str,
        provider,
        files: list[str] | None = None,
        state_key: str | None = None,
    ):
        pass

    @abstractmethod
    def download(self, source_path: Path, remote_path: str, session_id: str, provider, state_key: str | None = None):
        pass

    def clear_state(self, state_key: str):
        """Remove all sync state for a key. Default no-op."""
        pass


class NoOpStrategy(SyncStrategy):
    def upload(
        self,
        source_path: Path,
        remote_path: str,
        session_id: str,
        provider,
        files: list[str] | None = None,
        state_key: str | None = None,
    ):
        pass

    def download(self, source_path: Path, remote_path: str, session_id: str, provider, state_key: str | None = None):
        pass


class IncrementalSyncStrategy(SyncStrategy):
    def __init__(self, state):
        self.state = state

    @retry_with_backoff(max_retries=3, backoff_factor=1)
    def upload(
        self,
        source_path: Path,
        remote_path: str,
        session_id: str,
        provider,
        files: list[str] | None = None,
        state_key: str | None = None,
    ):
        if not source_path.exists():
            return

        if files:
            to_upload = files
        else:
            to_upload = self.state.detect_changes(state_key, source_path)

        if not to_upload:
            return

        # @@@native-first - use provider SDK file API when available, fall back to tar+execute
        if "upload_bytes" in type(provider).__dict__:
            _native_upload(session_id, provider, source_path, remote_path, to_upload)
        else:
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

    def download(self, source_path: Path, remote_path: str, session_id: str, provider, state_key: str | None = None):
        if "download_bytes" in type(provider).__dict__:
            _native_download(session_id, provider, source_path, remote_path)
        else:
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
