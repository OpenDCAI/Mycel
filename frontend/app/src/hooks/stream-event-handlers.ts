import {
  type AssistantTurn,
  type ChatEntry,
  type StreamStatus,
  type ToolSegment,
} from "../api";
import type { StreamEvent } from "../api/types";
import { makeId } from "./utils";

export type UpdateEntries = (updater: (prev: ChatEntry[]) => ChatEntry[]) => void;
export type { StreamEvent };

type EventPayload = Record<string, unknown>;

function updateTurnSegments(
  onUpdate: UpdateEntries,
  turnId: string,
  updater: (turn: AssistantTurn) => AssistantTurn,
) {
  onUpdate((prev) =>
    prev.map((e) =>
      e.id === turnId && e.role === "assistant" ? updater(e as AssistantTurn) : e,
    ),
  );
}

function findTurnToolSeg(prev: ChatEntry[], turnId: string, toolCallId: string): ToolSegment | undefined {
  const turn = prev.find((e) => e.id === turnId && e.role === "assistant") as AssistantTurn | undefined;
  return turn?.segments.find((s) => s.type === "tool" && s.step.id === toolCallId) as ToolSegment | undefined;
}

// --- Individual event handlers ---

function handleText(event: StreamEvent, turnId: string, onUpdate: UpdateEntries) {
  const payload = event.data as { content?: string } | string | undefined;
  const chunk = typeof payload === "string" ? payload : payload?.content ?? "";
  // No flushSync — let React batch. Sticky scroll observes childList mutations.
  updateTurnSegments(onUpdate, turnId, (turn) => {
    const segs = [...turn.segments];
    const last = segs[segs.length - 1];
    if (last?.type === "text") {
      segs[segs.length - 1] = { type: "text", content: last.content + chunk };
    } else {
      segs.push({ type: "text", content: chunk });
    }
    return { ...turn, segments: segs };
  });
}

function handleToolCall(event: StreamEvent, turnId: string, onUpdate: UpdateEntries) {
  const payload = (event.data ?? {}) as { id?: string; name?: string; args?: unknown };
  const toolCallId = payload.id ?? makeId("tc");

  onUpdate((prev) => {
    const existing = findTurnToolSeg(prev, turnId, toolCallId);
    if (existing) return prev;
    return prev.map((e) => {
      if (e.id !== turnId || e.role !== "assistant") return e;
      const t = e as AssistantTurn;
      const seg: ToolSegment = {
        type: "tool",
        step: { id: toolCallId, name: payload.name ?? "tool", args: payload.args ?? {}, status: "calling", timestamp: Date.now() },
      };
      return { ...t, segments: [...t.segments, seg] };
    });
  });
}

function markToolDone(turn: AssistantTurn, tcId: string | undefined, result: string, metadata?: Record<string, unknown>): AssistantTurn {
  return { ...turn, segments: turn.segments.map((s) => {
    if (s.type !== "tool" || s.step.id !== tcId) return s;
    const step = { ...s.step, result, status: "done" as const };
    // For background Task calls: create subagent_stream from metadata so AgentsView can track
    const taskId = metadata?.task_id as string | undefined;
    const threadId = (metadata?.subagent_thread_id as string | undefined) || (taskId ? `subagent_${taskId}` : undefined);
    if (threadId && !step.subagent_stream) {
      step.subagent_stream = {
        task_id: taskId || "",
        thread_id: threadId,
        description: (metadata?.description as string) || undefined,
        text: "",
        tool_calls: [],
        status: "running",
      };
    }
    return { ...s, step };
  }) };
}

function handleToolResult(event: StreamEvent, turnId: string, onUpdate: UpdateEntries) {
  const payload = (event.data ?? {}) as { content?: string; tool_call_id?: string; metadata?: Record<string, unknown> };
  const tcId = payload.tool_call_id;
  const result = payload.content ?? "";
  const metadata = payload.metadata;

  onUpdate((prev) => {
    const seg = tcId ? findTurnToolSeg(prev, turnId, tcId) : undefined;
    if (seg?.step.status === "done") return prev;
    if (seg && Date.now() - seg.step.timestamp < 200) {
      setTimeout(() => updateTurnSegments(onUpdate, turnId, (t) => markToolDone(t, tcId, result, metadata)), 200 - (Date.now() - seg.step.timestamp));
      return prev;
    }
    return prev.map((e) => e.id === turnId && e.role === "assistant" ? markToolDone(e as AssistantTurn, tcId, result, metadata) : e);
  });
}

function handleError(event: StreamEvent, turnId: string, onUpdate: UpdateEntries) {
  const text = typeof event.data === "string" ? event.data : JSON.stringify(event.data ?? "Unknown error");
  updateTurnSegments(onUpdate, turnId, (turn) => ({
    ...turn,
    segments: [...turn.segments, { type: "text", content: `\n\nError: ${text}` }],
  }));
}

function handleCancelled(event: StreamEvent, turnId: string, onUpdate: UpdateEntries) {
  const ids: string[] = (event.data as EventPayload)?.cancelled_tool_call_ids as string[] || [];
  updateTurnSegments(onUpdate, turnId, (turn) => ({
    ...turn,
    streaming: false,
    segments: turn.segments.map((seg) =>
      seg.type === "tool" && ids.includes(seg.step.id)
        ? { ...seg, step: { ...seg.step, status: "cancelled" as const, result: "任务被用户取消" } }
        : seg,
    ),
  }));
}

// --- Main dispatcher via handler map ---

type EventHandler = (event: StreamEvent, turnId: string, onUpdate: UpdateEntries) => void;

const EVENT_HANDLERS: Record<string, EventHandler> = {
  text: handleText,
  tool_call: handleToolCall,
  tool_result: handleToolResult,
  error: handleError,
  cancelled: handleCancelled,
};

export function processStreamEvent(
  event: StreamEvent,
  turnId: string,
  onUpdate: UpdateEntries,
  setRuntimeStatus: (v: StreamStatus | null) => void,
): { messageId?: string } {
  const data = (event.data ?? {}) as EventPayload;
  const messageId = typeof data.message_id === "string" ? data.message_id : undefined;

  // Control events — handled by useThreadStream
  if (event.type === "status") {
    if (event.data) setRuntimeStatus(event.data as StreamStatus);
    return { messageId };
  }
  if (event.type === "run_start" || event.type === "run_done") {
    return { messageId };
  }

  // Content events
  const handler = EVENT_HANDLERS[event.type];
  if (handler) {
    handler(event, turnId, onUpdate);
    return { messageId };
  }

  return { messageId };
}
