"""Monitor Middleware - 监控容器"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelCallResult,
    ModelRequest,
    ModelResponse,
)

from .base import BaseMonitor
from .context_monitor import ContextMonitor
from .cost import CostCalculator, fetch_openrouter_pricing, get_model_context_limit
from .runtime import AgentRuntime
from .state_monitor import StateMonitor
from .token_monitor import TokenMonitor


class MonitorMiddleware(AgentMiddleware):
    """监控中间件

    作为容器组合多个 Monitor，在 LLM 调用前后统一调度。
    提供 AgentRuntime 聚合所有监控数据。
    """

    tools = []  # 不注入工具

    def __init__(self, context_limit: int = 0, model_name: str = "", verbose: bool = False):
        self.verbose = verbose

        # 内置 monitors
        self._token_monitor = TokenMonitor()
        self._state_monitor = StateMonitor()

        # 注入成本计算器 + 从模型推导 context_limit（先拉取 OpenRouter 定价）
        if model_name:
            fetch_openrouter_pricing()
            self._token_monitor.cost_calculator = CostCalculator(model_name)
            if context_limit <= 0:
                context_limit = get_model_context_limit(model_name)

        if context_limit <= 0:
            context_limit = 128000

        self._context_monitor = ContextMonitor(context_limit=context_limit)

        # 可扩展的 monitors 列表
        self._monitors: list[BaseMonitor] = [
            self._token_monitor,
            self._context_monitor,
            self._state_monitor,
        ]

        # 聚合运行时
        self.runtime = AgentRuntime(
            token_monitor=self._token_monitor,
            context_monitor=self._context_monitor,
            state_monitor=self._state_monitor,
        )

        if verbose:
            print("[MonitorMiddleware] Initialized")

    def add_monitor(self, monitor: BaseMonitor) -> None:
        """添加自定义 Monitor"""
        self._monitors.append(monitor)

    def update_model(self, model_name: str, overrides: dict | None = None) -> None:
        """更新 cost calculator 和 context_limit（不重建 middleware）"""
        overrides = overrides or {}
        lookup_name = overrides.get("based_on") or model_name
        self._token_monitor.cost_calculator = CostCalculator(lookup_name)
        self._context_monitor.context_limit = (
            overrides.get("context_limit") or get_model_context_limit(lookup_name)
        )

    def mark_ready(self) -> None:
        """标记 Agent 就绪（初始化完成后调用）"""
        self._state_monitor.mark_ready()

    def mark_terminated(self) -> None:
        """标记 Agent 终止"""
        self._state_monitor.mark_terminated()

    def mark_error(self, error: Exception | None = None) -> None:
        """标记错误状态"""
        self._state_monitor.mark_error(error)

    def _dispatch_monitors(self, method_name: str, *args) -> None:
        """统一调度 monitors 方法"""
        for monitor in self._monitors:
            try:
                getattr(monitor, method_name)(*args)
            except Exception as e:
                if self.verbose:
                    print(f"[MonitorMiddleware] {method_name} error: {e}")

    # ========== AgentMiddleware 接口 ==========

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        """异步包装 LLM 调用，在前后调度所有 monitors"""
        req_dict = {"messages": request.messages}

        self._dispatch_monitors("on_request", req_dict)

        try:
            response = await handler(request)
        except Exception as e:
            self._state_monitor.mark_error(e)
            raise

        messages = response.result if hasattr(response, "result") else [response]
        resp_dict = {"messages": messages}

        self._dispatch_monitors("on_response", req_dict, resp_dict)

        return response

    def wrap_tool_call(self, request, handler):
        """包装工具调用（透传，不做处理）"""
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        """异步包装工具调用（透传，不做处理）"""
        return await handler(request)

    # ========== 指标访问 ==========

    def get_all_metrics(self) -> dict[str, Any]:
        """获取所有 monitors 的指标"""
        metrics = {}
        for monitor in self._monitors:
            name = monitor.__class__.__name__
            metrics[name] = monitor.get_metrics()
        return metrics

    def reset_all(self) -> None:
        """重置所有 monitors"""
        for monitor in self._monitors:
            monitor.reset()
