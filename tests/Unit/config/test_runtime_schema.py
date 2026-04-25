import pytest

from config.schema import MCPConfig


def test_mcp_config_rejects_string_enabled() -> None:
    with pytest.raises(ValueError, match="enabled"):
        MCPConfig.model_validate({"enabled": "false", "servers": {}})
