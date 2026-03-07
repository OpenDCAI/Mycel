"""Workspace synchronization across different sandbox providers."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sandbox.provider import ProviderCapability


class WorkspaceSync:
    """Handles workspace file synchronization between backend and sandbox."""

    def __init__(
        self,
        provider_capability: ProviderCapability,
        workspace_root: Path,
    ):
        self.provider_capability = provider_capability
        self.workspace_root = workspace_root
