"""Configuration constants for Leon web backend."""

import os
from pathlib import Path

from config.user_paths import user_home_path

# SQLite sandbox repos use this as their default local DB path.
DB_PATH = user_home_path("leon.db")
SANDBOXES_DIR = user_home_path("sandboxes")

# Workspace
LOCAL_WORKSPACE_ROOT = Path(os.environ.get("LEON_LOCAL_WORKSPACE_ROOT", str(Path.home()))).expanduser().resolve()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
