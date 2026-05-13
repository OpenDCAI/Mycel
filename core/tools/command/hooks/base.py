from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HookResult:
    allow: bool
    error_message: str = ""
    continue_chain: bool = True
    metadata: dict[str, Any] | None = None

    @classmethod
    def allow_command(cls, metadata: dict[str, Any] | None = None) -> "HookResult":
        return cls(allow=True, continue_chain=True, metadata=metadata)

    @classmethod
    def block_command(
        cls,
        error_message: str,
        continue_chain: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "HookResult":
        return cls(allow=False, error_message=error_message, continue_chain=continue_chain, metadata=metadata)


class BashHook(ABC):
    priority: int = 100
    name: str = "UnnamedHook"
    description: str = ""
    enabled: bool = True

    def __init__(self, workspace_root: Path | str | None = None):
        self.workspace_root = Path(workspace_root) if workspace_root else None

    @abstractmethod
    def check_command(self, command: str, context: dict[str, Any]) -> HookResult:
        pass

    def on_command_success(self, command: str, output: str, context: dict[str, Any]) -> None:
        pass

    def on_command_error(self, command: str, error: str, context: dict[str, Any]) -> None:
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, priority={self.priority}, enabled={self.enabled})>"
