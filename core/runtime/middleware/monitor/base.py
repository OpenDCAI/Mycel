from abc import ABC, abstractmethod
from typing import Any


class BaseMonitor(ABC):
    @abstractmethod
    def on_request(self, request: dict[str, Any]) -> None: ...

    @abstractmethod
    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None: ...

    def get_metrics(self) -> dict[str, Any]:
        return {}

    def reset(self) -> None:
        pass
