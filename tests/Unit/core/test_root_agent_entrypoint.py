import importlib
import re
from pathlib import Path


def test_root_agent_shim_aliases_canonical_runtime_entrypoint():
    root_agent = importlib.import_module("agent")
    runtime_agent = importlib.import_module("core.runtime.agent")

    assert root_agent.LeonAgent is runtime_agent.LeonAgent
    assert root_agent.create_leon_agent is runtime_agent.create_leon_agent


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
