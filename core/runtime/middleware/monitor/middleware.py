from collections.abc import Awaitable, Callable
from typing import Any

from core.runtime.middleware import (
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
    tools = ()

    def __init__(self, context_limit: int = 0, model_name: str = "", verbose: bool = False):
        self.verbose = verbose

        self._token_monitor = TokenMonitor()
        self._state_monitor = StateMonitor()

        if model_name:
            fetch_openrouter_pricing()
            self._token_monitor.cost_calculator = CostCalculator(model_name)
            if context_limit <= 0:
                context_limit = get_model_context_limit(model_name)

        if context_limit <= 0:
            context_limit = 128000

        self._context_monitor = ContextMonitor(context_limit=context_limit)

        self._monitors: list[BaseMonitor] = [
            self._token_monitor,
            self._context_monitor,
            self._state_monitor,
        ]

        self.runtime = AgentRuntime(
            token_monitor=self._token_monitor,
            context_monitor=self._context_monitor,
            state_monitor=self._state_monitor,
        )

        if verbose:
            print("[MonitorMiddleware] Initialized")

    def add_monitor(self, monitor: BaseMonitor) -> None:
        self._monitors.append(monitor)

    def update_model(self, model_name: str, overrides: dict | None = None) -> None:
        overrides = overrides or {}
        lookup_name = overrides.get("based_on") or model_name
        self._token_monitor.cost_calculator = CostCalculator(lookup_name)
        self._context_monitor.context_limit = overrides.get("context_limit") or get_model_context_limit(lookup_name)

    def mark_ready(self) -> None:
        self._state_monitor.mark_ready()

    def mark_terminated(self) -> None:
        self._state_monitor.mark_terminated()

    def mark_error(self, error: Exception | None = None) -> None:
        self._state_monitor.mark_error(error)

    def _dispatch_monitors(self, method_name: str, *args) -> None:
        for monitor in self._monitors:
            getattr(monitor, method_name)(*args)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        req_dict = {"messages": request.messages}

        self._dispatch_monitors("on_request", req_dict)

        try:
            response = await handler(request)
        except Exception as e:
            self._state_monitor.mark_error(e)
            raise

        if response.prepared_request is not None:
            return response

        messages = response.result if hasattr(response, "result") else [response]
        resp_dict = {"messages": messages}

        self._dispatch_monitors("on_response", req_dict, resp_dict)

        return response

    def get_all_metrics(self) -> dict[str, Any]:
        metrics = {}
        for monitor in self._monitors:
            name = monitor.__class__.__name__
            metrics[name] = monitor.get_metrics()
        return metrics

    def reset_all(self) -> None:
        for monitor in self._monitors:
            monitor.reset()
