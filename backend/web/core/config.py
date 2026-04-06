"""Configuration constants for Leon web backend."""

import os
from pathlib import Path

from config.user_paths import user_home_path

SANDBOXES_DIR = user_home_path("sandboxes")
SANDBOX_VOLUME_ROOT = Path(os.environ.get("LEON_SANDBOX_VOLUME_ROOT", str(user_home_path("volumes")))).expanduser().resolve()

# Workspace
LOCAL_WORKSPACE_ROOT = Path.cwd().resolve()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
