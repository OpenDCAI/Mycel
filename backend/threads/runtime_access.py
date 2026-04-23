"""Fail-loud runtime accessors for threads-owned shared state."""

from __future__ import annotations

from typing import Any


def get_thread_repo(app: Any) -> Any:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    thread_repo = getattr(runtime_state, "thread_repo", None)
    if thread_repo is None:
        raise RuntimeError("threads runtime thread_repo is not configured")
    return thread_repo


def get_thread_checkpoint_store(app: Any) -> Any:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    checkpoint_store = getattr(runtime_state, "checkpoint_store", None)
    if checkpoint_store is None:
        raise RuntimeError("threads runtime checkpoint_store is not configured")
    return checkpoint_store


def get_activity_reader(app: Any) -> Any:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    activity_reader = getattr(runtime_state, "activity_reader", None)
    if activity_reader is None:
        raise RuntimeError("threads runtime activity_reader is not configured")
    return activity_reader


def get_conversation_reader(app: Any) -> Any:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    conversation_reader = getattr(runtime_state, "conversation_reader", None)
    if conversation_reader is None:
        raise RuntimeError("threads runtime conversation_reader is not configured")
    return conversation_reader


def get_agent_actor_lookup(app: Any) -> Any:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    agent_actor_lookup = getattr(runtime_state, "agent_actor_lookup", None)
    if agent_actor_lookup is None:
        raise RuntimeError("threads runtime agent_actor_lookup is not configured")
    return agent_actor_lookup


def get_agent_runtime_gateway(app: Any) -> Any:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    runtime_gateway = getattr(runtime_state, "agent_runtime_gateway", None)
    if runtime_gateway is None:
        raise RuntimeError("threads runtime agent_runtime_gateway is not configured")
    return runtime_gateway


def get_optional_typing_tracker(app: Any) -> Any | None:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    return getattr(runtime_state, "typing_tracker", None) if runtime_state is not None else None


def get_optional_messaging_service(app: Any) -> Any | None:
    runtime_state = getattr(app.state, "threads_runtime_state", None)
    return getattr(runtime_state, "messaging_service", None) if runtime_state is not None else None
