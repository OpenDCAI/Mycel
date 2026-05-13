from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, overload

from backend.threads.chat_adapters.port import get_agent_runtime_gateway
from backend.threads.chat_adapters.runtime_notification_action import RuntimeNotificationAction, plan_runtime_notification_envelope
from backend.threads.chat_adapters.runtime_sync_event_hook import make_blocking_runtime_event_hook
from backend.threads.chat_adapters.runtime_thread_input_action import RuntimeThreadInputAction, plan_runtime_thread_input_envelope
from protocols.agent_runtime import (
    AgentRuntimeNotificationEnvelope,
    AgentRuntimeNotificationResult,
    AgentThreadInputEnvelope,
    AgentThreadInputResult,
)

RuntimeAction = RuntimeNotificationAction | RuntimeThreadInputAction
RuntimeActionEnvelope = AgentRuntimeNotificationEnvelope | AgentThreadInputEnvelope
RuntimeActionResult = AgentRuntimeNotificationResult | AgentThreadInputResult


def make_runtime_action_event_hook[EventT](
    app: Any,
    planner: Callable[[EventT], Iterable[RuntimeAction]],
    *,
    user_repo: Any,
    thread_repo: Any,
    activity_reader: Any,
) -> Callable[[EventT], None]:
    async def dispatch_event(event: EventT) -> int:
        return await dispatch_runtime_actions(
            app,
            planner(event),
            user_repo=user_repo,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )

    return make_blocking_runtime_event_hook(dispatch_event)


async def dispatch_runtime_actions(
    app: Any,
    actions: Iterable[RuntimeAction],
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> int:
    gateway = None
    dispatched_count = 0
    for action in actions:
        envelope = plan_runtime_action_envelope(
            action,
            user_repo=user_repo,
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )
        if envelope is None:
            continue
        if gateway is None:
            gateway = get_agent_runtime_gateway(app)
        await dispatch_runtime_action_envelope(gateway, envelope)
        dispatched_count += 1
    return dispatched_count


@overload
async def dispatch_runtime_action(
    app: Any,
    action: RuntimeThreadInputAction,
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> AgentThreadInputResult: ...


@overload
async def dispatch_runtime_action(
    app: Any,
    action: RuntimeNotificationAction,
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> AgentRuntimeNotificationResult | None: ...


async def dispatch_runtime_action(
    app: Any,
    action: RuntimeAction,
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> RuntimeActionResult | None:
    envelope = plan_runtime_action_envelope(
        action,
        user_repo=user_repo,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )
    if envelope is None:
        return None
    return await dispatch_runtime_action_envelope(get_agent_runtime_gateway(app), envelope)


@overload
def plan_runtime_action_envelope(
    action: RuntimeThreadInputAction,
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> AgentThreadInputEnvelope: ...


@overload
def plan_runtime_action_envelope(
    action: RuntimeNotificationAction,
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> AgentRuntimeNotificationEnvelope | None: ...


def plan_runtime_action_envelope(
    action: RuntimeAction,
    *,
    user_repo: Any = None,
    thread_repo: Any = None,
    activity_reader: Any = None,
) -> RuntimeActionEnvelope | None:
    # @@@runtime-action-boundary - actions plan backend context into runtime envelopes; gateways only dispatch envelopes.
    if isinstance(action, RuntimeNotificationAction):
        return plan_runtime_notification_envelope(
            action,
            user_repo=_required_dependency(user_repo, "user_repo", action),
            thread_repo=thread_repo,
            activity_reader=activity_reader,
        )
    if isinstance(action, RuntimeThreadInputAction):
        return plan_runtime_thread_input_envelope(action)
    raise TypeError(f"Unsupported runtime action: {type(action).__name__}")


async def dispatch_runtime_action_envelope(gateway: Any, envelope: RuntimeActionEnvelope) -> RuntimeActionResult:
    if isinstance(envelope, AgentRuntimeNotificationEnvelope):
        return await gateway.dispatch_notification(envelope)
    if isinstance(envelope, AgentThreadInputEnvelope):
        return await gateway.dispatch_thread_input(envelope)
    raise TypeError(f"Unsupported runtime action envelope: {type(envelope).__name__}")


def _required_dependency(value: Any, name: str, action: RuntimeNotificationAction) -> Any:
    if value is None:
        raise RuntimeError(f"{action.context} needs {name} to plan runtime notification action")
    return value
