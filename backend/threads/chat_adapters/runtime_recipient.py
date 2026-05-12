from __future__ import annotations

import logging
from typing import Any

from messaging.delivery.runtime_thread_selector import select_runtime_thread_for_recipient
from protocols.agent_runtime import AgentChatRecipient

from .runtime_identity import require_user, user_type

logger = logging.getLogger(__name__)


def resolve_runtime_notification_recipient(
    user_id: str,
    *,
    user_repo: Any,
    thread_repo: Any,
    activity_reader: Any,
    context: str,
    role: str = "recipient",
    runtime_context: str | None = None,
) -> AgentChatRecipient | None:
    user = require_user(user_repo, user_id, context=context, role=role)
    return select_runtime_notification_recipient(
        user_id,
        user_type(user, user_id, context=context),
        thread_repo=thread_repo,
        activity_reader=activity_reader,
        context=runtime_context or context,
    )


def select_runtime_notification_recipient(
    user_id: str,
    user_type: str,
    *,
    thread_repo: Any,
    activity_reader: Any,
    context: str,
) -> AgentChatRecipient | None:
    if user_type == "external":
        return AgentChatRecipient(agent_user_id=user_id, runtime_source="external")
    if user_type != "agent":
        return None
    return _resolve_managed_agent_runtime_recipient(
        user_id,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
        missing_runtime_message=f"Managed agent runtime is unavailable for {context} wake: {user_id}",
        skip_log_context=f"{context} wake",
    )


def resolve_runtime_chat_delivery_recipient(
    user_id: str,
    user_type: str,
    *,
    thread_repo: Any,
    activity_reader: Any,
) -> AgentChatRecipient | None:
    if user_type == "external":
        return AgentChatRecipient(agent_user_id=user_id, runtime_source="external")
    if user_type != "agent":
        raise RuntimeError(f"Chat delivery recipient type is not runtime-addressable: {user_type}")
    return _resolve_managed_agent_runtime_recipient(
        user_id,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
        missing_runtime_message=f"Managed agent runtime is unavailable for chat delivery to {user_id}",
        skip_log_context="chat wake",
    )


def _resolve_managed_agent_runtime_recipient(
    user_id: str,
    *,
    thread_repo: Any,
    activity_reader: Any,
    missing_runtime_message: str,
    skip_log_context: str,
) -> AgentChatRecipient | None:
    if activity_reader is None:
        raise RuntimeError(missing_runtime_message)
    thread_id = select_runtime_thread_for_recipient(
        user_id,
        thread_repo=thread_repo,
        activity_reader=activity_reader,
    )
    if thread_id is None:
        logger.info("Skipped %s for agent without runtime thread: %s", skip_log_context, user_id)
        return None
    return AgentChatRecipient(agent_user_id=user_id, runtime_source="mycel", thread_id=thread_id)
