"""SpillBuffer - catches oversized tool outputs, writes to disk, returns preview."""

from .middleware import SpillBufferMiddleware
from .spill import spill_if_needed

__all__ = ["SpillBufferMiddleware", "spill_if_needed"]
