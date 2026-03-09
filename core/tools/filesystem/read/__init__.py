"""Read subpackage - handles file reading with type-specific strategies."""

from core.tools.filesystem.read.dispatcher import read_file
from core.tools.filesystem.read.types import FileType, ReadLimits, ReadResult

__all__ = ["FileType", "ReadLimits", "ReadResult", "read_file"]
