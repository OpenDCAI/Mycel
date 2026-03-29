"""Configuration constants for Leon web backend."""

import os
from pathlib import Path

# Database paths
DB_PATH = Path.home() / ".leon" / "leon.db"
SANDBOXES_DIR = Path.home() / ".leon" / "sandboxes"
FILE_CHANNEL_ROOT = Path(
    os.environ.get("LEON_FILE_CHANNEL_ROOT",
                   os.environ.get("LEON_SANDBOX_VOLUME_ROOT",  # backwards compat
                                  str(Path.home() / ".leon" / "volumes")))
).expanduser().resolve()

# Workspace
LOCAL_WORKSPACE_ROOT = Path.cwd().resolve()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
