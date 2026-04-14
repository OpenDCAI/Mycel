"""AgentService - Registers Agent/TaskOutput/TaskStop tools into ToolRegistry.

Creates independent LeonAgent instances per spawn. Sub-agents run as asyncio
tasks; parent blocks until completion by default. `run_in_background=True`
fires-and-forgets and returns a task_id for polling via TaskOutput.
Backed by AgentRegistry (SQLite).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from config.loader import AgentLoader
from core.agents.registry import AgentEntry, AgentRegistry
from core.runtime.middleware.queue.formatters import (
    format_agent_message,
    format_background_notification,
    format_progress_notification,
)
from core.runtime.permissions import ToolPermissionContext
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema
from core.runtime.state import BootstrapConfig, ToolUseContext
from core.runtime.tool_result import tool_error, tool_permission_request, tool_success

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.runtime.agent import LeonAgent


EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]
ChildAgentFactory = Callable[..., "LeonAgent"]


def _resolve_default_child_agent_factory() -> ChildAgentFactory:
    from core.runtime.agent import create_leon_agent

    return cast(ChildAgentFactory, create_leon_agent)


# ── Sub-agent tool filtering (CC alignment) ──────────────────────────────────
# Tools that sub-agents must never access (prevents controlling parent).
AGENT_DISALLOWED: set[str] = {"TaskOutput", "TaskStop", "Agent"}

# Per-type allowed tool sets. Tools not in the set are blocked.
EXPLORE_ALLOWED: set[str] = {"Read", "Grep", "Glob", "list_dir", "WebSearch", "WebFetch", "tool_search"}
PLAN_ALLOWED: set[str] = EXPLORE_ALLOWED  # plan agents are also read-only
BASH_ALLOWED: set[str] = {"Bash", "Read", "Grep", "Glob", "list_dir", "tool_search"}


def _get_tool_filters(subagent_type: str) -> tuple[set[str], set[str] | None]:
    """Return (extra_blocked_tools, allowed_tools) for a sub-agent type.

    For explore/plan/bash: use allowed_tools whitelist (ToolRegistry skips unmatched).
    For general: only block AGENT_DISALLOWED, no whitelist.
    """
    agent_type = subagent_type.lower()
    allowed_map: dict[str, set[str]] = {
        "explore": EXPLORE_ALLOWED,
        "plan": PLAN_ALLOWED,
        "bash": BASH_ALLOWED,
    }

    if agent_type in allowed_map:
        return AGENT_DISALLOWED, allowed_map[agent_type]

    # general: only block parent-controlling tools, no whitelist
    return AGENT_DISALLOWED, None


def _get_subagent_agent_name(subagent_type: str) -> str:
    return subagent_type.lower()


def _resolve_subagent_model(
    workspace_root: Path,
    subagent_type: str,
    requested_model: str | None,
    inherited_model: str,
    service_default_model: str | None = None,
) -> str:
    def _is_inherit_marker(value: str | None) -> bool:
        return value is None or value.lower() in {"default", "inherit"}

    env_model = os.getenv("CLAUDE_CODE_SUBAGENT_MODEL")
    if env_model:
        return env_model
    if requested_model and not _is_inherit_marker(requested_model):
        return requested_model

    agent_def = AgentLoader(workspace_root=workspace_root).load_runtime_agents().get(_get_subagent_agent_name(subagent_type))
    if agent_def and agent_def.model:
        return agent_def.model

    if inherited_model and not _is_inherit_marker(inherited_model):
        return inherited_model
    if service_default_model and not _is_inherit_marker(service_default_model):
        return service_default_model
    return inherited_model


def _normalize_child_workspace_prompt(prompt: str, workspace_root: Path) -> str:
    workspace_text = str(workspace_root)
    for suffix in ("current working directory", "working directory"):
        prompt = prompt.replace(f"{workspace_text}/{suffix}", workspace_text)
    return prompt


def _filter_fork_messages(messages: list) -> list:
    """Filter parent messages for forkContext sub-agent spawning.

    Equivalent to CC's yF0: removes assistant messages whose tool_use blocks
    have no matching tool_result in a subsequent user message (orphan tool_use).
    Orphan tool_use blocks cause Anthropic API validation errors.
    """
    # Collect all tool_use_ids that have a corresponding tool_result
    answered: set[str] = set()
    for msg in messages:
        # ToolMessage or user message with tool_result content
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id:
            answered.add(tool_call_id)
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tid = block.get("tool_use_id") or block.get("tool_call_id")
                    if tid:
                        answered.add(tid)

    result = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            if tool_uses and any(b.get("id") not in answered for b in tool_uses):
                continue  # skip assistant message with unanswered tool_use
        result.append(msg)
    return result


AGENT_SCHEMA = make_tool_schema(
    name="Agent",
    description=(
        "Launch a sub-agent for independent task execution. "
        "Types: explore (read-only codebase search), plan (architecture design, read-only), "
        "bash (shell commands only), general (broad tool access except Agent, TaskOutput, and TaskStop). "
        "Use for: multi-step tasks, parallel work, tasks needing isolation. "
        "Do NOT use for simple file reads or single grep searches — use the tools directly."
    ),
    properties={
        "subagent_type": {
            "type": "string",
            "enum": ["explore", "plan", "general", "bash"],
            "description": "Type of agent to spawn. Omit for general-purpose.",
        },
        "prompt": {
            "type": "string",
            "description": "Task for the agent",
        },
        "name": {
            "type": "string",
            "description": "Optional display name for the spawned agent",
        },
        "description": {
            "type": "string",
            "description": (
                "Short description of what agent will do. Required when run_in_background is true; shown in the background task indicator."
            ),
        },
        "run_in_background": {
            "type": "boolean",
            "default": False,
            "description": "Fire-and-forget: return immediately with task_id instead of waiting for completion",
        },
        "model": {
            "type": "string",
            "description": "Optional sub-agent model override. Priority: env > this field > agent frontmatter > inherit.",
        },
        "max_turns": {
            "type": "integer",
            "description": "Maximum turns the agent can take",
        },
        "fork_context": {
            "type": "boolean",
            "default": False,
            "description": (
                "Inherit parent conversation history as read-only context. "
                "Use when the sub-agent needs background from the parent's work. "
                "Adds a ### ENTERING SUB-AGENT ROUTINE ### marker so the sub-agent "
                "knows which messages are context vs its actual task."
            ),
        },
    },
    required=["prompt", "description"],
)

TASK_OUTPUT_SCHEMA = make_tool_schema(
    name="TaskOutput",
    description=(
        "Get output of a background task (agent or bash). Blocks until task completes by default. Returns full text output or error."
    ),
    properties={
        "task_id": {
            "type": "string",
            "description": "The task ID returned when starting a background agent",
        },
        "block": {
            "type": "boolean",
            "default": True,
            "description": "Whether to wait for completion. Use false for a non-blocking status check.",
        },
        "timeout": {
            "type": "integer",
            "default": 30000,
            "minimum": 0,
            "maximum": 600000,
            "description": "Maximum wait time in milliseconds when block=true (default: 30000, max: 600000).",
        },
    },
    required=["task_id"],
)

TASK_STOP_SCHEMA = make_tool_schema(
    name="TaskStop",
    description="Cancel a running background task. Sends cancellation signal; task may take a moment to stop.",
    properties={
        "task_id": {
            "type": "string",
            "description": "The task ID to stop",
        },
    },
    required=["task_id"],
)

SEND_MESSAGE_SCHEMA = make_tool_schema(
    name="SendMessage",
    description="Send a queued message to another running agent by name. Delivered before that agent's next model turn.",
    properties={
        "target_name": {
            "type": "string",
            "description": "Display name of the running target agent",
        },
        "message": {
            "type": "string",
            "description": "Message body to deliver",
        },
        "sender_name": {
            "type": "string",
            "description": "Optional sender label for the delivered message",
        },
    },
    required=["target_name", "message"],
)

ASK_USER_QUESTION_SCHEMA = make_tool_schema(
    name="AskUserQuestion",
    description=(
        "Ask the user one or more structured questions when progress requires their choice or clarification. "
        "Use for genuine ambiguity, preference selection, or approval that needs an explicit answer before continuing."
    ),
    properties={
        "questions": {
            "type": "array",
            "description": "Questions to present to the user.",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "header": {"type": "string", "description": "Short UI label for the question."},
                    "question": {"type": "string", "description": "Full question text shown to the user."},
                    "multiSelect": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether the user may pick multiple options.",
                    },
                    "options": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "description": {"type": "string"},
                                "preview": {"type": "string"},
                            },
                            "required": ["label", "description"],
                        },
                    },
                },
                "required": ["header", "question", "options"],
            },
        },
        "annotations": {
            "type": "object",
            "description": "Optional structured annotations kept with the question request.",
        },
        "metadata": {
            "type": "object",
            "description": "Optional metadata describing the source of the question request.",
        },
    },
    required=["questions"],
)


class _RunningTask:
    """Tracks a background asyncio.Task (agent run) with its metadata."""

    def __init__(self, task: asyncio.Task, agent_id: str, thread_id: str, description: str = ""):
        self.task = task
        self.agent_id = agent_id
        self.thread_id = thread_id
        self.description = description

    @property
    def is_done(self) -> bool:
        return self.task.done()

    def get_result(self) -> str | None:
        if not self.task.done():
            return None
        exc = self.task.exception()
        if exc:
            return f"<tool_use_error>{exc}</tool_use_error>"
        return self.task.result()


class _BashBackgroundRun:
    """Wraps AsyncCommand to provide the same is_done/get_result interface as _RunningTask."""

    def __init__(self, async_cmd: Any, command: str, description: str = ""):
        self._cmd = async_cmd
        self.command = command
        self.description = description

    @property
    def is_done(self) -> bool:
        return bool(self._cmd.done)

    def get_result(self) -> str | None:
        if not self._cmd.done:
            return None
        stdout = "".join(self._cmd.stdout_buffer)
        stderr = "".join(self._cmd.stderr_buffer)
        exit_code = self._cmd.exit_code
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        if exit_code is not None and exit_code != 0:
            parts.append(f"[exit_code: {exit_code}]")
        return "\n".join(parts) if parts else "(completed with no output)"


# Type alias for the shared background run registry
BackgroundRun = _RunningTask | _BashBackgroundRun


def _background_run_cancelled(running: BackgroundRun) -> bool:
    return isinstance(running, _BashBackgroundRun) and bool(getattr(running._cmd, "cancelled", False))


async def request_background_run_stop(running: BackgroundRun) -> None:
    """Stop a background run and mark bash runs with authoritative cancellation state."""
    if isinstance(running, _RunningTask):
        running.task.cancel()
        return

    cmd = running._cmd
    if getattr(cmd, "done", False):
        cmd.cancelled = True
        return

    cmd.cancelled = True
    process = getattr(cmd, "process", None)
    wait = getattr(process, "wait", None) if process is not None else None
    terminate = getattr(process, "terminate", None) if process is not None else None
    kill = getattr(process, "kill", None) if process is not None else None

    if callable(terminate):
        terminate()
    if callable(wait):
        wait_fn = cast(Callable[[], Awaitable[Any]], wait)
        try:
            await asyncio.wait_for(wait_fn(), timeout=1.0)
        except TimeoutError:
            if callable(kill):
                kill()
            await wait_fn()

    if getattr(cmd, "exit_code", None) is None and process is not None:
        cmd.exit_code = getattr(process, "returncode", None)
    cmd.done = True


def _background_run_running_message(running: BackgroundRun) -> str:
    return "Command is still running." if isinstance(running, _BashBackgroundRun) else "Agent is still running."


def _background_run_result(running: BackgroundRun) -> str | None:
    result = running.get_result()
    if not _background_run_cancelled(running):
        return result

    cmd = getattr(running, "_cmd", None)
    stdout = "".join(getattr(cmd, "stdout_buffer", []) or [])
    if stdout:
        # @@@cancelled-run-result-honesty - cancelled bash runs may have partial
        # stdout, but they must still surface cancellation explicitly instead of
        # looking like a clean completion.
        return f"{stdout}\n[stderr]\nCommand cancelled"
    return "Command cancelled"


def _background_run_result_status(running: BackgroundRun, result: str | None) -> str:
    if _background_run_cancelled(running):
        return "cancelled"
    return "error" if (result and result.startswith("<tool_use_error>")) else "completed"


async def _wait_for_background_run(running: BackgroundRun, timeout_ms: int) -> bool:
    timeout_s = max(timeout_ms, 0) / 1000.0
    if isinstance(running, _RunningTask):
        try:
            await asyncio.wait_for(asyncio.shield(running.task), timeout=timeout_s)
            return True
        except TimeoutError:
            return running.is_done

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        if running.is_done:
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(0.1)


class AgentService:
    """Registers Agent, TaskOutput, TaskStop tools into ToolRegistry.

    Creates independent LeonAgent instances for each spawn. By default the
    parent blocks until the sub-agent completes (blocking tool call that does
    NOT block the frontend event loop). Set run_in_background=True for true
    fire-and-forget behaviour.

    The shared_runs dict (optional) allows CommandService to register bash
    background runs so that TaskOutput/TaskStop can retrieve them too.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        agent_registry: AgentRegistry,
        workspace_root: Path,
        model_name: str,
        queue_manager: Any | None = None,
        shared_runs: dict[str, BackgroundRun] | None = None,
        background_progress_interval_s: float = 30.0,
        thread_repo: Any = None,
        user_repo: Any = None,
        web_app: Any = None,
        child_agent_factory: ChildAgentFactory | None = None,
    ):
        self._agent_registry = agent_registry
        self._workspace_root = workspace_root
        self._model_name = model_name
        self._queue_manager = queue_manager
        self._background_progress_interval_s = background_progress_interval_s
        self._thread_repo = thread_repo
        self._user_repo = user_repo
        self._web_app = web_app
        self._child_agent_factory = child_agent_factory or _resolve_default_child_agent_factory()
        self._parent_bootstrap: BootstrapConfig | None = None
        self._parent_tool_context: Any | None = None
        # Shared with CommandService so TaskOutput covers both bash and agent runs.
        self._tasks: dict[str, BackgroundRun] = shared_runs if shared_runs is not None else {}

        tool_registry.register(
            ToolEntry(
                name="Agent",
                mode=ToolMode.INLINE,
                schema=AGENT_SCHEMA,
                handler=self._handle_agent,
                source="AgentService",
                search_hint="launch sub-agent spawn parallel task independent",
            )
        )
        tool_registry.register(
            ToolEntry(
                name="TaskOutput",
                mode=ToolMode.INLINE,
                schema=TASK_OUTPUT_SCHEMA,
                handler=self._handle_task_output,
                source="AgentService",
                search_hint="get background task output result poll",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )
        tool_registry.register(
            ToolEntry(
                name="TaskStop",
                mode=ToolMode.INLINE,
                schema=TASK_STOP_SCHEMA,
                handler=self._handle_task_stop,
                source="AgentService",
                search_hint="stop cancel background task agent",
            )
        )
        tool_registry.register(
            ToolEntry(
                name="SendMessage",
                mode=ToolMode.INLINE,
                schema=SEND_MESSAGE_SCHEMA,
                handler=self._handle_send_message,
                source="AgentService",
                search_hint="send message running agent delivery queue",
            )
        )
        tool_registry.register(
            ToolEntry(
                name="AskUserQuestion",
                mode=ToolMode.INLINE,
                schema=ASK_USER_QUESTION_SCHEMA,
                handler=self._handle_ask_user_question,
                source="AgentService",
                search_hint="ask user question clarification choice preference",
                is_read_only=True,
                is_concurrency_safe=True,
            )
        )

    @staticmethod
    def _normalize_child_sandbox(sandbox_type: str | None) -> str | None:
        return None if not sandbox_type or sandbox_type == "local" else sandbox_type

    def _ensure_subagent_thread_metadata(
        self,
        *,
        thread_id: str,
        parent_thread_id: str | None,
        agent_name: str,
        model_name: str,
    ) -> None:
        if self._thread_repo is None or self._user_repo is None or not parent_thread_id:
            return
        existing_thread = self._thread_repo.get_by_id(thread_id)
        if existing_thread is not None:
            return

        parent_thread = self._thread_repo.get_by_id(parent_thread_id)
        if parent_thread is None:
            return

        agent_user_id = parent_thread.get("agent_user_id")
        if not agent_user_id:
            return
        agent_user = self._user_repo.get_by_id(agent_user_id)
        if agent_user is None:
            return

        created_at = time.time()
        branch_index = self._thread_repo.get_next_branch_index(agent_user_id)
        sandbox_type = parent_thread.get("sandbox_type") or "local"
        cwd = parent_thread.get("cwd")
        self._thread_repo.create(
            thread_id=thread_id,
            agent_user_id=agent_user_id,
            sandbox_type=sandbox_type,
            cwd=cwd,
            created_at=created_at,
            model=model_name or parent_thread.get("model"),
            is_main=False,
            branch_index=branch_index,
            owner_user_id=str(parent_thread.get("owner_user_id") or ""),
            current_workspace_id=parent_thread.get("current_workspace_id"),
        )

    async def _handle_agent(
        self,
        prompt: str,
        subagent_type: str = "General",
        name: str | None = None,
        description: str | None = None,
        run_in_background: bool = False,
        model: str | None = None,
        max_turns: int | None = None,
        fork_context: bool = False,
        tool_context: ToolUseContext | None = None,
    ) -> Any:
        """Spawn an independent LeonAgent and run it with the given prompt."""
        from sandbox.thread_context import get_current_thread_id

        task_id = uuid.uuid4().hex[:8]
        agent_name = name or f"agent-{task_id}"
        parent_thread_id = get_current_thread_id()
        existing_child = None
        lookup_existing_child = getattr(self._agent_registry, "get_latest_by_name_and_parent", None)
        if name and parent_thread_id and lookup_existing_child is not None:
            existing_child = await lookup_existing_child(name, parent_thread_id)
        thread_id = existing_child.thread_id if existing_child is not None and existing_child.status != "running" else f"subagent-{task_id}"

        # Register in AgentRegistry immediately
        entry = AgentEntry(
            agent_id=task_id,
            name=agent_name,
            thread_id=thread_id,
            status="running",
            parent_agent_id=parent_thread_id,
            subagent_type=subagent_type,
        )
        await self._agent_registry.register(entry)
        self._ensure_subagent_thread_metadata(
            thread_id=thread_id,
            parent_thread_id=parent_thread_id,
            agent_name=agent_name,
            model_name=model or self._model_name,
        )

        # Create async task (independent LeonAgent runs inside)
        task = asyncio.create_task(
            self._run_agent(
                task_id,
                agent_name,
                thread_id,
                prompt,
                subagent_type,
                max_turns,
                model=model,
                description=description or "",
                run_in_background=run_in_background,
                fork_context=fork_context,
                parent_tool_context=tool_context,
            )
        )
        if run_in_background:
            # True fire-and-forget: track in self._tasks for TaskOutput/TaskStop
            running = _RunningTask(task=task, agent_id=task_id, thread_id=thread_id, description=description or "")
            self._tasks[task_id] = running
            return tool_success(
                json.dumps(
                    {
                        "task_id": task_id,
                        "agent_name": agent_name,
                        "thread_id": thread_id,
                        "status": "running",
                        "message": "Agent started in background. Use TaskOutput to get result.",
                    },
                    ensure_ascii=False,
                ),
                metadata={
                    "task_id": task_id,
                    "subagent_thread_id": thread_id,
                    "description": description or agent_name,
                },
            )

        # Default: parent blocks until sub-agent completes (does not block frontend event loop)
        try:
            result = await task
            await self._agent_registry.update_status(task_id, "completed")
            return tool_success(
                result,
                metadata={
                    "task_id": task_id,
                    "subagent_thread_id": thread_id,
                    "description": description or agent_name,
                },
            )
        except Exception as e:
            await self._agent_registry.update_status(task_id, "error")
            return tool_error(
                f"<tool_use_error>Agent failed: {e}</tool_use_error>",
                metadata={
                    "task_id": task_id,
                    "subagent_thread_id": thread_id,
                    "description": description or agent_name,
                },
            )

    async def _run_agent(
        self,
        task_id: str,
        agent_name: str,
        thread_id: str,
        prompt: str,
        subagent_type: str,
        max_turns: int | None,
        model: str | None = None,
        description: str = "",
        run_in_background: bool = False,
        fork_context: bool = False,
        parent_tool_context: ToolUseContext | None = None,
    ) -> str:
        """Create and run an independent LeonAgent, collect its text output."""
        # Isolate this sub-agent from the parent's LangChain callback chain.
        # asyncio.create_task() copies the current context, so this task inherits
        # var_child_runnable_config which carries the parent graph's inheritable
        # callbacks (including StreamMessagesHandler for stream_mode="messages").
        # Without isolation, the sub-agent's LLM calls would write tokens directly
        # into the parent's "messages" stream. We clear it here so the sub-agent
        # starts a fresh, independent callback context.
        from langchain_core.runnables.config import var_child_runnable_config

        var_child_runnable_config.set(None)

        from sandbox.thread_context import get_current_thread_id, set_current_thread_id

        parent_thread_id = get_current_thread_id()
        self._ensure_subagent_thread_metadata(
            thread_id=thread_id,
            parent_thread_id=parent_thread_id,
            agent_name=agent_name,
            model_name=model or self._model_name,
        )

        # emit_fn is set if EventBus is available; used for task lifecycle SSE events
        emit_fn: EventEmitter | None = None
        try:
            from backend.web.event_bus import get_event_bus

            if parent_thread_id:
                event_bus = get_event_bus()
                emit_fn = event_bus.make_emitter(
                    thread_id=parent_thread_id,
                    agent_id=task_id,
                    agent_name=agent_name,
                )
        except ImportError:
            pass  # backend not available in standalone core usage

        agent: LeonAgent | None = None
        progress_task: asyncio.Task | None = None
        progress_stop: asyncio.Event | None = None
        child_bootstrap_start_cost = 0.0
        child_bootstrap_start_tool_duration_ms = 0
        try:
            # Sub-agent context trimming: each spawn creates a fresh LeonAgent
            # with its own _build_system_prompt(). No CLAUDE.md content or
            # gitStatus is injected into the prompt pipeline (core/runtime/prompts
            # has no such injection). Therefore explore/plan/bash sub-agents
            # already run lightweight — no extra trimming is needed.
            #
            # Try to use context fork from parent agent's BootstrapConfig.
            # Falls back to create_leon_agent when bootstrap is not available.
            # Compute tool filtering for this sub-agent type
            extra_blocked, allowed = _get_tool_filters(subagent_type)
            agent_name_for_role = _get_subagent_agent_name(subagent_type)

            try:
                from core.runtime.fork import create_subagent_context
                from core.runtime.fork import fork_context as fork_bootstrap

                # Parent bootstrap is stored on the ToolUseContext or agent instance.
                # AgentService stores workspace_root and model_name directly; use those
                # to check if a richer bootstrap is available via a shared reference.
                # _parent_bootstrap is injected by LeonAgent when building AgentService.
                parent_bootstrap = getattr(self, "_parent_bootstrap", None)
                child_tool_context = None
                if parent_tool_context is not None:
                    child_tool_context = create_subagent_context(parent_tool_context)
                    child_bootstrap = child_tool_context.bootstrap
                elif parent_bootstrap is not None:
                    child_bootstrap = fork_bootstrap(parent_bootstrap)
                    selected_model = _resolve_subagent_model(
                        self._workspace_root,
                        subagent_type,
                        model,
                        child_bootstrap.model_name,
                        self._model_name,
                    )
                    agent = self._child_agent_factory(
                        model_name=selected_model,
                        workspace_root=child_bootstrap.workspace_root,
                        sandbox=self._normalize_child_sandbox(getattr(child_bootstrap, "sandbox_type", None)),
                        agent=agent_name_for_role,
                        web_app=self._web_app,
                        extra_blocked_tools=extra_blocked,
                        allowed_tools=allowed,
                        verbose=False,
                    )
                else:
                    raise AttributeError("no parent bootstrap")
                child_bootstrap_start_cost = float(getattr(child_bootstrap, "total_cost_usd", 0.0))
                child_bootstrap_start_tool_duration_ms = int(getattr(child_bootstrap, "total_tool_duration_ms", 0))
                if parent_tool_context is not None:
                    # @@@sa-05-subagent-policy-resolution
                    # Role-specific tool envelopes and model priority order must
                    # be resolved explicitly here instead of leaking through
                    # prompt text or whichever defaults happen to win later.
                    selected_model = _resolve_subagent_model(
                        self._workspace_root,
                        subagent_type,
                        model,
                        child_bootstrap.model_name,
                        self._model_name,
                    )
                    agent = self._child_agent_factory(
                        model_name=selected_model,
                        workspace_root=child_bootstrap.workspace_root,
                        sandbox=self._normalize_child_sandbox(getattr(child_bootstrap, "sandbox_type", None)),
                        agent=agent_name_for_role,
                        web_app=self._web_app,
                        extra_blocked_tools=extra_blocked,
                        allowed_tools=allowed,
                        verbose=False,
                    )
                # @@@sa-04-child-bootstrap-wiring
                # Keep the forked bootstrap/context handoff behind an explicit
                # LeonAgent API so AgentService stops reaching into QueryLoop
                # internals directly.
                assert agent is not None
                agent.apply_forked_child_context(
                    child_bootstrap,
                    tool_context=child_tool_context,
                )
            except (AttributeError, ImportError):
                inherited_model = getattr(parent_tool_context.bootstrap, "model_name", None) if parent_tool_context else None
                selected_model = _resolve_subagent_model(
                    self._workspace_root,
                    subagent_type,
                    model,
                    inherited_model or self._model_name,
                    self._model_name,
                )
                agent = self._child_agent_factory(
                    model_name=selected_model,
                    workspace_root=self._workspace_root,
                    sandbox=self._normalize_child_sandbox(
                        getattr(parent_tool_context.bootstrap, "sandbox_type", None) if parent_tool_context else None
                    ),
                    agent=agent_name_for_role,
                    web_app=self._web_app,
                    extra_blocked_tools=extra_blocked,
                    allowed_tools=allowed,
                    verbose=False,
                )
            # In async context LeonAgent defers checkpointer init; call ainit() to
            # ensure state is persisted (and loadable via GET /api/threads/{thread_id}).
            assert agent is not None
            await agent.ainit()
            # @@@subagent-prompt-path-sanitize - Parent models sometimes satisfy
            # "use absolute paths" by appending natural-language cwd labels onto the
            # real workspace path. Normalize the obvious fake suffix before dispatch.
            child_workspace_root = Path(getattr(agent, "workspace_root", self._workspace_root))
            prompt = _normalize_child_workspace_prompt(prompt, child_workspace_root)

            if parent_thread_id and parent_thread_id != thread_id:
                from sandbox.manager import bind_thread_to_existing_thread_lease

                bind_thread_to_existing_thread_lease(thread_id, parent_thread_id)

            # Wire child agent events to the parent's EventBus subscription
            # so the parent SSE stream shows sub-agent activity.
            if emit_fn is not None:
                runtime = getattr(agent, "runtime", None)
                if runtime is not None and hasattr(runtime, "bind_thread"):
                    runtime.bind_thread(activity_sink=emit_fn)

            set_current_thread_id(thread_id)

            # Notify frontend: task started
            if emit_fn is not None:
                emission = emit_fn(
                    {
                        "event": "task_start",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "thread_id": thread_id,
                                "background": run_in_background,
                                "task_type": "agent",
                                "description": description or agent_name,
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                if asyncio.iscoroutine(emission):
                    await emission

            config = {"configurable": {"thread_id": thread_id}}
            output_parts: list[str] = []
            latest_progress = description or agent_name

            if run_in_background and self._queue_manager and parent_thread_id and self._background_progress_interval_s > 0:
                progress_stop = asyncio.Event()
                progress_task = asyncio.create_task(
                    self._emit_background_progress(
                        task_id=task_id,
                        agent_name=agent_name,
                        parent_thread_id=parent_thread_id,
                        latest_progress=lambda: latest_progress,
                        stop_event=progress_stop,
                    )
                )

            # Build initial input — with or without forked parent context
            if fork_context:
                from sandbox.thread_context import get_current_messages

                # @@@pt-04-fork-context-source
                # The Agent tool already has an explicit parent ToolUseContext on
                # the live ToolRunner path. Forked sub-agents must prefer that
                # concrete message snapshot over ambient ContextVar state, or the
                # direct runner path silently drops parent context.
                parent_msgs = list(parent_tool_context.messages) if parent_tool_context is not None else get_current_messages()
                fork_marker = (
                    "\n\n### ENTERING SUB-AGENT ROUTINE ###\n"
                    "Messages above are from the parent thread (read-only context).\n"
                    "Only complete the specific task assigned below.\n\n"
                )
                initial_messages: list = [
                    *_filter_fork_messages(parent_msgs),
                    {"role": "user", "content": fork_marker + prompt},
                ]
            else:
                initial_messages = [{"role": "user", "content": prompt}]

            if self._web_app is not None:
                from backend.web.services.streaming_service import run_child_thread_live

                result = await run_child_thread_live(
                    agent,
                    thread_id,
                    prompt,
                    self._web_app,
                    input_messages=initial_messages,
                )
                if result:
                    output_parts.append(result)
                    latest_progress = self._summarize_progress(result, description or agent_name)
            else:
                async for chunk in agent.agent.astream(
                    {"messages": initial_messages},
                    config=config,
                    stream_mode="updates",
                ):
                    for _, node_update in chunk.items():
                        if not isinstance(node_update, dict):
                            continue
                        msgs = node_update.get("messages", [])
                        if not isinstance(msgs, list):
                            msgs = [msgs]
                        for msg in msgs:
                            if msg.__class__.__name__ == "AIMessage":
                                content = getattr(msg, "content", "")
                                if isinstance(content, str) and content:
                                    output_parts.append(content)
                                    latest_progress = self._summarize_progress(content, description or agent_name)
                                elif isinstance(content, list):
                                    for block in content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            text = block.get("text", "")
                                            if text:
                                                output_parts.append(text)
                                                latest_progress = self._summarize_progress(text, description or agent_name)

            await self._agent_registry.update_status(task_id, "completed")
            result = "\n".join(output_parts) or "(Agent completed with no text output)"
            if progress_stop is not None:
                progress_stop.set()
            if progress_task is not None:
                await progress_task
            # Notify frontend: task done
            if emit_fn is not None:
                emission = emit_fn(
                    {
                        "event": "task_done",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "background": run_in_background,
                            },
                            ensure_ascii=False,
                        ),
                    }
                )
                if asyncio.iscoroutine(emission):
                    await emission
            # Queue notification only for background runs — blocking callers already
            # received the result as the tool's return value; sending a notification
            # would trigger a spurious new parent turn.
            if run_in_background and self._queue_manager and parent_thread_id:
                label = description or agent_name
                notification = format_background_notification(
                    task_id=task_id,
                    status="completed",
                    summary=label,
                    result=result,
                    description=label,
                )
                self._queue_manager.enqueue(notification, parent_thread_id, notification_type="agent")
            return result

        except Exception:
            if progress_stop is not None:
                progress_stop.set()
            if progress_task is not None:
                await progress_task
            logger.exception("[AgentService] Agent %s failed", agent_name)
            await self._agent_registry.update_status(task_id, "error")
            # Notify frontend: task error
            if emit_fn is not None:
                try:
                    emission = emit_fn(
                        {
                            "event": "task_error",
                            "data": json.dumps(
                                {
                                    "task_id": task_id,
                                    "background": run_in_background,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                    if asyncio.iscoroutine(emission):
                        await emission
                except Exception:
                    logger.exception("Failed to emit background agent task_error event for task %s", task_id)
            if run_in_background and self._queue_manager and parent_thread_id:
                label = description or agent_name
                notification = format_background_notification(
                    task_id=task_id,
                    status="error",
                    summary=label,
                    result="Agent failed",
                    description=label,
                )
                self._queue_manager.enqueue(notification, parent_thread_id, notification_type="agent")
            raise
        finally:
            if agent is not None:
                try:
                    self._merge_child_bootstrap_accumulators(
                        getattr(self, "_parent_bootstrap", None),
                        getattr(agent, "_bootstrap", None),
                        child_bootstrap_start_cost=child_bootstrap_start_cost,
                        child_bootstrap_start_tool_duration_ms=child_bootstrap_start_tool_duration_ms,
                    )
                    if hasattr(agent, "_agent_service") and hasattr(agent._agent_service, "cleanup_background_runs"):
                        await agent._agent_service.cleanup_background_runs()
                    # @@@web-child-close-owner - web child threads stay visible
                    # via their persisted thread/task surface, not by keeping
                    # this LeonAgent instance alive forever. The live bridge
                    # owns the eventual close after it finishes harvesting the
                    # child run result.
                    if self._web_app is None:
                        # @@@subagent-sandbox-close-skip - Child agents can share the
                        # parent's lease; closing the child sandbox here can pause the
                        # shared lease mid-owner-turn.
                        agent.close(cleanup_sandbox=False)
                except Exception:
                    logger.exception("Failed to clean up child agent after task %s", task_id)

    @staticmethod
    def _merge_child_bootstrap_accumulators(
        parent_bootstrap: Any,
        child_bootstrap: Any,
        *,
        child_bootstrap_start_cost: float,
        child_bootstrap_start_tool_duration_ms: int,
    ) -> None:
        if parent_bootstrap is None or child_bootstrap is None or parent_bootstrap is child_bootstrap:
            return
        # @@@sa-03-bootstrap-rollup
        # Sub-agent loops start from a forked bootstrap snapshot. At join time we
        # need to preserve both the parent's concurrent growth and the child's
        # post-fork delta instead of letting one side overwrite the other.
        child_cost_delta = max(
            0.0,
            float(getattr(child_bootstrap, "total_cost_usd", 0.0)) - child_bootstrap_start_cost,
        )
        child_tool_duration_delta = max(
            0,
            int(getattr(child_bootstrap, "total_tool_duration_ms", 0)) - child_bootstrap_start_tool_duration_ms,
        )
        parent_bootstrap.total_cost_usd = float(getattr(parent_bootstrap, "total_cost_usd", 0.0)) + child_cost_delta
        parent_bootstrap.total_tool_duration_ms = int(getattr(parent_bootstrap, "total_tool_duration_ms", 0)) + child_tool_duration_delta

    @staticmethod
    def _summarize_progress(text: str, default_text: str) -> str:
        collapsed = " ".join(text.split()).strip()
        if not collapsed:
            return default_text
        return collapsed[:120]

    async def _emit_background_progress(
        self,
        *,
        task_id: str,
        agent_name: str,
        parent_thread_id: str,
        latest_progress: Any,
        stop_event: asyncio.Event,
    ) -> None:
        # @@@sa-06-progress-loop - keep prompt-facing coordinator updates on the
        # real thread delivery queue instead of inventing a detached parallel channel.
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._background_progress_interval_s)
                return
            except TimeoutError:
                pass

            if self._queue_manager is None:
                return

            notification = format_progress_notification(
                task_id,
                latest_progress(),
                step="running",
            )
            self._queue_manager.enqueue(
                notification,
                parent_thread_id,
                notification_type="agent",
                source="system",
                sender_name=agent_name,
            )

    async def _handle_task_output(self, task_id: str, block: bool = True, timeout: int = 30_000) -> str:
        """Get output of a background agent task."""
        running = self._tasks.get(task_id)
        if not running:
            return f"Error: task '{task_id}' not found"

        if not block:
            if not running.is_done:
                return json.dumps(
                    {
                        "task_id": task_id,
                        "status": "running",
                        "message": _background_run_running_message(running),
                    },
                    ensure_ascii=False,
                )

            result = _background_run_result(running)
            return json.dumps(
                {
                    "task_id": task_id,
                    "status": _background_run_result_status(running, result),
                    "result": result,
                },
                ensure_ascii=False,
            )

        if not running.is_done:
            completed = await _wait_for_background_run(running, min(timeout, 600_000))
            if not completed and not running.is_done:
                return json.dumps(
                    {
                        "task_id": task_id,
                        "status": "timeout",
                        "message": _background_run_running_message(running),
                    },
                    ensure_ascii=False,
                )

        if not running.is_done:
            return json.dumps(
                {
                    "task_id": task_id,
                    "status": "running",
                    "message": _background_run_running_message(running),
                },
                ensure_ascii=False,
            )

        result = _background_run_result(running)
        return json.dumps(
            {
                "task_id": task_id,
                "status": _background_run_result_status(running, result),
                "result": result,
            },
            ensure_ascii=False,
        )

    async def _handle_send_message(
        self,
        target_name: str,
        message: str,
        sender_name: str | None = None,
    ) -> str:
        if self._queue_manager is None:
            return "<tool_use_error>SendMessage requires queue_manager</tool_use_error>"

        matches = await self._agent_registry.list_running_by_name(target_name)
        if not matches:
            return f"<tool_use_error>Running agent '{target_name}' not found</tool_use_error>"
        if len(matches) > 1:
            return (
                f"<tool_use_error>Running agent name '{target_name}' is ambiguous. "
                "Use a unique name before calling SendMessage.</tool_use_error>"
            )
        target = matches[0]

        delivered = format_agent_message(sender_name or "agent", message)
        self._queue_manager.enqueue(
            delivered,
            target.thread_id,
            notification_type="agent",
            source="system",
            sender_name=sender_name or "agent",
        )
        return f"Message sent to {target.name}."

    async def _handle_ask_user_question(
        self,
        questions: list[dict[str, Any]],
        annotations: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        tool_context: ToolUseContext | None = None,
    ) -> Any:
        if tool_context is None or tool_context.request_permission is None:
            return tool_error("<tool_use_error>AskUserQuestion requires an interactive owner resolver</tool_use_error>")

        payload: dict[str, Any] = {"questions": questions}
        if annotations is not None:
            payload["annotations"] = annotations
        if metadata is not None:
            payload["metadata"] = metadata

        request_result = tool_context.request_permission(
            "AskUserQuestion",
            payload,
            ToolPermissionContext(is_read_only=True, is_destructive=False),
            None,
            "Please answer the following questions so Leon can continue.",
        )
        request_id = request_result.get("request_id") if isinstance(request_result, dict) else request_result
        if not isinstance(request_id, str) or not request_id:
            return tool_error("<tool_use_error>AskUserQuestion could not create a user-facing request</tool_use_error>")

        return tool_permission_request(
            "User input required to continue.",
            metadata={
                "decision": "ask",
                "request_id": request_id,
                "request_kind": "ask_user_question",
            },
        )

    async def _stop_background_run(self, task_id: str, running: BackgroundRun) -> None:
        if isinstance(running, _RunningTask):
            was_running = not running.task.done()
            if was_running:
                running.task.cancel()
                try:
                    await running.task
                except asyncio.CancelledError:
                    pass
                await self._agent_registry.update_status(running.agent_id, "error")
            self._tasks.pop(task_id, None)
            return

        if not running.is_done:
            await request_background_run_stop(running)

        self._tasks.pop(task_id, None)

    async def cleanup_background_runs(self) -> None:
        for task_id, running in list(self._tasks.items()):
            await self._stop_background_run(task_id, running)

    async def _handle_task_stop(self, task_id: str) -> str:
        """Stop a running background agent task."""
        running = self._tasks.get(task_id)
        if not running:
            return f"Error: task '{task_id}' not found"

        if running.is_done:
            return f"Task {task_id} already completed"

        await self._stop_background_run(task_id, running)
        return f"Task {task_id} cancelled"
