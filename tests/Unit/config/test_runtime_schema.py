import json
from pathlib import Path

import pytest

from config.schema import LeonSettings


def test_runtime_schema_has_no_top_level_mcp_config() -> None:
    assert not hasattr(LeonSettings(), "mcp")
    with pytest.raises(ValueError, match="mcp"):
        LeonSettings.model_validate({"mcp": {"enabled": True, "servers": {}}})


def test_runtime_fields_must_live_under_runtime_object() -> None:
    with pytest.raises(ValueError, match="context_limit"):
        LeonSettings.model_validate({"context_limit": 12345})


def test_default_runtime_config_uses_runtime_object() -> None:
    defaults_path = Path(__file__).parents[3] / "config" / "defaults" / "runtime.json"
    payload = json.loads(defaults_path.read_text(encoding="utf-8"))

    assert "runtime" in payload
    assert "mcp" not in payload
    assert "context_limit" not in payload
    assert "block_network_commands" not in payload


def test_runtime_schema_rejects_unknown_nested_fields() -> None:
    with pytest.raises(ValueError, match="max_results"):
        LeonSettings.model_validate({"tools": {"search": {"max_results": 50}}})


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("runtime.enable_audit_log", {"runtime": {"enable_audit_log": "false"}}),
        ("runtime.block_network_commands", {"runtime": {"block_network_commands": 1}}),
        ("memory.pruning.enabled", {"memory": {"pruning": {"enabled": "false"}}}),
        ("memory.pruning.trim_tool_results", {"memory": {"pruning": {"trim_tool_results": 1}}}),
        ("memory.compaction.enabled", {"memory": {"compaction": {"enabled": "false"}}}),
        ("tools.filesystem.enabled", {"tools": {"filesystem": {"enabled": 1}}}),
        ("tools.search.tools.glob", {"tools": {"search": {"tools": {"glob": "false"}}}}),
        ("tools.web.enabled", {"tools": {"web": {"enabled": "false"}}}),
        ("tools.command.enabled", {"tools": {"command": {"enabled": 1}}}),
        ("tools.spill_buffer.enabled", {"tools": {"spill_buffer": {"enabled": "false"}}}),
    ],
)
def test_runtime_schema_rejects_coerced_booleans(path: str, payload: dict) -> None:
    with pytest.raises(ValueError, match=path.split(".")[-1]):
        LeonSettings.model_validate(payload)
