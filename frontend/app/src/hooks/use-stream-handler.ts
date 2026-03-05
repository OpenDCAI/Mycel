import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  cancelRun,
  postRun,
  type AssistantTurn,
  type ChatEntry,
  type StreamStatus,
} from "../api";
import type { StreamEvent } from "../api/types";
import { processStreamEvent } from "./stream-event-handlers";
import { useThreadStream } from "./use-thread-stream";
import { makeId } from "./utils";

interface StreamHandlerDeps {
  threadId: string;
  refreshThreads: () => Promise<void>;
  onUpdate: (updater: (prev: ChatEntry[]) => ChatEntry[]) => void;
  /** True while useThreadData is loading the snapshot — connection waits for this. */
  loading: boolean;
  /** Callback for activity events (command_progress, background_task_*). */
  onActivityEvent?: (event: StreamEvent) => void;
  /**
   * True when navigating from a new-chat creation (postRun already called in NewChatPage).
   * Tells useThreadStream to connect from seq=0 instead of last_seq, so we don't miss
   * events that were emitted between postRun() and ChatPage mount.
   */
  runStarted?: boolean;
}

export interface StreamHandlerState {
  runtimeStatus: StreamStatus | null;
  isRunning: boolean;
}

export interface StreamHandlerActions {
  handleSendMessage: (message: string) => Promise<void>;
  handleStopStreaming: () => Promise<void>;
}

/**
 * Reuse the last entry if it's an assistant turn (mark it streaming);
 * otherwise create a new assistant turn.
 */
function applyReconnectTurn(
  prev: ChatEntry[],
  fallbackId: string,
): { entries: ChatEntry[]; turnId: string } {
  const last = prev[prev.length - 1];
  if (last?.role === "assistant") {
    return {
      entries: prev.map((e) =>
        e.id === last.id && e.role === "assistant"
          ? { ...e, streaming: true } as AssistantTurn
          : e,
      ),
      turnId: last.id,
    };
  }
  const newTurn: AssistantTurn = {
    id: fallbackId,
    role: "assistant",
    segments: [],
    timestamp: Date.now(),
    streaming: true,
  };
  return { entries: [...prev, newTurn], turnId: fallbackId };
}

export function useStreamHandler(
  deps: StreamHandlerDeps,
): StreamHandlerState & StreamHandlerActions {
  const { threadId, refreshThreads, onUpdate, loading, onActivityEvent, runStarted } = deps;

  // Local state for immediate UI feedback when user sends a message
  // (covers the window between flushSync and useThreadStream.isRunning becoming true)
  const [sendPending, setSendPending] = useState(false);

  const { isRunning: streamIsRunning, runtimeStatus, subscribe } =
    useThreadStream(threadId, { loading, refreshThreads, runStarted });

  const isRunning = streamIsRunning || sendPending;

  // Clear sendPending once the stream picks up
  useEffect(() => {
    if (streamIsRunning) setSendPending(false);
  }, [streamIsRunning]);

  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;
  const onActivityRef = useRef<((event: StreamEvent) => void) | undefined>(onActivityEvent);
  onActivityRef.current = onActivityEvent;
  const refreshRef = useRef(refreshThreads);
  refreshRef.current = refreshThreads;

  /**
   * Active turn ID. Set by handleSendMessage (temp then server ID).
   * For auto-reconnect, set lazily on first non-status event.
   */
  const turnIdRef = useRef<string>("");
  /**
   * True once the server message_id has been bound to the turn entry.
   * Reset at the start of each new connection.
   */
  const hasBoundRef = useRef(false);

  // Subscribe to stream events → drive UI state
  useEffect(() => {
    console.log("[STREAM-DIAG] subscriber registered");
    return subscribe((event) => {
      console.log(`[STREAM-DIAG] event=${event.type}, turnId=${turnIdRef.current}, hasBound=${hasBoundRef.current}`);
      // run_start: ensure we have an assistant turn ready
      if (event.type === "run_start" && !turnIdRef.current) {
        const fallbackId = makeId("reconnect-turn");
        onUpdateRef.current((prev) => {
          const { entries, turnId } = applyReconnectTurn(prev, fallbackId);
          turnIdRef.current = turnId;
          return entries;
        });
        return;
      }

      // run_done: finalize current turn
      if (event.type === "run_done") {
        const doneId = turnIdRef.current;
        if (doneId) {
          onUpdateRef.current((prev) =>
            prev.map((e) =>
              e.id === doneId && e.role === "assistant"
                ? { ...e, streaming: false } as AssistantTurn
                : e,
            ),
          );
        }
        turnIdRef.current = "";
        hasBoundRef.current = false;
        return;
      }

      // For auto-reconnect: no turn has been created by handleSendMessage.
      // Create or continue the last assistant turn on the first content event.
      if (!turnIdRef.current && event.type !== "status") {
        const fallbackId = makeId("reconnect-turn");
        onUpdateRef.current((prev) => {
          const { entries, turnId } = applyReconnectTurn(prev, fallbackId);
          turnIdRef.current = turnId;
          return entries;
        });
      }

      const { messageId } = processStreamEvent(
        event,
        turnIdRef.current,
        onUpdateRef.current,
        // runtimeStatus is managed by useThreadStream; pass no-op here
        () => {},
        onActivityRef.current,
      );

      // Bind temporary turn ID to the server-assigned message ID (first time only)
      if (messageId && turnIdRef.current && messageId !== turnIdRef.current && !hasBoundRef.current) {
        hasBoundRef.current = true;
        const tempId = turnIdRef.current;
        turnIdRef.current = messageId;
        onUpdateRef.current((prev) =>
          prev.map((e) =>
            e.id === tempId && e.role === "assistant"
              ? { ...e, id: messageId, messageIds: [messageId] } as AssistantTurn
              : e,
          ),
        );
      }
    });
  }, [subscribe]);

  const handleSendMessage = useCallback(
    async (message: string) => {
      const tempTurnId = makeId("turn");
      const userEntry: ChatEntry = {
        id: makeId("user"),
        role: "user",
        content: message,
        timestamp: Date.now(),
      };
      const assistantTurn: AssistantTurn = {
        id: tempTurnId,
        role: "assistant",
        segments: [],
        timestamp: Date.now(),
        streaming: true,
      };

      // Set turn context before connect() so the subscriber knows which turn to update
      turnIdRef.current = tempTurnId;
      hasBoundRef.current = false;

      flushSync(() => {
        onUpdateRef.current((prev) => [...prev, userEntry, assistantTurn]);
        setSendPending(true);
      });

      try {
        await postRun(threadId, message);
        // Connection is persistent — no need to reconnect.
        // run_start event will confirm isRunning.
      } catch (err) {
        setSendPending(false);
        // Show error in the assistant turn
        if (err instanceof Error) {
          onUpdateRef.current((prev) =>
            prev.map((e) =>
              e.id === tempTurnId && e.role === "assistant"
                ? {
                    ...e,
                    streaming: false,
                    segments: [{ type: "text" as const, content: `\n\nError: ${err.message}` }],
                  } as AssistantTurn
                : e,
            ),
          );
        }
        turnIdRef.current = "";
        hasBoundRef.current = false;
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
    // Don't disconnect — persistent connection stays open.
    // cancelled + run_done events will arrive and update state.
  }, [threadId]);

  return { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming };
}
