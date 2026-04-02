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
import uuid
from pathlib import Path
from typing import Any

from config.loader import AgentLoader
from core.agents.registry import AgentEntry, AgentRegistry
from core.runtime.middleware.queue.formatters import (
    format_agent_message,
    format_background_notification,
    format_progress_notification,
)
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry
from core.runtime.state import ToolUseContext

logger = logging.getLogger(__name__)

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
) -> str:
    env_model = os.getenv("CLAUDE_CODE_SUBAGENT_MODEL")
    if env_model:
        return env_model
    if requested_model:
        return requested_model

    agent_def = AgentLoader(workspace_root=workspace_root).load_all_agents().get(_get_subagent_agent_name(subagent_type))
    if agent_def and agent_def.model:
        return agent_def.model

    return inherited_model


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


AGENT_SCHEMA = {
    "name": "Agent",
    "description": (
        "Launch a sub-agent for independent task execution. "
        "Types: explore (read-only codebase search), plan (architecture design, read-only), "
        "bash (shell commands only), general (full tool access). "
        "Use for: multi-step tasks, parallel work, tasks needing isolation. "
        "Do NOT use for simple file reads or single grep searches — use the tools directly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
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
                    "Short description of what agent will do. Required when run_in_background is true; "
                    "shown in the background task indicator."
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
        "required": ["prompt"],
    },
}

TASK_OUTPUT_SCHEMA = {
    "name": "TaskOutput",
    "description": "Get output of a background task (agent or bash). Blocks until task completes by default. Returns full text output or error.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID returned when starting a background agent",
            },
        },
        "required": ["task_id"],
    },
}

TASK_STOP_SCHEMA = {
    "name": "TaskStop",
    "description": "Cancel a running background task. Sends cancellation signal; task may take a moment to stop.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "The task ID to stop",
            },
        },
        "required": ["task_id"],
    },
}

SEND_MESSAGE_SCHEMA = {
    "name": "SendMessage",
    "description": "Send a queued message to another running agent by name. Delivered before that agent's next model turn.",
    "parameters": {
        "type": "object",
        "properties": {
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
        "required": ["target_name", "message"],
    },
}


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
    ):
        self._agent_registry = agent_registry
        self._workspace_root = workspace_root
        self._model_name = model_name
        self._queue_manager = queue_manager
        self._background_progress_interval_s = background_progress_interval_s
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
                search_hint="send message running agent mailbox queue",
            )
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
    ) -> str:
        """Spawn an independent LeonAgent and run it with the given prompt."""
        from sandbox.thread_context import get_current_thread_id

        task_id = uuid.uuid4().hex[:8]
        agent_name = name or f"agent-{task_id}"
        thread_id = f"subagent-{task_id}"
        parent_thread_id = get_current_thread_id()

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
            return json.dumps(
                {
                    "task_id": task_id,
                    "agent_name": agent_name,
                    "thread_id": thread_id,
                    "status": "running",
                    "message": "Agent started in background. Use TaskOutput to get result.",
                },
                ensure_ascii=False,
            )

        # Default: parent blocks until sub-agent completes (does not block frontend event loop)
        try:
            result = await task
            await self._agent_registry.update_status(task_id, "completed")
            return result
        except Exception as e:
            await self._agent_registry.update_status(task_id, "error")
            return f"<tool_use_error>Agent failed: {e}</tool_use_error>"

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

        # Lazy import avoids circular dependency (agent.py imports AgentService)
        from core.runtime.agent import create_leon_agent
        from sandbox.thread_context import get_current_thread_id, set_current_thread_id

        parent_thread_id = get_current_thread_id()

        # emit_fn is set if EventBus is available; used for task lifecycle SSE events
        emit_fn = None
        try:
            from backend.web.event_bus import get_event_bus

            event_bus = get_event_bus()
            emit_fn = event_bus.make_emitter(
                thread_id=parent_thread_id,
                agent_id=task_id,
                agent_name=agent_name,
            )
        except ImportError:
            pass  # backend not available in standalone core usage

        agent = None
        progress_task: asyncio.Task | None = None
        progress_stop: asyncio.Event | None = None
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
                from core.runtime.fork import create_subagent_context, fork_context

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
                    child_bootstrap = fork_context(parent_bootstrap)
                    selected_model = _resolve_subagent_model(
                        self._workspace_root,
                        subagent_type,
                        model,
                        child_bootstrap.model_name,
                    )
                    agent = create_leon_agent(
                        model_name=selected_model,
                        workspace_root=child_bootstrap.workspace_root,
                        agent=agent_name_for_role,
                        extra_blocked_tools=extra_blocked,
                        allowed_tools=allowed,
                        verbose=False,
                    )
                else:
                    raise AttributeError("no parent bootstrap")
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
                    )
                    agent = create_leon_agent(
                        model_name=selected_model,
                        workspace_root=child_bootstrap.workspace_root,
                        agent=agent_name_for_role,
                        extra_blocked_tools=extra_blocked,
                        allowed_tools=allowed,
                        verbose=False,
                    )
                # @@@sa-04-child-bootstrap-wiring
                # The fork only becomes real once the spawned child agent and its
                # nested AgentService both receive the forked bootstrap/context.
                agent._bootstrap = child_bootstrap
                agent.agent._bootstrap = child_bootstrap
                if hasattr(agent, "_agent_service"):
                    agent._agent_service._parent_bootstrap = child_bootstrap
                    if child_tool_context is not None:
                        agent._agent_service._parent_tool_context = child_tool_context
            except (AttributeError, ImportError):
                inherited_model = getattr(parent_tool_context.bootstrap, "model_name", None) if parent_tool_context else None
                selected_model = _resolve_subagent_model(
                    self._workspace_root,
                    subagent_type,
                    model,
                    inherited_model or self._model_name,
                )
                agent = create_leon_agent(
                    model_name=selected_model,
                    workspace_root=self._workspace_root,
                    agent=agent_name_for_role,
                    extra_blocked_tools=extra_blocked,
                    allowed_tools=allowed,
                    verbose=False,
                )
            # In async context LeonAgent defers checkpointer init; call ainit() to
            # ensure state is persisted (and loadable via GET /api/threads/{thread_id}).
            await agent.ainit()

            # Wire child agent events to the parent's EventBus subscription
            # so the parent SSE stream shows sub-agent activity.
            if emit_fn is not None:
                if hasattr(agent, "runtime") and hasattr(agent.runtime, "bind_thread"):
                    agent.runtime.bind_thread(activity_sink=emit_fn)

            set_current_thread_id(thread_id)

            # Notify frontend: task started
            if emit_fn is not None:
                await emit_fn(
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
                parent_msgs = get_current_messages()
                _FORK_MARKER = (
                    "\n\n### ENTERING SUB-AGENT ROUTINE ###\n"
                    "Messages above are from the parent thread (read-only context).\n"
                    "Only complete the specific task assigned below.\n\n"
                )
                initial_messages: list = [
                    *_filter_fork_messages(parent_msgs),
                    {"role": "user", "content": _FORK_MARKER + prompt},
                ]
            else:
                initial_messages = [{"role": "user", "content": prompt}]

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
                await emit_fn(
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
                    await emit_fn(
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
                except Exception:
                    pass
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
                    if hasattr(agent, "_agent_service") and hasattr(agent._agent_service, "cleanup_background_runs"):
                        await agent._agent_service.cleanup_background_runs()
                    agent.close()
                except Exception:
                    pass

    @staticmethod
    def _summarize_progress(text: str, fallback: str) -> str:
        collapsed = " ".join(text.split()).strip()
        if not collapsed:
            return fallback
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
        # real queue path instead of inventing a detached mailbox abstraction.
        while True:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._background_progress_interval_s)
                return
            except asyncio.TimeoutError:
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

    async def _handle_task_output(self, task_id: str) -> str:
        """Get output of a background agent task."""
        running = self._tasks.get(task_id)
        if not running:
            return f"Error: task '{task_id}' not found"

        if not running.is_done:
            return json.dumps(
                {
                    "task_id": task_id,
                    "status": "running",
                    "message": "Agent is still running.",
                },
                ensure_ascii=False,
            )

        result = running.get_result()
        status = "error" if (result and result.startswith("<tool_use_error>")) else "completed"
        return json.dumps(
            {
                "task_id": task_id,
                "status": status,
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
            process = getattr(running._cmd, "process", None)
            wait = getattr(process, "wait", None) if process is not None else None
            terminate = getattr(process, "terminate", None) if process is not None else None
            kill = getattr(process, "kill", None) if process is not None else None

            if callable(terminate):
                terminate()
            if callable(wait):
                try:
                    await asyncio.wait_for(wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    if callable(kill):
                        kill()
                    await wait()

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
