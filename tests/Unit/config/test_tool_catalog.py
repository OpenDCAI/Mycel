import pytest

from config.defaults.tool_catalog import tool_enabled_for_agent


def test_tool_enabled_for_agent_rejects_non_boolean_runtime_override() -> None:
    with pytest.raises(RuntimeError, match="Tool runtime override enabled must be a boolean"):
        tool_enabled_for_agent("Bash", configured_tools=["*"], runtime={"tools:Bash": {"enabled": "false"}})


def test_tool_enabled_for_agent_treats_empty_tool_list_as_none_enabled() -> None:
    assert tool_enabled_for_agent("Bash", configured_tools=[], runtime={}) is False


def test_tool_enabled_for_agent_treats_named_tool_list_as_enabled_set() -> None:
    assert tool_enabled_for_agent("Read", configured_tools=["Read"], runtime={}) is True
    assert tool_enabled_for_agent("Bash", configured_tools=["Read"], runtime={}) is False
