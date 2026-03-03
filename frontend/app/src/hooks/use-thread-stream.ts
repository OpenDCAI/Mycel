import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadRuntime, streamActivityEvents, streamEvents, type StreamStatus } from "../api";
import type { StreamEvent } from "../api/types";

export type ConnectionPhase =
  | "idle"            // no active run stream
  | "connecting"      // establishing main SSE
  | "streaming"       // receiving main SSE events
  | "reconnecting";   // withReconnection handling network retry internally

export interface UseThreadStreamResult {
  phase: ConnectionPhase;
  isRunning: boolean;
  runtimeStatus: StreamStatus | null;
  /** Trigger a new main SSE connection (called by handleSendMessage or auto-reconnect). */
  connect: (startSeq?: number) => void;
  /** Abort the current run stream connection and set phase to idle. */
  disconnect: () => void;
  /** Subscribe to all dispatched stream events. Returns an unsubscribe function. */
  subscribe: (handler: (event: StreamEvent) => void) => () => void;
}

/**
 * Unified SSE connection manager for a single thread.
 *
 * Two independent channels:
 * - Run stream (`/runs/events`): temporary, per-run, manages isRunning state
 * - Notification stream (`/activity/events`): permanent, page-lifetime, handles
 *   new_run / background_task_done / run_done events without any grace period
 *
 * This eliminates the grace-period race condition where background tasks completing
 * after 5s would miss the notification window.
 */
export function useThreadStream(
  threadId: string,
  deps: { loading: boolean; refreshThreads: () => Promise<void>; runStarted?: boolean },
): UseThreadStreamResult {
  const { loading, refreshThreads, runStarted } = deps;

  const [phase, setPhase] = useState<ConnectionPhase>("idle");
  const [isRunning, setIsRunning] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<StreamStatus | null>(null);

  /** AbortController for the run stream only (temporary). */
  const runAcRef = useRef<AbortController | null>(null);
  /** AbortController for the notification stream (permanent, page-lifetime). */
  const notifyAcRef = useRef<AbortController | null>(null);

  const refreshRef = useRef(refreshThreads);
  refreshRef.current = refreshThreads;

  /** Event subscribers set — never recreated, always current. */
  const subscribers = useRef<Set<(event: StreamEvent) => void>>(new Set());

  const subscribe = useCallback((handler: (event: StreamEvent) => void) => {
    subscribers.current.add(handler);
    return () => subscribers.current.delete(handler);
  }, []);

  /** Start the main SSE (run stream). Aborts any existing run stream first. */
  const connect = useCallback((startSeq = 0) => {
    runAcRef.current?.abort();

    const ac = new AbortController();
    runAcRef.current = ac;
    setPhase("connecting");
    setIsRunning(true);

    void (async () => {
      try {
        setPhase("streaming");
        await streamEvents(
          threadId,
          (event) => {
            if (event.type === "status" && event.data) {
              setRuntimeStatus(event.data as StreamStatus);
            }
            for (const h of subscribers.current) h(event);
          },
          ac.signal,
          startSeq,
        );

        if (ac.signal.aborted) return;

        // Run stream ended naturally — mark idle, notification stream stays open
        setIsRunning(false);
        setPhase("idle");
      } catch (err) {
        if (ac.signal.aborted) return;
        console.error("[useThreadStream] run stream error:", err);
        setIsRunning(false);
        setPhase("idle");
      }
    })();
  }, [threadId]);

  const disconnect = useCallback(() => {
    runAcRef.current?.abort();
    runAcRef.current = null;
    setIsRunning(false);
    setPhase("idle");
  }, []);

  // On mount (after loading): check runtime + start permanent notification stream
  useEffect(() => {
    if (loading) return;

    if (runStarted) {
      // Navigated from NewChatPage: postRun was already called there.
      // Connect IMMEDIATELY from seq=0 — do NOT await getThreadRuntime().
      // A fast run may finish within the ~200ms network round-trip, making
      // state !== "active" and causing connect() to be skipped entirely.
      connect(0);
      // Still fetch runtime for runtimeStatus display (non-blocking)
      void getThreadRuntime(threadId).then((rt) => { if (rt) setRuntimeStatus(rt); }).catch(() => {});
    } else {
      // Page refresh / direct URL: check if a run is already active
      void (async () => {
        try {
          const runtime = await getThreadRuntime(threadId);
          if (runtime) setRuntimeStatus(runtime);
          if (runtime?.state?.state === "active") {
            connect(runtime.last_seq ?? 0);
          }
        } catch (err) {
          console.error("[useThreadStream] init runtime check failed:", err);
        }
      })();
    }

    // Permanent notification stream — stays open for the entire page lifetime.
    // Handles: new_run (background task → continuation run), run_done, activity events.
    const notifyAc = new AbortController();
    notifyAcRef.current = notifyAc;

    void streamActivityEvents(
      threadId,
      (event) => {
        // Dispatch to all subscribers (activities panel etc.)
        for (const h of subscribers.current) h(event);

        if (event.type === "new_run") {
          // A background task triggered a continuation run — connect run stream
          void refreshRef.current();
          connect(0);
        } else if (event.type === "run_done") {
          // Continuation run finished — refresh thread list
          void refreshRef.current();
        }
      },
      notifyAc.signal,
    );

    return () => {
      notifyAc.abort();
      notifyAcRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, loading]);

  // Abort run stream when threadId changes or component unmounts
  useEffect(() => {
    return () => {
      runAcRef.current?.abort();
    };
  }, [threadId]);

  // Graceful cleanup on page unload
  useEffect(() => {
    const cleanup = () => {
      runAcRef.current?.abort();
      notifyAcRef.current?.abort();
    };
    window.addEventListener("beforeunload", cleanup);
    return () => window.removeEventListener("beforeunload", cleanup);
  }, []);

  return { phase, isRunning, runtimeStatus, connect, disconnect, subscribe };
}
