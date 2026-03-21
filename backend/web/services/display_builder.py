"""Backend-owned display state — single source of truth for ChatEntry[].

Replaces two frontend state machines (message-mapper.ts + use-stream-handler.ts)
with one Python module.  Both GET (refresh) and SSE (streaming) produce entries
from this builder.

GET  → build_from_checkpoint() or get_entries()  → full entries[]
SSE  → apply_event()                              → display_delta
"""

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types — mirror frontend/app/src/api/types.ts
# ---------------------------------------------------------------------------

DeltaType = Literal[
    "append_entry",
    "append_segment",
    "update_segment",
    "finalize_turn",
    "full_state",
]


# ---------------------------------------------------------------------------
# Helpers — ported from message-mapper.ts
# ---------------------------------------------------------------------------

_SYSTEM_REMINDER_RE = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>")
_CHAT_MESSAGE_RE = re.compile(r"<chat-message[^>]*>([\s\S]*?)</chat-message>")


def _extract_text_content(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts = []
        for block in raw:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(raw) if raw is not None else ""


def _strip_system_reminders(text: str) -> str:
    return _SYSTEM_REMINDER_RE.sub("", text).strip()


def _extract_chat_message(text: str) -> str | None:
    m = _CHAT_MESSAGE_RE.search(text)
    return m.group(1).strip() if m else None


def _make_id(prefix: str = "db") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Entry builders
# ---------------------------------------------------------------------------

def _build_tool_segments(tool_calls: list, msg_index: int, now: int) -> list[dict]:
    segs = []
    for j, raw in enumerate(tool_calls):
        call = raw if isinstance(raw, dict) else {}
        segs.append({
            "type": "tool",
            "step": {
                "id": call.get("id") or f"hist-tc-{msg_index}-{j}",
                "name": call.get("name") or "unknown",
                "args": call.get("args") or {},
                "status": "calling",
                "timestamp": now,
            },
        })
    return segs


def _create_turn(msg_id: str, segments: list[dict], now: int) -> dict:
    return {
        "id": msg_id,
        "messageIds": [msg_id],
        "role": "assistant",
        "segments": segments,
        "timestamp": now,
    }


def _append_to_turn(turn: dict, msg_id: str, segments: list[dict]) -> None:
    turn["segments"].extend(segments)
    turn.setdefault("messageIds", []).append(msg_id)


# ---------------------------------------------------------------------------
# ThreadDisplay — per-thread in-memory state
# ---------------------------------------------------------------------------

@dataclass
class ThreadDisplay:
    entries: list[dict] = field(default_factory=list)
    current_turn_id: str | None = None
    current_run_id: str | None = None
    display_seq: int = 0  # monotonic counter for display_delta dedup


# ---------------------------------------------------------------------------
# DisplayBuilder — owns all display computation
# ---------------------------------------------------------------------------

class DisplayBuilder:
    """Single source of truth for per-thread ChatEntry[] display state."""

    def __init__(self) -> None:
        self._threads: dict[str, ThreadDisplay] = {}

    # --- Public API ---

    def get_entries(self, thread_id: str) -> list[dict] | None:
        """Return in-memory entries, or None if not cached (cold start)."""
        td = self._threads.get(thread_id)
        return td.entries if td else None

    def get_display_seq(self, thread_id: str) -> int:
        """Return current display_seq for dedup on SSE reconnect."""
        td = self._threads.get(thread_id)
        return td.display_seq if td else 0

    def set_entries(self, thread_id: str, entries: list[dict]) -> None:
        """Set entries for a thread (after build_from_checkpoint)."""
        self._threads[thread_id] = ThreadDisplay(entries=entries)

    def build_from_checkpoint(self, thread_id: str, messages: list[dict]) -> list[dict]:
        """Convert serialized checkpoint messages → ChatEntry[].

        Port of frontend mapBackendEntries.
        """
        now = int(time.time() * 1000)
        current_turn: dict | None = None
        current_run_id: str | None = None
        entries: list[dict] = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                continue
            msg_type = msg.get("type", "")
            if msg_type == "HumanMessage":
                current_turn, current_run_id = self._handle_human(
                    msg, i, entries, current_turn, current_run_id, now,
                )
            elif msg_type == "AIMessage":
                current_turn, current_run_id = self._handle_ai(
                    msg, i, entries, current_turn, current_run_id, now,
                )
            elif msg_type == "ToolMessage":
                self._handle_tool(msg, i, current_turn, now)

        td = ThreadDisplay(entries=entries, current_turn_id=current_turn["id"] if current_turn else None,
                           current_run_id=current_run_id)
        self._threads[thread_id] = td
        return entries

    def apply_event(self, thread_id: str, event_type: str, data: dict) -> dict | None:
        """Apply a streaming event → mutate entries → return delta dict or None.

        Called after emit() in streaming_service.  The delta is sent as
        SSE event: display_delta.
        """
        td = self._threads.get(thread_id)
        if td is None:
            td = ThreadDisplay()
            self._threads[thread_id] = td

        handler = _EVENT_HANDLERS.get(event_type)
        if handler:
            delta = handler(td, data)
            if delta:
                td.display_seq += 1
                delta["_display_seq"] = td.display_seq
            return delta
        return None

    def finalize_turn(self, thread_id: str) -> dict | None:
        """Close the current turn.  Returns finalize_turn delta."""
        td = self._threads.get(thread_id)
        if not td or not td.current_turn_id:
            return None
        return _handle_finalize(td)

    def open_turn(self, thread_id: str, turn_id: str | None = None,
                  timestamp: int | None = None) -> dict:
        """Open a new assistant turn.  Returns append_entry delta."""
        td = self._threads.get(thread_id)
        if td is None:
            td = ThreadDisplay()
            self._threads[thread_id] = td
        turn_id = turn_id or _make_id("turn")
        ts = timestamp or int(time.time() * 1000)
        turn: dict = {
            "id": turn_id,
            "role": "assistant",
            "segments": [],
            "timestamp": ts,
            "streaming": True,
        }
        td.entries.append(turn)
        td.current_turn_id = turn_id
        return {"type": "append_entry", "entry": turn}

    def clear(self, thread_id: str) -> None:
        """Remove cached display state for a thread."""
        self._threads.pop(thread_id, None)

    # --- Checkpoint handlers (port of message-mapper.ts) ---

    def _handle_human(
        self, msg: dict, i: int,
        entries: list[dict], current_turn: dict | None, current_run_id: str | None,
        now: int,
    ) -> tuple[dict | None, str | None]:
        display = msg.get("display") or {}
        meta = msg.get("metadata") or {}

        # Hidden
        if display.get("showing") is False:
            return None, None

        # System / external chat notification → notice
        ntype = meta.get("notification_type")
        source = meta.get("source")
        if source == "system" or (source == "external" and ntype == "chat"):
            content = _extract_text_content(msg.get("content"))
            msg_run_id = meta.get("run_id") or None

            # Fold into current turn if same run
            if current_turn and (not msg_run_id or msg_run_id == current_run_id):
                current_turn["segments"].append({
                    "type": "notice",
                    "content": content,
                    "notification_type": ntype,
                })
                return current_turn, current_run_id

            # Standalone notice
            entries.append({
                "id": msg.get("id") or f"hist-notice-{i}",
                "role": "notice",
                "content": content,
                "notification_type": ntype,
                "timestamp": now,
            })
            return None, None

        # Normal user message
        entries.append({
            "id": msg.get("id") or f"hist-user-{i}",
            "role": "user",
            "content": _extract_text_content(msg.get("content")),
            "timestamp": now,
        })
        return None, None

    def _handle_ai(
        self, msg: dict, i: int,
        entries: list[dict], current_turn: dict | None, current_run_id: str | None,
        now: int,
    ) -> tuple[dict | None, str | None]:
        display = msg.get("display") or {}

        # Hidden: skip
        if display.get("showing") is False:
            return current_turn, current_run_id

        text_content = _strip_system_reminders(_extract_text_content(msg.get("content")))
        tool_calls = msg.get("tool_calls") or []
        msg_id = msg.get("id") or f"hist-turn-{i}"
        msg_run_id = (msg.get("metadata") or {}).get("run_id") or None

        segments: list[dict] = []
        if text_content:
            segments.append({"type": "text", "content": text_content})
        if tool_calls:
            segments.extend(_build_tool_segments(tool_calls, i, now))

        # @@@turn-merge — merge within same run_id
        if current_turn and msg_run_id and msg_run_id == current_run_id:
            _append_to_turn(current_turn, msg_id, segments)
            return current_turn, current_run_id
        if current_turn and not msg_run_id and not current_run_id:
            _append_to_turn(current_turn, msg_id, segments)
            return current_turn, current_run_id

        turn = _create_turn(msg_id, segments, now)
        entries.append(turn)
        return turn, msg_run_id

    def _handle_tool(self, msg: dict, _i: int, current_turn: dict | None, _now: int) -> None:
        display = msg.get("display") or {}
        if display.get("showing") is False:
            return
        if not current_turn:
            return

        tc_id = msg.get("tool_call_id")
        if not tc_id:
            return

        for seg in current_turn["segments"]:
            if seg.get("type") == "tool" and seg.get("step", {}).get("id") == tc_id:
                content_str = _extract_text_content(msg.get("content"))
                seg["step"]["result"] = content_str
                seg["step"]["status"] = "done"

                # Restore subagent_stream from metadata
                meta = msg.get("metadata") or {}
                task_id = meta.get("task_id")
                sub_thread = meta.get("subagent_thread_id") or (f"subagent-{task_id}" if task_id else None)

                if not task_id and seg["step"].get("name") == "Agent":
                    try:
                        parsed = json.loads(content_str)
                        if isinstance(parsed, dict) and parsed.get("task_id"):
                            task_id = parsed["task_id"]
                            sub_thread = parsed.get("thread_id") or f"subagent-{task_id}"
                    except (json.JSONDecodeError, TypeError):
                        pass

                if sub_thread and not seg["step"].get("subagent_stream"):
                    seg["step"]["subagent_stream"] = {
                        "task_id": task_id or "",
                        "thread_id": sub_thread,
                        "description": meta.get("description"),
                        "text": "",
                        "tool_calls": [],
                        "status": "completed",
                    }
                break


# ---------------------------------------------------------------------------
# Streaming event handlers — called by apply_event
# ---------------------------------------------------------------------------

def _get_current_turn(td: ThreadDisplay) -> dict | None:
    """Get the current open assistant turn, or None."""
    if not td.current_turn_id:
        return None
    for entry in reversed(td.entries):
        if entry.get("role") == "assistant" and entry.get("id") == td.current_turn_id:
            return entry
    return None


def _handle_user_message(td: ThreadDisplay, data: dict) -> dict | None:
    """Owner sent a message — add UserMessage entry.

    Does NOT break current_turn_id — the ongoing stream continues to
    append to the active turn.  Turn transitions are handled by
    run_start/run_done events.  This allows steers to appear at the
    bottom while the agent keeps streaming above.
    """
    content = data.get("content", "")
    entry: dict = {
        "id": _make_id("user"),
        "role": "user",
        "content": content,
        "timestamp": int(time.time() * 1000),
    }
    td.entries.append(entry)
    return {"type": "append_entry", "entry": entry}


def _handle_run_start(td: ThreadDisplay, data: dict) -> dict | None:
    if data.get("showing") is False:
        return None

    source = data.get("source")
    run_id = data.get("run_id")
    now = int(time.time() * 1000)

    # External notification run: reopen last assistant turn (fold into it)
    if source and source != "owner":
        for entry in reversed(td.entries):
            if entry.get("role") == "assistant":
                entry["streaming"] = True
                td.current_turn_id = entry["id"]
                td.current_run_id = run_id
                # No delta — the turn already exists in the frontend's entries.
                # Subsequent deltas (append_segment) will target this turn.
                return None
        # No previous turn — fall through to create new

    turn_id = _make_id("turn")
    turn: dict = {
        "id": turn_id,
        "role": "assistant",
        "segments": [],
        "timestamp": now,
        "streaming": True,
    }
    td.entries.append(turn)
    td.current_turn_id = turn_id
    td.current_run_id = run_id
    return {"type": "append_entry", "entry": turn}


def _handle_text(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        return None

    content = data.get("content", "")
    if not content:
        return None

    segments = turn["segments"]
    if segments and segments[-1].get("type") == "text":
        # Append to existing text segment
        segments[-1]["content"] += content
        return {
            "type": "update_segment",
            "index": -1,
            "patch": {"append_content": content},
        }

    # New text segment
    seg = {"type": "text", "content": content}
    segments.append(seg)
    return {"type": "append_segment", "segment": seg}


def _handle_tool_call(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        return None

    tc_id = data.get("id") or _make_id("tc")
    tc_name = data.get("name", "")
    tc_args = data.get("args")

    # Dedup: if tool_call already exists, update args only
    for seg in turn["segments"]:
        if seg.get("type") == "tool" and seg.get("step", {}).get("id") == tc_id:
            if tc_args is not None and tc_args != {}:
                seg["step"]["args"] = tc_args
                return {
                    "type": "update_segment",
                    "index": _find_seg_index(turn, tc_id),
                    "patch": {"args": tc_args},
                }
            return None

    seg = {
        "type": "tool",
        "step": {
            "id": tc_id,
            "name": tc_name or "tool",
            "args": tc_args or {},
            "status": "calling",
            "timestamp": int(time.time() * 1000),
        },
    }
    turn["segments"].append(seg)
    return {"type": "append_segment", "segment": seg}


def _handle_tool_result(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        return None

    tc_id = data.get("tool_call_id")
    result = data.get("content", "")
    metadata = data.get("metadata") or {}

    for i, seg in enumerate(turn["segments"]):
        if seg.get("type") == "tool" and seg.get("step", {}).get("id") == tc_id:
            seg["step"]["result"] = result
            seg["step"]["status"] = "done"

            # Subagent stream tracking
            task_id = metadata.get("task_id")
            sub_thread = metadata.get("subagent_thread_id") or (f"subagent-{task_id}" if task_id else None)
            if sub_thread and not seg["step"].get("subagent_stream"):
                seg["step"]["subagent_stream"] = {
                    "task_id": task_id or "",
                    "thread_id": sub_thread,
                    "description": metadata.get("description"),
                    "text": "",
                    "tool_calls": [],
                    "status": "running",
                }

            return {
                "type": "update_segment",
                "index": i,
                "patch": {"status": "done", "result": result},
            }
    return None


def _handle_notice(td: ThreadDisplay, data: dict) -> dict | None:
    content = data.get("content", "")
    ntype = data.get("notification_type")

    turn = _get_current_turn(td)
    if turn:
        # Fold into current turn
        seg = {"type": "notice", "content": content, "notification_type": ntype}
        turn["segments"].append(seg)
        return {"type": "append_segment", "segment": seg}

    # Standalone notice
    entry: dict = {
        "id": _make_id("notice"),
        "role": "notice",
        "content": content,
        "notification_type": ntype,
        "timestamp": int(time.time() * 1000),
    }
    td.entries.append(entry)
    return {"type": "append_entry", "entry": entry}


def _handle_finalize(td: ThreadDisplay) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        td.current_turn_id = None
        return None

    now = int(time.time() * 1000)
    turn["streaming"] = False
    turn["endTimestamp"] = now
    # Remove retry segments
    turn["segments"] = [s for s in turn["segments"] if s.get("type") != "retry"]
    td.current_turn_id = None
    return {"type": "finalize_turn", "timestamp": now}


def _handle_run_done(td: ThreadDisplay, data: dict) -> dict | None:
    return _handle_finalize(td)


def _handle_error(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        return None

    if isinstance(data, str):
        text = data
    elif isinstance(data, dict) and "error" in data:
        text = str(data["error"])
    else:
        text = json.dumps(data)

    seg = {"type": "text", "content": f"\n\nError: {text}"}
    turn["segments"].append(seg)
    return {"type": "append_segment", "segment": seg}


def _handle_cancelled(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        return None

    ids = data.get("cancelled_tool_call_ids") or []
    patches = []
    for seg in turn["segments"]:
        if seg.get("type") == "tool" and seg.get("step", {}).get("id") in ids:
            seg["step"]["status"] = "cancelled"
            seg["step"]["result"] = "任务被用户取消"
            patches.append(seg["step"]["id"])

    if not patches:
        return None
    return {
        "type": "update_segment",
        "index": -1,
        "patch": {"cancelled_ids": patches},
    }


def _handle_retry(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn:
        return None

    seg = {
        "type": "retry",
        "attempt": data.get("attempt", 1),
        "maxAttempts": data.get("max_attempts", 10),
        "waitSeconds": data.get("wait_seconds", 0),
    }
    # Replace existing retry
    turn["segments"] = [s for s in turn["segments"] if s.get("type") != "retry"]
    turn["segments"].append(seg)
    return {"type": "append_segment", "segment": seg}


def _handle_task_start(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn or not data.get("task_id"):
        return None

    task_id = data["task_id"]
    sub_thread = data.get("thread_id") or f"subagent-{task_id}"

    # Find most recent Agent tool call without subagent_stream
    for seg in reversed(turn["segments"]):
        if (seg.get("type") == "tool"
                and seg.get("step", {}).get("name") == "Agent"
                and seg.get("step", {}).get("status") == "calling"
                and not seg.get("step", {}).get("subagent_stream")):
            seg["step"]["subagent_stream"] = {
                "task_id": task_id,
                "thread_id": sub_thread,
                "description": data.get("description"),
                "text": "",
                "tool_calls": [],
                "status": "running",
            }
            idx = _find_seg_index(turn, seg["step"]["id"])
            return {
                "type": "update_segment",
                "index": idx,
                "patch": {"subagent_stream": seg["step"]["subagent_stream"]},
            }
    return None


def _handle_task_done(td: ThreadDisplay, data: dict) -> dict | None:
    turn = _get_current_turn(td)
    if not turn or not data.get("task_id"):
        return None

    task_id = data["task_id"]
    for seg in turn["segments"]:
        if (seg.get("type") == "tool"
                and seg.get("step", {}).get("subagent_stream", {}).get("task_id") == task_id):
            seg["step"]["subagent_stream"]["status"] = "completed"
            idx = _find_seg_index(turn, seg["step"]["id"])
            return {
                "type": "update_segment",
                "index": idx,
                "patch": {"subagent_stream_status": "completed"},
            }
    return None


def _find_seg_index(turn: dict, tc_id: str) -> int:
    for i, seg in enumerate(turn.get("segments", [])):
        if seg.get("type") == "tool" and seg.get("step", {}).get("id") == tc_id:
            return i
    return -1


# Event type → handler
_EVENT_HANDLERS: dict[str, Any] = {
    "user_message": _handle_user_message,
    "run_start": _handle_run_start,
    "run_done": _handle_run_done,
    "text": _handle_text,
    "tool_call": _handle_tool_call,
    "tool_result": _handle_tool_result,
    "notice": _handle_notice,
    "error": _handle_error,
    "cancelled": _handle_cancelled,
    "retry": _handle_retry,
    "task_start": _handle_task_start,
    "task_done": _handle_task_done,
}
