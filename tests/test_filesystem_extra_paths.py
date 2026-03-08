"""extra_allowed_paths lets the middleware accept paths outside workspace_root."""

import tempfile
from pathlib import Path

from core.filesystem.middleware import FileSystemMiddleware


def test_extra_allowed_path_validates() -> None:
    """A file under an extra_allowed_path should pass validation."""
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as extra:
        mw = FileSystemMiddleware(workspace, extra_allowed_paths=[extra], verbose=False)
        target = Path(extra) / "data.txt"
        target.write_text("hello")

        ok, err, resolved = mw._validate_path(str(target), "read")
        assert ok, f"Expected valid but got: {err}"
        assert resolved == target.resolve()


def test_without_extra_paths_blocks() -> None:
    """Without extra_allowed_paths, a path outside workspace must be rejected."""
    with tempfile.TemporaryDirectory() as workspace, tempfile.TemporaryDirectory() as outside:
        mw = FileSystemMiddleware(workspace, verbose=False)
        target = Path(outside) / "secret.txt"
        target.write_text("nope")

        ok, err, _ = mw._validate_path(str(target), "read")
        assert not ok
        assert "outside workspace" in err.lower()
