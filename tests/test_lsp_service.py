from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.runtime.registry import ToolRegistry
from core.tools.lsp.service import LSPService


class _FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, str, int, int]] = []

    async def request_definition(self, rel_path: str, line: int, character: int):
        self.calls.append(("definition", rel_path, line, character))
        return [
            {
                "absolutePath": "/tmp/example.py",
                "range": {"start": {"line": line, "character": character}},
            }
        ]


class _FakePyright:
    def __init__(self):
        self.calls: list[tuple[str, str, int, int]] = []

    async def request_implementation(self, rel_path: str, line: int, character: int):
        self.calls.append(("implementation", rel_path, line, character))
        return [
            {
                "absolutePath": "/tmp/example.py",
                "range": {"start": {"line": line, "character": character}},
            }
        ]


def test_lsp_schema_uses_one_based_character_positions(tmp_path):
    reg = ToolRegistry()
    LSPService(registry=reg, workspace_root=tmp_path)

    schema = reg.get("LSP").get_schema()
    props = schema["parameters"]["properties"]

    assert "character" in props
    assert "column" not in props
    assert "1-based" in props["line"]["description"]
    assert "1-based" in props["character"]["description"]


@pytest.mark.asyncio
async def test_lsp_handle_converts_one_based_positions_to_zero_based_for_definition(tmp_path):
    reg = ToolRegistry()
    service = LSPService(registry=reg, workspace_root=tmp_path)
    fake = _FakeSession()
    service._get_session = AsyncMock(return_value=fake)

    file_path = tmp_path / "example.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    result = await service._handle(
        operation="goToDefinition",
        file_path=str(file_path),
        line=5,
        character=3,
    )

    assert fake.calls == [("definition", "example.py", 4, 2)]
    payload = json.loads(result)
    assert payload[0]["line"] == 4
    assert payload[0]["column"] == 2


@pytest.mark.asyncio
async def test_lsp_handle_converts_one_based_positions_to_zero_based_for_pyright_ops(tmp_path):
    reg = ToolRegistry()
    service = LSPService(registry=reg, workspace_root=tmp_path)
    fake = _FakePyright()
    service._get_pyright = AsyncMock(return_value=fake)

    file_path = tmp_path / "example.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    result = await service._handle(
        operation="goToImplementation",
        file_path=str(file_path),
        line=7,
        character=4,
    )

    assert fake.calls == [("implementation", "example.py", 6, 3)]
    payload = json.loads(result)
    assert payload[0]["line"] == 6
    assert payload[0]["column"] == 3
