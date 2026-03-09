"""FileSystem backend abstraction.

Canonical location: sandbox.interfaces.filesystem
This module re-exports for backward compatibility.
"""

from sandbox.interfaces.filesystem import *  # noqa: F401,F403
from sandbox.interfaces.filesystem import (
    DirEntry,
    DirListResult,
    FileReadResult,
    FileSystemBackend,
    FileWriteResult,
)

__all__ = [
    "FileSystemBackend",
    "FileReadResult",
    "FileWriteResult",
    "DirEntry",
    "DirListResult",
]
