"""AgentBaySandbox — cloud sandbox via Alibaba AgentBay."""

from __future__ import annotations

import os
from pathlib import Path

from sandbox.config import SandboxConfig
from sandbox.providers.agentbay import AgentBayProvider
from sandbox.remote import RemoteSandbox


class AgentBaySandbox(RemoteSandbox):
    def __init__(self, config: SandboxConfig, db_path: Path | None = None) -> None:
        ab = config.agentbay
        api_key = ab.api_key or os.getenv("AGENTBAY_API_KEY")
        if not api_key:
            raise ValueError("AgentBay sandbox requires AGENTBAY_API_KEY")

        provider = AgentBayProvider(
            api_key=api_key,
            region_id=ab.region_id,
            default_context_path=ab.context_path,
            image_id=ab.image_id,
            provider_name=config.name,
            supports_pause=ab.supports_pause,
            supports_resume=ab.supports_resume,
        )
        super().__init__(
            provider=provider,
            config=config,
            default_cwd=ab.context_path,
            db_path=db_path,
        )
        print(f"[AgentBaySandbox] Initialized (region={ab.region_id})")

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def working_dir(self) -> str:
        return self._config.agentbay.context_path

    @property
    def env_label(self) -> str:
        return "Remote Linux sandbox (Ubuntu)"
