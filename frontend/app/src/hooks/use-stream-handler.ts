import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import {
  cancelRun,
  postRun,
  type AssistantTurn,
  type ChatEntry,
  type NoticeMessage,
  type NotificationType,
  type StreamStatus,
} from "../api";
import { processStreamEvent } from "./stream-event-handlers";
import { useThreadStream } from "./use-thread-stream";
import { makeId } from "./utils";

interface StreamHandlerDeps {
  threadId: string;
  refreshThreads: () => Promise<void>;
  onUpdate: (updater: (prev: ChatEntry[]) => ChatEntry[]) => void;
  /** True while useThreadData is loading the snapshot — connection waits for this. */
  loading: boolean;
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
  if (last?.role === "assistant" && (last as AssistantTurn).streaming) {
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
  const { threadId, refreshThreads, onUpdate, loading, runStarted } = deps;

  const [sendPending, setSendPending] = useState(false);

  const { isRunning: streamIsRunning, runtimeStatus, subscribe } =
    useThreadStream(threadId, { loading, refreshThreads, runStarted });

  const isRunning = streamIsRunning || sendPending;

  useEffect(() => {
    if (streamIsRunning) setSendPending(false);
  }, [streamIsRunning]);

  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;
  const refreshRef = useRef(refreshThreads);
  refreshRef.current = refreshThreads;

  /**
   * Active turn ID. Set by handleSendMessage (temp then server ID).
   * For auto-reconnect, set lazily on first non-status event.
   *
   * CRITICAL: must be set SYNCHRONOUSLY via flushSync.
   */
  const turnIdRef = useRef<string>("");
  const hasBoundRef = useRef(false);

  useEffect(() => {
    function ensureReconnectTurn() {
      const fallbackId = makeId("reconnect-turn");
      flushSync(() => {
        onUpdateRef.current((prev) => {
          const { entries, turnId } = applyReconnectTurn(prev, fallbackId);
          turnIdRef.current = turnId;
          return entries;
        });
      });
    }

    return subscribe((event) => {
      // notice: standalone entry
      if (event.type === "notice") {
        const d = (event.data ?? {}) as { content?: string; notification_type?: string; source?: string };
        if (d.source === "external") return;
        const noticeEntry: NoticeMessage = {
          id: makeId("stream-notice"),
          role: "notice",
          content: d.content ?? "",
          notification_type: d.notification_type as NotificationType | undefined,
          timestamp: Date.now(),
        };
        onUpdateRef.current((prev) => [...prev, noticeEntry]);
        return;
      }

      // run_start: create turn for visible runs
      if (event.type === "run_start") {
        const d = (event.data ?? {}) as { showing?: boolean };
        if (d.showing !== false) {
          ensureReconnectTurn();
        }
        return;
      }

      // run_done: finalize current turn
      if (event.type === "run_done") {
        const doneId = turnIdRef.current;
        if (doneId) {
          onUpdateRef.current((prev) =>
            prev.map((e) =>
              e.id === doneId && e.role === "assistant"
                ? { ...e, streaming: false, endTimestamp: Date.now() } as AssistantTurn
                : e,
            ),
          );
        }
        turnIdRef.current = "";
        hasBoundRef.current = false;
        return;
      }

      // @@@per-event-showing — each content event carries its own `showing`.
      // Skip hidden events (frontend decides, same logic as mapBackendEntries).
      const eventData = (event.data ?? {}) as { showing?: boolean; is_tell_owner?: boolean };
      if (eventData.showing === false && !eventData.is_tell_owner) {
        return;
      }

      // Auto-reconnect: create turn for visible content events
      const TURN_CONTENT_EVENTS = new Set(["text", "tool_call", "tool_result", "error", "cancelled", "retry"]);
      if (!turnIdRef.current && TURN_CONTENT_EVENTS.has(event.type)) {
        ensureReconnectTurn();
      }

      const { messageId } = processStreamEvent(
        event,
        turnIdRef.current,
        onUpdateRef.current,
        () => {},
      );

      // Bind temporary turn ID to server-assigned message ID (first time only)
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

      const prevTurnId = turnIdRef.current;
      if (prevTurnId) {
        onUpdateRef.current((prev) =>
          prev.map((e) =>
            e.id === prevTurnId && e.role === "assistant"
              ? { ...e, streaming: false, endTimestamp: Date.now() } as AssistantTurn
              : e,
          ),
        );
      }
      turnIdRef.current = tempTurnId;
      hasBoundRef.current = false;

      flushSync(() => {
        onUpdateRef.current((prev) => [...prev, userEntry, assistantTurn]);
        setSendPending(true);
      });

      try {
        await postRun(threadId, message);
      } catch (err) {
        setSendPending(false);
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
  }, [threadId]);

  return { runtimeStatus, isRunning, handleSendMessage, handleStopStreaming };
}
