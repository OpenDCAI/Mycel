"""Monitor 基类"""

from abc import ABC, abstractmethod
from typing import Any


class BaseMonitor(ABC):
    """Monitor 接口

    所有 Monitor 实现此接口，由 MonitorMiddleware 统一调度。
    """

    @abstractmethod
    def on_request(self, request: dict[str, Any]) -> None:
        """LLM 请求前调用"""
        pass

    @abstractmethod
    def on_response(self, request: dict[str, Any], response: dict[str, Any]) -> None:
        """LLM 响应后调用"""
        pass

    def get_metrics(self) -> dict[str, Any]:
        """返回当前指标，供 runtime 聚合"""
        return {}

    def reset(self) -> None:
        """重置指标"""
        pass
