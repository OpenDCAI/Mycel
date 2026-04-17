import re
from pathlib import Path


def test_root_agent_compatibility_shim_is_removed():
    repo_root = Path(__file__).resolve().parents[3]

    assert not (repo_root / "agent.py").exists()
    assert 'py-modules = ["agent"]' not in (repo_root / "pyproject.toml").read_text(encoding="utf-8")


def test_internal_entrypoints_import_canonical_runtime_agent():
    repo_root = Path(__file__).resolve().parents[3]
    checked_paths = [
        Path("langgraph_app.py"),
        Path("examples/chat.py"),
        Path("tests/Integration/test_e2e_summary_persistence.py"),
    ]
    root_agent_import = re.compile(r"^\s*(from agent import|import agent(?:\s|$))", re.MULTILINE)

    offenders = [str(path) for path in checked_paths if root_agent_import.search((repo_root / path).read_text(encoding="utf-8"))]

    assert offenders == []
