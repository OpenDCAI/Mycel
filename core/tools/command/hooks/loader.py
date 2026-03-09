"""Bash hook loader - auto-discovers and loads all hook plugins."""

import importlib
import inspect
from pathlib import Path

from .base import BashHook


def load_hooks(
    hooks_dir: Path | str | None = None,
    workspace_root: Path | str | None = None,
    **hook_kwargs,
) -> list[BashHook]:
    """Auto-load all bash hook plugins, sorted by priority."""
    hooks_dir = Path(hooks_dir) if hooks_dir else Path(__file__).parent
    hooks: list[BashHook] = []

    for py_file in hooks_dir.glob("*.py"):
        if py_file.name.startswith("_") or py_file.name in ["base.py", "loader.py"]:
            continue

        try:
            module_name = f"middleware.command.hooks.{py_file.stem}"
            module = importlib.import_module(module_name)

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if obj is BashHook or not issubclass(obj, BashHook) or obj.__module__ != module.__name__:
                    continue

                hook_instance = obj(workspace_root=workspace_root, **hook_kwargs)
                if hook_instance.enabled:
                    hooks.append(hook_instance)
                    print(f"[BashHooks] Loaded: {hook_instance.name} (priority={hook_instance.priority})")

        except Exception as e:
            print(f"[BashHooks] Failed to load {py_file.name}: {e}")

    hooks.sort(key=lambda h: h.priority)
    print(f"[BashHooks] Total {len(hooks)} hooks loaded")
    return hooks


def discover_hooks() -> list[str]:
    """Discover all available hook plugins without loading them."""
    hooks_dir = Path(__file__).parent
    return [
        py_file.stem
        for py_file in hooks_dir.glob("*.py")
        if not py_file.name.startswith("_") and py_file.name not in ["base.py", "loader.py"]
    ]
