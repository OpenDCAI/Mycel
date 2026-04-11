/**
 * @@@display-builder — thin delta reducer for backend-owned display model.
 *
 * Replaces use-stream-handler.ts + stream-event-handlers.ts (~550 lines)
 * with a simple switch/case that applies display_delta events from the backend.
 * All display logic (turn management, notice folding, merge) lives in
 * backend/web/services/display_builder.py.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  cancelRun,
  isAssistantTurn,
  postRun,
  type AssistantTurn,
  type ChatEntry,
  type StreamStatus,
  type ToolStep,
  type TurnSegment,
} from "../api";
import type { UseThreadStreamResult } from "./use-thread-stream";
import { makeId } from "./utils";
import { asRecord } from "../lib/records";

// --- Delta types from backend ---

interface AppendEntryDelta {
  type: "append_entry";
  entry: ChatEntry;
}

interface AppendSegmentDelta {
  type: "append_segment";
  segment: TurnSegment;
}

type UpdateSegmentPatch = Partial<Pick<ToolStep, "status" | "result" | "args" | "subagent_stream">> & {
  append_content?: string;
  subagent_stream_status?: NonNullable<ToolStep["subagent_stream"]>["status"];
  cancelled_ids?: string[];
};

interface UpdateSegmentDelta {
  type: "update_segment";
  index: number;
  patch: UpdateSegmentPatch;
}

interface FinalizeTurnDelta {
  type: "finalize_turn";
  timestamp: number;
}

interface FullStateDelta {
  type: "full_state";
  entries: ChatEntry[];
}

type DisplayDelta =
  | AppendEntryDelta
  | AppendSegmentDelta
  | UpdateSegmentDelta
  | FinalizeTurnDelta
  | FullStateDelta;

type SequencedDisplayDelta = DisplayDelta & { _display_seq?: number };

const DISPLAY_DELTA_TYPES = new Set<string>([
  "append_entry",
  "append_segment",
  "update_segment",
  "finalize_turn",
  "full_state",
]);

// --- Helpers ---

function updateLastTurn(
  entries: ChatEntry[],
  updater: (turn: AssistantTurn) => AssistantTurn,
): ChatEntry[] {
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (isAssistantTurn(entry)) {
      const updated = [...entries];
      updated[i] = updater(entry);
      return updated;
    }
  }
  return entries;
}

function isSequencedDisplayDelta(value: unknown): value is SequencedDisplayDelta {
  const delta = asRecord(value);
  return typeof delta?.type === "string" && DISPLAY_DELTA_TYPES.has(delta.type);
}

// --- Delta reducer ---

function applyDelta(entries: ChatEntry[], delta: DisplayDelta): ChatEntry[] {
  switch (delta.type) {
    case "append_entry":
      return [...entries, delta.entry];

    case "append_segment":
      return updateLastTurn(entries, (t) => ({
        ...t,
        segments: [...t.segments, delta.segment],
      }));

    case "update_segment": {
      return updateLastTurn(entries, (t) => {
        const segs = [...t.segments];
        const idx = delta.index < 0 ? segs.length + delta.index : delta.index;
        if (idx < 0 || idx >= segs.length) return t;

        const seg = { ...segs[idx] };
        const patch = delta.patch;

        // Text append
        if (seg.type === "text" && typeof patch.append_content === "string") {
          seg.content = (seg.content || "") + patch.append_content;
        }
        // Tool status update
        if (seg.type === "tool" && patch.status) {
          seg.step = { ...seg.step, status: patch.status };
          if (patch.result !== undefined) seg.step.result = patch.result;
        }
        // Tool args update
        if (seg.type === "tool" && patch.args !== undefined) {
          seg.step = { ...seg.step, args: patch.args };
        }
        // Subagent stream
        if (seg.type === "tool" && patch.subagent_stream) {
          seg.step = { ...seg.step, subagent_stream: patch.subagent_stream };
        }
        if (seg.type === "tool" && patch.subagent_stream_status) {
          if (seg.step.subagent_stream) {
            seg.step = {
              ...seg.step,
              status: patch.subagent_stream_status === "completed" ? "done" : seg.step.status,
              subagent_stream: { ...seg.step.subagent_stream, status: patch.subagent_stream_status },
            };
          }
        }
        // Cancelled
        const cancelledIds = patch.cancelled_ids;
        if (cancelledIds && Array.isArray(cancelledIds)) {
          return {
            ...t,
            segments: segs.map((s) =>
              s.type === "tool" && cancelledIds.includes(s.step.id)
                ? { ...s, step: { ...s.step, status: "cancelled" as const, result: "任务被用户取消" } }
                : s,
            ),
          };
        }

        segs[idx] = seg;
        return { ...t, segments: segs };
      });
    }

    case "finalize_turn":
      return updateLastTurn(entries, (t) => ({
        ...t,
        streaming: false,
        endTimestamp: delta.timestamp,
        segments: t.segments.filter((s) => s.type !== "retry"),
      }));

    case "full_state":
      return delta.entries;
  }
}

// --- Hook ---

interface DisplayDeltaDeps {
  threadId: string;
  onUpdate: (updater: (prev: ChatEntry[]) => ChatEntry[]) => void;
  /** display_seq from GET response — skip deltas with _display_seq <= this */
  displaySeq: number;
  stream: Pick<UseThreadStreamResult, "runtimeStatus" | "isRunning" | "subscribe">;
}

export interface DisplayDeltaState {
  runtimeStatus: StreamStatus | null;
  isRunning: boolean;
}

export interface DisplayDeltaActions {
  handleSendMessage: (message: string, attachments?: string[]) => Promise<void>;
  handleStopStreaming: () => Promise<void>;
}

export function useDisplayDeltas(
  deps: DisplayDeltaDeps,
): DisplayDeltaState & DisplayDeltaActions {
  const { threadId, onUpdate, displaySeq, stream } = deps;

  const [sendPending, setSendPending] = useState(false);
  const [displayRunState, setDisplayRunState] = useState<{
    threadId: string;
    state: "unknown" | "open" | "closed";
  }>({ threadId, state: "unknown" });
  const { isRunning: streamIsRunning, runtimeStatus, subscribe } = stream;
  const currentDisplayRunState = displayRunState.threadId === threadId ? displayRunState.state : "unknown";
  const isRunning = sendPending || (currentDisplayRunState === "unknown" ? streamIsRunning : currentDisplayRunState === "open");

  useEffect(() => {
    if (!streamIsRunning) return;
    const clearPending = window.setTimeout(() => setSendPending(false), 0);
    return () => window.clearTimeout(clearPending);
  }, [streamIsRunning]);

  const onUpdateRef = useRef(onUpdate);
  const displaySeqRef = useRef(displaySeq);
  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);
  useEffect(() => {
    displaySeqRef.current = displaySeq;
  }, [displaySeq]);

  // Subscribe to display_delta events only
  useEffect(() => {
    return subscribe((event) => {
      if (event.type !== "display_delta") return;
      if (!isSequencedDisplayDelta(event.data)) return;
      const delta = event.data;

      // @@@display-seq-dedup — skip stale deltas replayed from ring buffer
      const deltaSeq = delta._display_seq;
      if (typeof deltaSeq === "number" && deltaSeq <= displaySeqRef.current) return;
      if (delta.type === "append_entry" && delta.entry.role === "assistant" && delta.entry.streaming !== false) {
        setSendPending(false);
        setDisplayRunState({ threadId, state: "open" });
      }
      if (delta.type === "finalize_turn") {
        setDisplayRunState({ threadId, state: "closed" });
      }
      flushSync(() => {
        onUpdateRef.current((prev) => applyDelta(prev, delta));
      });
    });
  }, [subscribe, threadId]);

  const handleSendMessage = useCallback(
    async (message: string, attachments?: string[]) => {
      // No optimistic user entry — backend emits user_message event via SSE,
      // which display_builder converts to append_entry delta.
      setSendPending(true);
      try {
        await postRun(threadId, message, undefined, attachments?.length ? { attachments } : undefined);
      } catch (err) {
        setSendPending(false);
        if (err instanceof Error && err.message === "Run cancelled") return;
        if (err instanceof Error) {
          const errorTurn: AssistantTurn = {
            id: makeId("error"),
            role: "assistant",
            segments: [{ type: "text" as const, content: `\n\nError: ${err.message}` }],
            timestamp: Date.now(),
          };
          onUpdateRef.current((prev) => [...prev, errorTurn]);
        }
      }
    },
    [threadId],
  );

  const handleStopStreaming = useCallback(async () => {
    try {
      await cancelRun(threadId);
      setSendPending(false);
      setDisplayRunState({ threadId, state: "closed" });
    } catch (err) {
      console.error("Failed to cancel run:", err);
    }
  }, [threadId]);

  return { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming };
}
