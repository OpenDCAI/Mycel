"""Real-LLM smoke test (opt-in, NOT part of the pure suite).

Exercises the full stack against a live OpenAI-compatible endpoint: real model
-> bind_tools -> tool call -> tool execution -> usage accounting -> final answer.

Env-gated so the default ``run.py`` stays API-free. To run:

    export LLM_API_KEY=...  LLM_BASE_URL=http://host:port  LLM_MODEL=gpt-5.5
    python agent_core/tests/test_real_llm.py

Tests skip (not fail) when the env vars are absent.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from langchain_core.messages import AIMessage, ToolMessage


def _cfg() -> tuple[str | None, str | None, str]:
    return (
        os.environ.get("LLM_API_KEY"),
        os.environ.get("LLM_BASE_URL"),
        os.environ.get("LLM_MODEL", "gpt-5.5"),
    )


def _model():
    from agent_core.models import OpenAIChatModel

    key, base, model = _cfg()
    return OpenAIChatModel(model, api_key=key, base_url=base)


def test_real_no_tool_completion():
    key, base, _ = _cfg()
    if not (key and base):
        print("SKIP test_real_no_tool_completion (LLM_API_KEY/LLM_BASE_URL unset)")
        return

    async def run():
        from agent_core import Agent, UsageMeter
        from agent_core.registry import ToolRegistry

        agent = Agent(
            model=_model(),
            registry=ToolRegistry(),
            system_prompt="You are terse. Answer in one short sentence.",
            usage_meter=UsageMeter(),
            max_turns=3,
        )
        result = await agent.ainvoke("In one word, what color is a clear daytime sky?")
        assert result["reason"] == "completed"
        assert isinstance(result["messages"][-1], AIMessage)
        assert agent.usage.total_tokens > 0
        print(f"   -> reply={result['messages'][-1].content!r} tokens={agent.usage.total_tokens}")

    asyncio.run(run())


def test_real_agent_tool_use():
    key, base, _ = _cfg()
    if not (key and base):
        print("SKIP test_real_agent_tool_use (LLM_API_KEY/LLM_BASE_URL unset)")
        return

    async def run():
        from agent_core import Agent, UsageMeter
        from agent_core.builtins import default_toolset

        with tempfile.TemporaryDirectory() as tmp:
            agent = Agent(
                model=_model(),
                tools=default_toolset(tmp),
                workspace_root=tmp,
                system_prompt="You are a terse assistant. Use the provided tools to do what is asked.",
                usage_meter=UsageMeter(),
                max_turns=6,
            )
            result = await agent.ainvoke(
                "Use the run_bash tool to run exactly: echo agentcore-live-ok . "
                "Then tell me the exact text it printed."
            )
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert tool_msgs, "model never called a tool"
            assert any("agentcore-live-ok" in m.content for m in tool_msgs), "marker missing from tool output"
            assert result["reason"] == "completed"
            assert agent.usage.total_tokens > 0
            final = result["messages"][-1]
            assert isinstance(final, AIMessage) and "agentcore-live-ok" in final.content
            print(f"   -> turns={agent.usage.turns} tokens={agent.usage.total_tokens} final={final.content[:80]!r}")

    asyncio.run(run())


if __name__ == "__main__":
    import traceback

    passed = failed = 0
    for name in ("test_real_no_tool_completion", "test_real_agent_tool_use"):
        try:
            print(f"\n=== {name} ===")
            globals()[name]()
            print(f"PASS  {name}")
            passed += 1
        except Exception:
            print(f"FAIL  {name}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
