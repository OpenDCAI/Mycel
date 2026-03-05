import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadRuntime, streamThreadEvents, type StreamStatus } from "../api";
import type { StreamEvent } from "../api/types";

export type ConnectionPhase =
  | "idle"            // not connected
  | "connecting"      // establishing SSE
  | "connected"       // receiving events, may or may not be running
  | "reconnecting"    // network retry
  | "error";          // unrecoverable error (shows "reconnect" button)

export interface UseThreadStreamResult {
  phase: ConnectionPhase;
  isRunning: boolean;
  runtimeStatus: StreamStatus | null;
  /** Establish persistent SSE connection to the thread. */
  connect: (startSeq?: number) => void;
  /** Abort SSE connection. */
  disconnect: () => void;
  /** Subscribe to all dispatched stream events. Returns an unsubscribe function. */
  subscribe: (handler: (event: StreamEvent) => void) => () => void;
}

/**
 * Single persistent SSE connection manager for a thread.
 *
 * One channel: `/api/threads/{id}/events` — survives across runs.
 * `run_start` → isRunning=true, `run_done` → isRunning=false, connection stays open.
 */
export function useThreadStream(
  threadId: string,
  deps: { loading: boolean; refreshThreads: () => Promise<void>; runStarted?: boolean },
): UseThreadStreamResult {
  const { loading, refreshThreads, runStarted } = deps;

  const [phase, setPhase] = useState<ConnectionPhase>("idle");
  const [isRunning, setIsRunning] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<StreamStatus | null>(null);

  /** Single AbortController for the persistent SSE connection. */
  const acRef = useRef<AbortController | null>(null);

  const refreshRef = useRef(refreshThreads);
  refreshRef.current = refreshThreads;

  /** Event subscribers set — never recreated, always current. */
  const subscribers = useRef<Set<(event: StreamEvent) => void>>(new Set());

  const subscribe = useCallback((handler: (event: StreamEvent) => void) => {
    subscribers.current.add(handler);
    return () => subscribers.current.delete(handler);
  }, []);

  /** Establish persistent SSE connection. */
  const connect = useCallback((startSeq = 0) => {
    console.log(`[SSE-DIAG] connect(${startSeq}) called, threadId=${threadId}`);
    acRef.current?.abort();

    const ac = new AbortController();
    acRef.current = ac;
    setPhase("connecting");

    void (async () => {
      try {
        setPhase("connected");
        console.log(`[SSE-DIAG] streamThreadEvents starting, after=${startSeq}`);
        await streamThreadEvents(
          threadId,
          (event) => {
            // Guard: ignore events from aborted connections
            if (ac.signal.aborted) return;
            console.log(`[SSE-DIAG] event received: type=${event.type}, subscribers=${subscribers.current.size}`);
            if (event.type === "status" && event.data) {
              setRuntimeStatus(event.data as StreamStatus);
            }
            if (event.type === "run_start") {
              setIsRunning(true);
            }
            if (event.type === "run_done") {
              setIsRunning(false);
              void refreshRef.current();
            }
            if (event.type === "error") {
              // Don't change isRunning — error events during a run
              // are followed by run_done
            }
            for (const h of subscribers.current) h(event);
          },
          ac.signal,
          startSeq,
        );

        if (ac.signal.aborted) {
          console.log("[SSE-DIAG] streamThreadEvents returned, signal was aborted");
          return;
        }
        // streamThreadEvents returned (max attempts reached or 4xx error)
        console.log("[SSE-DIAG] streamThreadEvents returned normally → phase=error");
        setPhase("error");
      } catch (err) {
        if (ac.signal.aborted) {
          console.log("[SSE-DIAG] streamThreadEvents threw, signal was aborted");
          return;
        }
        console.error("[SSE-DIAG] connection error:", err);
        setPhase("error");
      }
    })();
  }, [threadId]);

  const disconnect = useCallback(() => {
    acRef.current?.abort();
    acRef.current = null;
    setIsRunning(false);
    setPhase("idle");
  }, []);

  // On mount (after loading): establish persistent connection
  useEffect(() => {
    if (loading) return;

    if (runStarted) {
      // Navigated from NewChatPage: postRun was already called.
      // Connect immediately, the run_start event will set isRunning.
      setIsRunning(true); // optimistic — run_start will confirm
      connect(0);
      // Non-blocking: still fetch runtime for runtimeStatus display
      void getThreadRuntime(threadId)
        .then((rt) => { if (rt) setRuntimeStatus(rt); })
        .catch(() => {});
    } else {
      // Page refresh / direct URL: check runtime then connect
      async function init() {
        try {
          const runtime = await getThreadRuntime(threadId);
          if (runtime) setRuntimeStatus(runtime);
          if (runtime?.state?.state === "active") {
            setIsRunning(true);
          }
          connect(runtime?.last_seq ?? 0);
        } catch (err) {
          console.error("[useThreadStream] init failed:", err);
          connect(0);
        }
      }
      void init();
    }

    return () => {
      console.log("[SSE-DIAG] useEffect cleanup — aborting SSE connection");
      acRef.current?.abort();
      acRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, loading]);

  // Tab visibility: reset reconnection on tab visible
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "visible" && phase === "error") {
        connect(0);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [phase, connect]);

  // Graceful cleanup on page unload
  useEffect(() => {
    const cleanup = () => acRef.current?.abort();
    window.addEventListener("beforeunload", cleanup);
    return () => window.removeEventListener("beforeunload", cleanup);
  }, []);

  return { phase, isRunning, runtimeStatus, connect, disconnect, subscribe };
}
