"""Pytest configuration for Leon tests.

Ensures the project root is in sys.path so imports work correctly.
"""

import gc
import sys
import time
from pathlib import Path

import pytest

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


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
    """Provide a temporary SQLite database path with Windows-safe cleanup."""
    db_path = tmp_path / "test.db"
    yield db_path
    _unlink_db(db_path)
