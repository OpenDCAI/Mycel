"""Configuration constants for Leon web backend."""

import os
from pathlib import Path

# Database paths
DB_PATH = Path.home() / ".leon" / "leon.db"
SANDBOXES_DIR = Path.home() / ".leon" / "sandboxes"
SANDBOX_FILES_ROOT = Path(
    os.environ.get("LEON_SANDBOX_FILES_ROOT", str(Path.home() / ".leon" / "sandbox_files"))
).expanduser().resolve()

# Workspace
LOCAL_WORKSPACE_ROOT = Path.cwd().resolve()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
