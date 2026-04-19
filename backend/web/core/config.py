"""Configuration constants for Leon web backend."""

from backend import sandbox_paths
from backend.local_workspace import local_workspace_root
from config.user_paths import user_home_path

# SQLite sandbox repos use this as their default local DB path.
DB_PATH = user_home_path("leon.db")
SANDBOXES_DIR = sandbox_paths.SANDBOXES_DIR

# Workspace
LOCAL_WORKSPACE_ROOT = local_workspace_root()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
