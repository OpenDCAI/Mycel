from __future__ import annotations

import pytest

from backend.web.core import lifespan as lifespan_module


def test_web_runtime_contract_requires_postgres_checkpointer_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEON_POSTGRES_URL", raising=False)

    with pytest.raises(RuntimeError, match="LEON_POSTGRES_URL"):
        lifespan_module._require_web_runtime_contract()
