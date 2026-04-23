from __future__ import annotations

import ast
from pathlib import Path


def test_cli_agent_package_does_not_import_backend_modules() -> None:
    cli_root = Path(__file__).resolve().parents[3] / "cli" / "agent"

    for path in sorted(cli_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue

            assert all(not name.startswith("backend") for name in imported), (
                f"{path.name} imports backend internals: {imported}"
            )
