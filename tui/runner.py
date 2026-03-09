"""
Non-interactive runner for Leon AI CLI

Supports:
- Single message execution
- Multi-turn via stdin (messages separated by blank lines)
- Interactive mode (simple readline, no TUI)
- Debug output (tool calls, queue status, etc.)
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from config.schema import DEFAULT_MODEL


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
        self.total_tool_calls = 0
        self._start_time = None

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

        # 状态
        state_info = status.get("state", {})
        print(f"\n[STATE] {state_info.get('state', 'unknown')}")

        # Token 统计
        self._print_token_stats(status.get("tokens", {}))

        # 上下文统计
        self._print_context_stats(status.get("context", {}))

        # Memory 状态
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
        for node_name, node_update in chunk.items():
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

        # Extract tool calls
        tool_calls = getattr(msg, "tool_calls", [])
        for tc in tool_calls:
            tool_info = {
                "name": tc.get("name", "unknown"),
                "args": tc.get("args", {}),
            }
            result["tool_calls"].append(tool_info)
            self.total_tool_calls += 1

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
        # Indent multi-line output
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
                print(f"\n[QUEUE] steer={sizes['steer']}, followup={sizes['followup']}")
        except Exception:
            pass

    async def run_interactive(self) -> None:
        """Simple interactive mode (readline, no TUI)"""
        print("Leon AI Interactive Mode")
        print("Commands: /exit, /quit, /clear, /thread")
        print("-" * 40)

        while True:
            try:
                message = input("\n> ").strip()
                if not message:
                    continue

                # Handle commands
                if message.lower() in ("/exit", "/quit", "exit", "quit"):
                    break
                if message.lower() == "/clear":
                    self.turn_count = 0
                    self.total_tool_calls = 0
                    self.thread_id = f"run-{uuid.uuid4().hex[:8]}"
                    print(f"[INFO] New thread: {self.thread_id}")
                    continue
                if message.lower() == "/thread":
                    print(f"[INFO] Thread: {self.thread_id}")
                    continue

                await self.run_turn(message)

            except EOFError:
                break
            except KeyboardInterrupt:
                print("\n[INTERRUPTED]")
                break

        self._print_summary()

    async def run_stdin(self) -> None:
        """Read multiple messages from stdin (separated by blank lines)"""
        content = sys.stdin.read()
        messages = [m.strip() for m in content.split("\n\n") if m.strip()]

        if not messages:
            print("[ERROR] No messages provided via stdin")
            return

        self._debug_print(f"[INFO] Processing {len(messages)} messages from stdin")

        for msg in messages:
            await self.run_turn(msg)

        self._print_summary()

    async def run_single(self, message: str) -> None:
        """Single turn execution"""
        result = await self.run_turn(message)

        if self.json_output:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif not self.debug:
            # Non-debug mode: only output response
            if result.get("response"):
                print(result["response"])
            elif result.get("error"):
                print(f"Error: {result['error']}")

        if self.debug:
            self._print_summary()

    def _print_summary(self) -> None:
        """Print session summary"""
        if not self.debug or self.json_output:
            return

        print(f"\n{'=' * 50}")
        print("[SUMMARY]")
        print(f"  Thread: {self.thread_id}")
        print(f"  Total turns: {self.turn_count}")
        print(f"  Total tool calls: {self.total_tool_calls}")


def cmd_run(args, unknown_args: list[str]) -> None:
    """Handle 'run' command"""
    import os

    from tui.config import ConfigManager

    # Load config
    config_manager = ConfigManager()
    config_manager.load_to_env()

    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: No API key configured. Run 'leonai config' first.")
        return

    # Parse arguments
    run_config = _parse_run_args(args, unknown_args)

    if run_config is None:
        _show_run_help()
        return

    # Get workspace and thread
    workspace = Path(args.workspace) if args.workspace else Path.cwd()
    thread_id = args.thread or f"run-{uuid.uuid4().hex[:8]}"

    # Auto-detect sandbox when resuming a thread
    sandbox_arg = _detect_sandbox(args, thread_id)

    # Create agent
    agent = _create_agent(args, workspace, sandbox_arg, run_config["debug"])
    if agent is None:
        return

    # Create and run
    runner = NonInteractiveRunner(
        agent,
        thread_id,
        debug=run_config["debug"],
        json_output=run_config["json"],
    )

    try:
        if run_config["interactive"]:
            asyncio.run(runner.run_interactive())
        elif run_config["stdin"]:
            asyncio.run(runner.run_stdin())
        elif run_config["message"]:
            asyncio.run(runner.run_single(run_config["message"]))
    except KeyboardInterrupt:
        if run_config["debug"]:
            print("\n[INTERRUPTED]")
    finally:
        agent.close()


def _parse_run_args(args, unknown_args: list[str]) -> dict | None:
    """Parse run command arguments. Returns None if help should be shown."""
    message = None
    stdin_mode = False
    interactive_mode = False
    debug_mode = False
    json_mode = False

    positional_args = []
    for arg in unknown_args:
        if arg == "--stdin":
            stdin_mode = True
        elif arg in ("-i", "--interactive"):
            interactive_mode = True
        elif arg in ("-d", "--debug"):
            debug_mode = True
        elif arg == "--json":
            json_mode = True
        elif not arg.startswith("-"):
            positional_args.append(arg)

    # Message can come from multiple sources
    if args.subcommand and not args.subcommand.startswith("-"):
        message = args.subcommand
    elif args.extra_args:
        message = args.extra_args[0]
    elif positional_args:
        message = positional_args[0]

    # Validate mode combinations
    mode_count = sum([bool(message), stdin_mode, interactive_mode])
    if mode_count > 1:
        print("Error: Cannot combine MESSAGE, --stdin, and --interactive")
        print("Usage:")
        print('  leonai run "message"       Single message')
        print("  leonai run --stdin         Read from stdin")
        print("  leonai run -i              Interactive mode")
        return None

    if mode_count == 0:
        return None

    return {
        "message": message,
        "stdin": stdin_mode,
        "interactive": interactive_mode,
        "debug": debug_mode,
        "json": json_mode,
    }


def _show_run_help() -> None:
    """Show help for run command"""
    print("Usage: leonai run [OPTIONS] [MESSAGE]")
    print()
    print("Options:")
    print("  MESSAGE              Single message to send")
    print("  --stdin              Read messages from stdin (blank line separated)")
    print("  -i, --interactive    Interactive mode (simple readline)")
    print("  -d, --debug          Show debug output (tool calls, queue status)")
    print("  --json               JSON output (single message mode only)")
    print("  --workspace <dir>    Working directory")
    print("  --thread <id>        Thread ID (for multi-turn persistence)")
    print()
    print("Examples:")
    print('  leonai run "List files in current directory"')
    print('  leonai run -d "Read README.md"')
    print("  leonai run -i -d")
    print('  echo -e "List files\\n\\nRead README.md" | leonai run --stdin -d')
    print('  leonai run --thread my-test "First message"')
    print('  leonai run --thread my-test "Continue conversation"')


def _detect_sandbox(args, thread_id: str) -> str | None:
    """Auto-detect sandbox when resuming a thread"""
    sandbox_arg = getattr(args, "sandbox", None)
    if not sandbox_arg and args.thread:
        from sandbox.manager import lookup_sandbox_for_thread

        detected = lookup_sandbox_for_thread(thread_id)
        if detected:
            config_path = Path.home() / ".leon" / "sandboxes" / f"{detected}.json"
            if config_path.exists():
                return detected
    return sandbox_arg


def _create_agent(args, workspace: Path, sandbox_arg: str | None, debug: bool):
    """Create agent with error handling"""
    import os

    if debug:
        print("[DEBUG] Initializing agent...", flush=True)
        print(f"[DEBUG] Workspace: {workspace}", flush=True)
        print(f"[DEBUG] Thread: {args.thread or 'auto'}", flush=True)

    from agent import create_leon_agent

    model_name = getattr(args, "model", None) or os.getenv("MODEL_NAME") or DEFAULT_MODEL

    try:
        agent = create_leon_agent(
            model_name=model_name,
            profile=args.profile,
            workspace_root=workspace,
            sandbox=sandbox_arg,
            verbose=debug,
        )
        if debug:
            print("[DEBUG] Agent ready", flush=True)
        return agent
    except Exception as e:
        print(f"Error: Failed to initialize agent: {e}")
        return None
