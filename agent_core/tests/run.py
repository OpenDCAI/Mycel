"""Dependency-free test runner (no pytest needed).

Collects ``test_*`` functions from the agent_core test modules and runs them.
Each test wraps its own ``asyncio.run``.

    python agent_core/tests/run.py
"""

from __future__ import annotations

import importlib
import sys
import traceback

MODULES = [
    "agent_core.tests.test_loop",
    "agent_core.tests.test_agent",
    "agent_core.tests.test_multiagent",
    "agent_core.tests.test_recovery",
    "agent_core.tests.test_concurrency",
    "agent_core.tests.test_permissions",
    "agent_core.tests.test_lifecycle",
    "agent_core.tests.test_usage",
]


def main() -> int:
    passed = failed = 0
    for modname in MODULES:
        mod = importlib.import_module(modname)
        names = sorted(n for n in dir(mod) if n.startswith("test_"))
        print(f"\n=== {modname} ===")
        for name in names:
            try:
                getattr(mod, name)()
                print(f"PASS  {name}")
                passed += 1
            except Exception:
                print(f"FAIL  {name}")
                traceback.print_exc()
                failed += 1
    print(f"\nTOTAL: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
