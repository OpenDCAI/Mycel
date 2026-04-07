from __future__ import annotations

from types import SimpleNamespace

import pytest
from psycopg import OperationalError

from backend.web.core import lifespan as lifespan_module


def test_web_runtime_contract_requires_postgres_checkpointer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEON_POSTGRES_URL", raising=False)

    with pytest.raises(RuntimeError, match="LEON_POSTGRES_URL"):
        lifespan_module._require_web_runtime_contract()


@pytest.mark.asyncio
async def test_web_runtime_contract_fails_when_postgres_checkpointer_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEON_POSTGRES_URL", "postgresql://example")

    async def _connect(_dsn: str):
        raise OperationalError("connection refused")

    fake_async_connection = SimpleNamespace(connect=_connect)
    monkeypatch.setattr(lifespan_module, "AsyncConnection", fake_async_connection)

    with pytest.raises(OperationalError, match="connection refused"):
        await lifespan_module._validate_web_checkpointer_contract()
