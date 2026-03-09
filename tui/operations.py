# Backward compat - deprecated, use core.operations instead
from core.operations import (  # noqa: F401
    FileOperation,
    FileOperationRecorder,
    current_thread_id,
    get_recorder,
    set_recorder,
)

__all__ = [
    "FileOperation",
    "FileOperationRecorder",
    "current_thread_id",
    "get_recorder",
    "set_recorder",
]
