from __future__ import annotations

from types import SimpleNamespace

from backend.web.services import idle_reaper as idle_reaper_module


class _MutatingManager:
    def __init__(self, pool: dict[str, object], victim_key: str | None = None) -> None:
        self._pool = pool
        self._victim_key = victim_key

    def enforce_idle_timeouts(self) -> int:
        if self._victim_key is not None:
            self._pool.pop(self._victim_key, None)
            self._victim_key = None
        return 1


def test_run_idle_reaper_once_snapshots_agent_pool_before_iteration(monkeypatch) -> None:
    agent_pool: dict[str, object] = {}
    agent_pool["agent-1"] = SimpleNamespace(
        _sandbox=SimpleNamespace(
            manager=SimpleNamespace(
                provider=SimpleNamespace(name="daytona_selfhost"),
                enforce_idle_timeouts=_MutatingManager(agent_pool, "agent-2").enforce_idle_timeouts,
            )
        )
    )
    agent_pool["agent-2"] = SimpleNamespace(
        _sandbox=SimpleNamespace(
            manager=SimpleNamespace(
                provider=SimpleNamespace(name="e2b"),
                enforce_idle_timeouts=lambda: 1,
            )
        )
    )
    app = SimpleNamespace(state=SimpleNamespace(agent_pool=agent_pool))

    monkeypatch.setattr(idle_reaper_module, "init_providers_and_managers", lambda: ({}, {}))

    assert idle_reaper_module.run_idle_reaper_once(app) == 2
