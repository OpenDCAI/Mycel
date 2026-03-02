"""Configuration constants for Leon web backend."""

from pathlib import Path

# Database paths
DB_PATH = Path.home() / ".leon" / "leon.db"
SANDBOXES_DIR = Path.home() / ".leon" / "sandboxes"
# @@@local-workspace-root - Local mode file tree root defaults to ~/Downloads
LOCAL_WORKSPACE_ROOT = (Path.home() / "Downloads").resolve()

# Idle reaper
IDLE_REAPER_INTERVAL_SEC = 30
