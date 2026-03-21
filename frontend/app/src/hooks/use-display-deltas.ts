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
  postRun,
  type AssistantTurn,
  type ChatEntry,
  type StreamStatus,
} from "../api";
import { useThreadStream } from "./use-thread-stream";
import { makeId } from "./utils";

// --- Delta types from backend ---

interface AppendEntryDelta {
  type: "append_entry";
  entry: ChatEntry;
}

interface AppendSegmentDelta {
  type: "append_segment";
  segment: Record<string, unknown>;
}

interface UpdateSegmentDelta {
  type: "update_segment";
  index: number;
  patch: Record<string, unknown>;
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

// --- Helpers ---

function updateLastTurn(
  entries: ChatEntry[],
  updater: (turn: AssistantTurn) => AssistantTurn,
): ChatEntry[] {
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i].role === "assistant") {
      const updated = [...entries];
      updated[i] = updater(entries[i] as AssistantTurn);
      return updated;
    }
  }
  return entries;
}

// --- Delta reducer ---

function applyDelta(entries: ChatEntry[], delta: DisplayDelta): ChatEntry[] {
  switch (delta.type) {
    case "append_entry":
      return [...entries, delta.entry];

    case "append_segment":
      return updateLastTurn(entries, (t) => ({
        ...t,
        segments: [...t.segments, delta.segment as AssistantTurn["segments"][number]],
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
          seg.step = { ...seg.step, status: patch.status as "done" | "cancelled" };
          if (patch.result !== undefined) seg.step.result = patch.result as string;
        }
        // Tool args update
        if (seg.type === "tool" && patch.args !== undefined) {
          seg.step = { ...seg.step, args: patch.args };
        }
        // Subagent stream
        if (seg.type === "tool" && patch.subagent_stream) {
          seg.step = { ...seg.step, subagent_stream: patch.subagent_stream as AssistantTurn["segments"][number] extends { step: infer S } ? S extends { subagent_stream?: infer SS } ? SS : never : never };
        }
        if (seg.type === "tool" && patch.subagent_stream_status) {
          if (seg.step.subagent_stream) {
            seg.step = {
              ...seg.step,
              subagent_stream: { ...seg.step.subagent_stream, status: patch.subagent_stream_status as "completed" },
            };
          }
        }
        // Cancelled
        if (patch.cancelled_ids && Array.isArray(patch.cancelled_ids)) {
          return {
            ...t,
            segments: segs.map((s) =>
              s.type === "tool" && (patch.cancelled_ids as string[]).includes(s.step.id)
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
  refreshThreads: () => Promise<void>;
  onUpdate: (updater: (prev: ChatEntry[]) => ChatEntry[]) => void;
  loading: boolean;
  runStarted?: boolean;
  /** display_seq from GET response — skip deltas with _display_seq <= this */
  displaySeq: number;
}

export interface DisplayDeltaState {
  runtimeStatus: StreamStatus | null;
  isRunning: boolean;
}

export interface DisplayDeltaActions {
  handleSendMessage: (message: string) => Promise<void>;
  handleStopStreaming: () => Promise<void>;
}

export function useDisplayDeltas(
  deps: DisplayDeltaDeps,
): DisplayDeltaState & DisplayDeltaActions {
  const { threadId, refreshThreads, onUpdate, loading, runStarted, displaySeq } = deps;

  const [sendPending, setSendPending] = useState(false);

  const { isRunning: streamIsRunning, runtimeStatus, subscribe } =
    useThreadStream(threadId, { loading, refreshThreads, runStarted });

  const isRunning = streamIsRunning || sendPending;

  useEffect(() => {
    if (streamIsRunning) setSendPending(false);
  }, [streamIsRunning]);

  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;
  const displaySeqRef = useRef(displaySeq);
  displaySeqRef.current = displaySeq;

  // Subscribe to display_delta events only
  useEffect(() => {
    return subscribe((event) => {
      if (event.type !== "display_delta") return;
      const delta = event.data as DisplayDelta | undefined;
      if (!delta || !delta.type) return;

      // @@@display-seq-dedup — skip stale deltas replayed from ring buffer
      const deltaSeq = (delta as any)._display_seq;
      if (typeof deltaSeq === "number" && deltaSeq <= displaySeqRef.current) return;
      flushSync(() => {
        onUpdateRef.current((prev) => applyDelta(prev, delta));
      });
    });
  }, [subscribe]);

  const handleSendMessage = useCallback(
    async (message: string) => {
      // No optimistic user entry — backend emits user_message event via SSE,
      // which display_builder converts to append_entry delta.
      setSendPending(true);
      try {
        await postRun(threadId, message);
      } catch (err) {
        setSendPending(false);
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
    } catch (err) {
      console.error("Failed to cancel run:", err);
    }
  }, [threadId]);

  return { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming };
}
