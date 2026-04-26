from pathlib import Path

from sandbox.config import sandbox_config_dir

SANDBOXES_DIR: Path | None = sandbox_config_dir()
