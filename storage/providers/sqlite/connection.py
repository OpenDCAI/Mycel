"""Backward-compatible SQLite connection helpers.

All new call sites should prefer `storage.providers.sqlite.kernel`.
"""

import sqlite3
from pathlib import Path

from storage.providers.sqlite.kernel import BUSY_TIMEOUT_MS, connect_sqlite


def create_connection(
    db_path: Path | str,
    *,
    row_factory: type | None = None,
) -> sqlite3.Connection:
    """Create a SQLite connection with standard Leon settings.

    Guarantees: WAL mode, 30s busy_timeout, check_same_thread=False.
    """
    return connect_sqlite(
        db_path,
        row_factory=row_factory,
        check_same_thread=False,
        timeout_ms=BUSY_TIMEOUT_MS,
    )
