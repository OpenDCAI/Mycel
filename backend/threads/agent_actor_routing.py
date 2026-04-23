"""Threads-owned routing helpers from agent-actor identity to canonical thread."""

from __future__ import annotations


def select_runtime_thread_for_recipient(
    recipient_user_id: str,
    *,
    thread_repo,
) -> str | None:
    thread = thread_repo.get_canonical_thread_for_agent_actor(recipient_user_id)
    if thread is not None:
        # @@@chat-routing-default-main-thread - chat operates on agent identity,
        # not thread identity. When no thread is explicitly targeted, route to
        # the agent's canonical/main thread only.
        return str(thread["id"])
    return None
