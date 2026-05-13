import gc
import sys
import time
from pathlib import Path

import pytest

from sandbox.thread_context import set_current_messages, set_current_run_id, set_current_thread_id

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def clean_sandbox_thread_context():
    set_current_thread_id("")
    set_current_run_id("")
    set_current_messages([])
    yield
    set_current_thread_id("")
    set_current_run_id("")
    set_current_messages([])


def _unlink_db(db_path: Path) -> None:
    """Delete a SQLite database file safely on all platforms.

    On Windows, sqlite3 connections hold OS-level file locks. Force GC to
    release any lingering connection objects, delete WAL/SHM auxiliary files,
    then retry the main file deletion a few times before giving up.
    """
    gc.collect()
    for wal_suffix in ("-wal", "-shm"):
        Path(str(db_path) + wal_suffix).unlink(missing_ok=True)
    if sys.platform == "win32":
        for _attempt in range(5):
            try:
                db_path.unlink(missing_ok=True)
                return
            except PermissionError:
                time.sleep(0.1)
                gc.collect()
        db_path.unlink(missing_ok=True)  # final attempt; raises if still locked
    else:
        db_path.unlink(missing_ok=True)


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    yield db_path
    _unlink_db(db_path)
