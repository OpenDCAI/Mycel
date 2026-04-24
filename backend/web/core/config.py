"""Configuration constants for Mycel web backend."""

from backend.sandboxes.local_workspace import local_workspace_root
from config.user_paths import user_home_path

# SQLite sandbox repos use this as their default local DB path.
DB_PATH = user_home_path("leon.db")

# Workspace
LOCAL_WORKSPACE_ROOT = local_workspace_root()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
