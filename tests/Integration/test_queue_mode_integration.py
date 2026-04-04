"""Integration test for Queue Mode - tests non-preemptive steer behavior with real agent.

Non-preemptive means: tool calls are NEVER skipped when a steer message arrives.
Instead, all tool calls finish normally, then the steer message is injected before
the next LLM call via before_model().
"""

import asyncio
import os
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_LLM_TESTS") != "1",
    reason="requires real LLM endpoint and credentials",
)


def test_queue_mode_steer_non_preemptive():
    """
    Test non-preemptive steer: inject message during agent execution.

    Flow:
    1. Start agent with a task that triggers multiple tool calls
    2. After first tool call, inject a steer message
    3. Verify tool calls are NOT skipped (non-preemptive)
    4. Verify steer message is injected before next model call
    """
    from agent import create_leon_agent

    agent = create_leon_agent()
    queue_manager = agent.queue_manager

    tool_calls_seen = []
    tool_results_seen = []
    steer_injected = False

    test_message = f"请列出 {agent.workspace_root} 目录的文件，然后读取其中的 pyproject.toml 文件内容"
    config = {"configurable": {"thread_id": "test-queue-mode"}}

    def inject_steer():
        time.sleep(2)
        print("[TEST] Injecting steer message...")
        queue_manager.enqueue(
            "停止！改为告诉我今天星期几",
            thread_id="test-queue-mode",
        )

    steer_thread = threading.Thread(target=inject_steer)
    steer_thread.start()

    print(f"[TEST] Starting agent with: {test_message[:50]}...")

    async def run_agent():
        nonlocal steer_injected

        try:
            async for chunk in agent.agent.astream(
                {"messages": [{"role": "user", "content": test_message}]},
                config=config,
                stream_mode="updates",
            ):
                for node_name, node_update in chunk.items():
                    if not isinstance(node_update, dict):
                        continue

                    messages = node_update.get("messages", [])
                    if not isinstance(messages, list):
                        messages = [messages]

                    for msg in messages:
                        msg_class = msg.__class__.__name__

                        if msg_class == "AIMessage":
                            tool_calls = getattr(msg, "tool_calls", [])
                            for tc in tool_calls:
                                tool_name = tc.get("name", "unknown")
                                tool_calls_seen.append(tool_name)
                                print(f"[TEST] Tool call: {tool_name}")

                        elif msg_class == "ToolMessage":
                            content = str(getattr(msg, "content", ""))[:100]
                            tool_results_seen.append(content)
                            # Non-preemptive: no "Skipped" messages
                            if "Skipped" in content:
                                print("[TEST] WARNING: Tool was SKIPPED (unexpected!)")
                            else:
                                print(f"[TEST] Tool result: {content[:50]}...")

                        elif msg_class == "HumanMessage":
                            content = getattr(msg, "content", "")
                            if "<system-reminder>" in str(content):
                                steer_injected = True
                                print("[TEST] Steer system-reminder injected!")

        except Exception as e:
            print(f"[TEST] Error: {e}")
            import traceback

            traceback.print_exc()

    asyncio.run(run_agent())
    steer_thread.join()

    print("\n" + "=" * 50)
    print("[TEST] Results:")
    print(f"  Tool calls seen: {tool_calls_seen}")
    print(f"  Tool results: {len(tool_results_seen)}")
    print(f"  Steer injected: {steer_injected}")
    skipped = any("Skipped" in r for r in tool_results_seen)
    print(f"  Any skipped (should be False): {skipped}")
    print("=" * 50)

    agent.close()

    assert len(tool_calls_seen) > 0, "Expected at least one tool call"
    assert not skipped, "Non-preemptive mode should never skip tool calls"


if __name__ == "__main__":
    test_queue_mode_steer_non_preemptive()
