"""Configuration constants for Leon web backend."""

from backend.local_workspace import local_workspace_root
from config.user_paths import user_home_path

# SQLite sandbox repos use this as their default local DB path.
DB_PATH = user_home_path("leon.db")
SANDBOXES_DIR = user_home_path("sandboxes")

# Workspace
LOCAL_WORKSPACE_ROOT = local_workspace_root()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
