# Backward compat - deprecated, use core.runtime.agent instead
from core.runtime.agent import (  # noqa: F401
    LeonAgent,
    create_leon_agent,
)

__all__ = ["LeonAgent", "create_leon_agent"]
