"""Command Hooks Plugin System."""

from core.tools.command.hooks.base import BashHook as CommandHook
from core.tools.command.hooks.base import HookResult
from core.tools.command.hooks.loader import load_hooks

__all__ = ["CommandHook", "HookResult", "load_hooks"]
