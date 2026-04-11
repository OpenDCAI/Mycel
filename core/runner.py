"""
Non-interactive runner for Leon AI
"""

import asyncio
from typing import Any


class NonInteractiveRunner:
    """Non-interactive runner supporting multi-turn conversations"""

    def __init__(
        self,
        agent,
        thread_id: str,
        debug: bool = False,
        json_output: bool = False,
    ):
        self.agent = agent
        self.thread_id = thread_id
        self.debug = debug
        self.json_output = json_output
        self.turn_count = 0

    def _debug_print(self, msg: str) -> None:
        """Print debug message if debug mode is enabled"""
        if self.debug and not self.json_output:
            print(msg, flush=True)

    async def run_turn(self, message: str) -> dict:
        """Execute one turn of conversation, return result"""
        import time

        self.turn_count += 1
        result = {
            "turn": self.turn_count,
            "tool_calls": [],
            "response": "",
        }

        if self.debug and not self.json_output:
            print(f"\n{'=' * 50}")
            print(f"=== Turn {self.turn_count} ===")
            print(f"[USER] {message}")

        config = {"configurable": {"thread_id": self.thread_id}}
        t0 = time.perf_counter()

        # @@@ Set sandbox thread context and ensure session before invoke
        if hasattr(self.agent, "_sandbox"):
            from sandbox.thread_context import set_current_thread_id

            set_current_thread_id(self.thread_id)
            if self.agent._sandbox.name != "local":
                self.agent._sandbox.ensure_session(self.thread_id)

        # 状态转移：→ ACTIVE
        if hasattr(self.agent, "runtime"):
            from core.runtime.middleware.monitor import AgentState

            self.agent.runtime.transition(AgentState.ACTIVE)

        try:
            async for chunk in self.agent.agent.astream(
                {"messages": [{"role": "user", "content": message}]},
                config=config,
                stream_mode="updates",
            ):
                if not chunk:
                    continue
                self._process_chunk(chunk, result)

        except asyncio.CancelledError:
            self._debug_print("\n[INTERRUPTED]")
            result["interrupted"] = True
        except Exception as e:
            self._debug_print(f"\n[ERROR] {e}")
            result["error"] = str(e)
        finally:
            # 状态转移：→ IDLE
            if hasattr(self.agent, "runtime"):
                from core.runtime.middleware.monitor import AgentState

                if self.agent.runtime.current_state == AgentState.ACTIVE:
                    self.agent.runtime.transition(AgentState.IDLE)

        elapsed = time.perf_counter() - t0
        result["duration"] = round(elapsed, 2)

        if self.debug and not self.json_output:
            self._print_queue_status()
            self._print_runtime_state()
            print(f"\n[TURN] Duration: {elapsed:.2f}s")

        return result

    def _print_runtime_state(self) -> None:
        """Print runtime state (if available)"""
        if not self.debug or self.json_output or not hasattr(self.agent, "runtime"):
            return

        status = self.agent.runtime.get_status_dict()

        state_info = status.get("state", {})
        print(f"\n[STATE] {state_info.get('state', 'unknown')}")

        self._print_token_stats(status.get("tokens", {}))
        self._print_context_stats(status.get("context", {}))
        self._print_memory_stats(status)

    def _print_token_stats(self, tokens: dict) -> None:
        """Print token statistics"""
        if tokens.get("total_tokens", 0) == 0:
            return

        print(
            f"[TOKENS] total={tokens['total_tokens']} "
            f"(in={tokens.get('input_tokens', 0)}, "
            f"out={tokens.get('output_tokens', 0)}, "
            f"cache_r={tokens.get('cache_read_tokens', 0)}, "
            f"cache_w={tokens.get('cache_write_tokens', 0)}, "
            f"reasoning={tokens.get('reasoning_tokens', 0)})"
        )

        cost = tokens.get("cost", 0)
        if cost > 0:
            print(f"[COST] ${cost:.4f}")
        print(f"[LLM_CALLS] {tokens['call_count']}")

    def _print_context_stats(self, context: dict) -> None:
        """Print context statistics"""
        if context.get("estimated_tokens", 0) > 0:
            print(f"[CONTEXT] ~{context['estimated_tokens']} tokens ({context['usage_percent']}% of limit)")

    def _print_memory_stats(self, status: dict) -> None:
        """Print memory middleware statistics"""
        if not hasattr(self.agent, "_memory_middleware"):
            return

        mm = self.agent._memory_middleware
        parts = []

        if mm._cached_summary:
            parts.append(f"summary_cached=yes (up_to_idx={mm._compact_up_to_index})")
        else:
            parts.append("summary_cached=no")

        flags = status.get("state", {}).get("flags", {})
        if flags.get("compacting"):
            parts.append("COMPACTING")

        print(f"[MEMORY] {', '.join(parts)}")

    def _process_chunk(self, chunk: dict, result: dict) -> None:
        """Process streaming chunk, extract tool calls and response"""
        for _node_name, node_update in chunk.items():
            if not isinstance(node_update, dict):
                continue

            messages = node_update.get("messages", [])
            if not isinstance(messages, list):
                messages = [messages]

            for msg in messages:
                msg_class = msg.__class__.__name__

                if msg_class == "AIMessage":
                    self._handle_ai_message(msg, result)

                elif msg_class == "ToolMessage":
                    self._handle_tool_message(msg)

    def _handle_ai_message(self, msg: Any, result: dict) -> None:
        """Handle AIMessage - extract content and tool calls"""
        content = self._extract_text_content(msg)

        if content:
            result["response"] = content
            if self.debug and not self.json_output:
                print(f"\n[ASSISTANT]\n{content}")

        tool_calls = getattr(msg, "tool_calls", [])
        for tc in tool_calls:
            tool_info = {
                "name": tc.get("name", "unknown"),
                "args": tc.get("args", {}),
            }
            result["tool_calls"].append(tool_info)

            if self.debug and not self.json_output:
                self._print_tool_call(tool_info)

    def _extract_text_content(self, msg: Any) -> str:
        """Extract text content from AIMessage"""
        raw_content = getattr(msg, "content", "")

        if isinstance(raw_content, str):
            return raw_content

        if isinstance(raw_content, list):
            text_parts = []
            for block in raw_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            return "".join(text_parts)

        return str(raw_content)

    def _print_tool_call(self, tool_info: dict) -> None:
        """Print tool call information"""
        print(f"\n[TOOL_CALL] {tool_info['name']}")
        for k, v in tool_info["args"].items():
            v_str = str(v)
            if len(v_str) > 100:
                v_str = v_str[:100] + "..."
            print(f"  {k}: {v_str}")

    def _handle_tool_message(self, msg: Any) -> None:
        """Handle ToolMessage - show result preview"""
        if not self.debug or self.json_output:
            return

        content = str(getattr(msg, "content", ""))
        preview = content[:200] + "..." if len(content) > 200 else content
        preview = preview.replace("\n", "\n  ")
        print(f"\n[TOOL_RESULT]\n  {preview}")

    def _print_queue_status(self) -> None:
        """Print queue status (if queue middleware is available)"""
        if not self.debug or self.json_output:
            return

        try:
            qm = getattr(self.agent, "queue_manager", None)
            if qm:
                sizes = qm.queue_sizes(thread_id=self.thread_id)
                print(f"\n[QUEUE] followup={sizes['followup']}")
        except Exception:
            pass
