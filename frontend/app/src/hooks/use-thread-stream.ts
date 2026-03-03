import { useCallback, useEffect, useRef, useState } from "react";
import { getThreadRuntime, streamActivityEvents, streamEvents, type StreamStatus } from "../api";
import type { StreamEvent } from "../api/types";

export type ConnectionPhase =
  | "idle"            // no active connection
  | "connecting"      // establishing main SSE
  | "streaming"       // receiving main SSE events
  | "activity-grace"  // main SSE closed, watching activity SSE for up to 5s
  | "reconnecting";   // withReconnection handling network retry internally

export interface UseThreadStreamResult {
  phase: ConnectionPhase;
  isRunning: boolean;
  runtimeStatus: StreamStatus | null;
  /** Trigger a new main SSE connection (called by handleSendMessage or auto-reconnect). */
  connect: (startSeq?: number) => void;
  /** Abort the current connection and set phase to idle. */
  disconnect: () => void;
  /** Subscribe to all dispatched stream events. Returns an unsubscribe function. */
  subscribe: (handler: (event: StreamEvent) => void) => () => void;
}

/** Grace period after main SSE closes before we give up waiting for activity events. */
const GRACE_MS = 5_000;

/**
 * Unified SSE connection manager for a single thread.
 *
 * Manages:
 * - Main SSE stream (`/runs/events`) with built-in reconnection
 * - Activity SSE grace period (`/activity/events`) after main stream closes
 * - Auto-reconnect when `new_run` event arrives during activity-grace
 * - Initialization: check runtime state on mount and auto-connect if active
 */
export function useThreadStream(
  threadId: string,
  deps: { loading: boolean; refreshThreads: () => Promise<void> },
): UseThreadStreamResult {
  const { loading, refreshThreads } = deps;

  const [phase, setPhase] = useState<ConnectionPhase>("idle");
  const [isRunning, setIsRunning] = useState(false);
  const [runtimeStatus, setRuntimeStatus] = useState<StreamStatus | null>(null);

  /** Single AbortController for whichever connection is currently active. */
  const acRef = useRef<AbortController | null>(null);
  const refreshRef = useRef(refreshThreads);
  refreshRef.current = refreshThreads;

  /** Event subscribers set — never recreated, always current. */
  const subscribers = useRef<Set<(event: StreamEvent) => void>>(new Set());

  const subscribe = useCallback((handler: (event: StreamEvent) => void) => {
    subscribers.current.add(handler);
    return () => subscribers.current.delete(handler);
  }, []);

  const disconnect = useCallback(() => {
    acRef.current?.abort();
    acRef.current = null;
    setIsRunning(false);
    setPhase("idle");
  }, []);

  /** Start the main SSE connection. Aborts any existing connection first. */
  const connect = useCallback((startSeq = 0) => {
    // Abort existing connection (main or activity-grace)
    acRef.current?.abort();

    const ac = new AbortController();
    acRef.current = ac;
    setPhase("connecting");
    setIsRunning(true);

    void (async () => {
      try {
        setPhase("streaming");
        await streamEvents(
          threadId,
          (event) => {
            // Update runtime status from status events
            if (event.type === "status" && event.data) {
              setRuntimeStatus(event.data as StreamStatus);
            }
            // Dispatch all events to subscribers
            for (const h of subscribers.current) h(event);
          },
          ac.signal,
          startSeq,
        );

        if (ac.signal.aborted) return;

        // Main stream ended naturally → enter activity-grace phase
        setIsRunning(false);
        setPhase("activity-grace");

        const graceAc = new AbortController();
        acRef.current = graceAc;
        let newRunDetected = false;

        // Auto-close after GRACE_MS if no new_run event arrives
        const graceTimer = setTimeout(() => graceAc.abort(), GRACE_MS);

        try {
          await streamActivityEvents(
            threadId,
            (event) => {
              // Dispatch activity events to subscribers
              for (const h of subscribers.current) h(event);

              if (event.type === "new_run") {
                // Background task triggered a continuation run
                newRunDetected = true;
                clearTimeout(graceTimer);
                graceAc.abort();
              } else if (event.type === "run_done") {
                // Continuation run finished — refresh thread list
                void refreshRef.current();
              }
            },
            graceAc.signal,
          );
        } finally {
          clearTimeout(graceTimer);
          // Only reset to idle if nothing else took over the connection
          if (!newRunDetected && (acRef.current === graceAc || acRef.current === null)) {
            setPhase("idle");
          }
        }

        if (newRunDetected) {
          // Refresh thread list then reconnect main SSE for the continuation run
          await refreshRef.current();
          connect(0);
        }
      } catch (err) {
        if (ac.signal.aborted) return;
        console.error("[useThreadStream] stream error:", err);
        setIsRunning(false);
        setPhase("idle");
      }
    })();
  }, [threadId]); // threadId is stable per component mount (key={threadId} on ChatPage)

  // Auto-connect on init when loading finishes: check runtime and connect if active
  useEffect(() => {
    if (loading) return;

    void (async () => {
      try {
        const runtime = await getThreadRuntime(threadId);
        if (runtime) setRuntimeStatus(runtime);
        const isActive = runtime?.state?.state === "active";
        if (isActive) {
          connect(runtime?.last_seq ?? 0);
        }
      } catch (err) {
        // Non-fatal: runtime check failed, stay idle
        console.error("[useThreadStream] init runtime check failed:", err);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, loading]);

  // Abort connection when threadId changes or component unmounts
  useEffect(() => {
    return () => {
      acRef.current?.abort();
    };
  }, [threadId]);

  // Graceful cleanup on page unload
  useEffect(() => {
    const cleanup = () => acRef.current?.abort();
    window.addEventListener("beforeunload", cleanup);
    return () => window.removeEventListener("beforeunload", cleanup);
  }, []);

  return { phase, isRunning, runtimeStatus, connect, disconnect, subscribe };
}
