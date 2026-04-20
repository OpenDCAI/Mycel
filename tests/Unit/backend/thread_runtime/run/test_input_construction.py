from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


def test_build_initial_input_prefers_explicit_input_messages() -> None:
    from backend.thread_runtime.run.input_construction import build_initial_input

    input_messages = [object()]
    initial_input, prompt_restore = asyncio.run(
        build_initial_input(
            message="hello",
            message_metadata={"source": "owner"},
            input_messages=input_messages,
            agent=SimpleNamespace(),
            app=SimpleNamespace(),
            thread_id="thread-1",
            emit=None,
            emit_queued_terminal_followups=None,
        )
    )

    assert initial_input == {"messages": input_messages}
    prompt_restore()


def test_build_initial_input_wraps_message_metadata_when_present() -> None:
    from backend.thread_runtime.run.input_construction import build_initial_input

    initial_input, _prompt_restore = asyncio.run(
        build_initial_input(
            message="hello",
            message_metadata={"source": "system", "notification_type": "agent"},
            input_messages=None,
            agent=SimpleNamespace(),
            app=SimpleNamespace(),
            thread_id="thread-1",
            emit=None,
            emit_queued_terminal_followups=None,
        )
    )

    messages = initial_input["messages"]
    assert len(messages) == 1
    assert messages[0].content == "hello"
    assert messages[0].metadata == {"source": "system", "notification_type": "agent"}


@pytest.mark.asyncio
async def test_build_initial_input_adds_terminal_followthrough_system_note_and_queued_items() -> None:
    from backend.thread_runtime.run.input_construction import build_initial_input

    queued = [
        {
            "content": "queued notification",
            "source": "system",
            "notification_type": "agent",
        }
    ]

    async def emit_queued_terminal_followups(*, app, thread_id, emit):
        assert app is not None
        assert thread_id == "thread-1"
        assert emit is not None
        return queued

    agent = SimpleNamespace(agent=SimpleNamespace(system_prompt=SimpleNamespace(content="base prompt")))
    initial_input, prompt_restore = await build_initial_input(
        message="terminal done",
        message_metadata={"source": "system", "notification_type": "command"},
        input_messages=None,
        agent=agent,
        app=SimpleNamespace(),
        thread_id="thread-1",
        emit=lambda *_args, **_kwargs: None,
        emit_queued_terminal_followups=emit_queued_terminal_followups,
    )

    messages = initial_input["messages"]
    assert [message.content for message in messages] == ["terminal done", "queued notification"]
    assert agent.agent.system_prompt.content != "base prompt"
    assert "explicit assistant followthrough" in agent.agent.system_prompt.content

    prompt_restore()
    assert agent.agent.system_prompt.content == "base prompt"
