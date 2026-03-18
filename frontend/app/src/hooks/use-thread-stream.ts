import { useCallback, useEffect, useReducer, useRef } from "react";
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

// ---------------------------------------------------------------------------
// ThreadConnectionManager — imperative SSE lifecycle, framework-agnostic
// ---------------------------------------------------------------------------

class ThreadConnectionManager {
  // --- public state (read-only from outside) ---
  phase: ConnectionPhase = "idle";
  isRunning = false;
  runtimeStatus: StreamStatus | null = null;

  // --- internal ---
  private threadId = "";
  private ac: AbortController | null = null;
  private version = 0;
  private lastSeenSeq = 0; // @@@dedup-events — monotonic seq from backend, skip duplicates
  private subscribers = new Set<(event: StreamEvent) => void>();
  private listener: (() => void) | null = null; // React re-render trigger
  private refreshThreads: (() => Promise<void>) | null = null;

  // --- state-change notification ---
  onChange(fn: () => void) { this.listener = fn; }
  setRefreshThreads(fn: () => Promise<void>) { this.refreshThreads = fn; }

  private notify() { this.listener?.(); }

  private setPhase(p: ConnectionPhase) {
    if (this.phase === p) return;
    this.phase = p;
    this.notify();
  }

  private setRunning(v: boolean) {
    if (this.isRunning === v) return;
    this.isRunning = v;
    this.notify();
  }

  private setStatus(s: StreamStatus | null) {
    this.runtimeStatus = s;
    this.notify();
  }

  // --- core methods ---

  /** Establish persistent SSE connection. Idempotent — aborts any prior connection. */
  connect(startSeq = 0) {
    // @@@dedup-connect — abort previous connection, bump version to invalidate stale callbacks
    this.ac?.abort();

    const ac = new AbortController();
    this.ac = ac;
    const ver = ++this.version;
    this.setPhase("connecting");

    void (async () => {
      try {
        this.setPhase("connected");
        await streamThreadEvents(
          this.threadId,
          (event) => {
            if (this.version !== ver) return; // stale connection
            // @@@dedup-events — skip events with seq we've already seen (React strict mode
            // can open duplicate SSE connections in dev; both deliver the same events).
            const d = (event.data ?? {}) as { _seq?: number };
            if (typeof d._seq === "number") {
              if (d._seq <= this.lastSeenSeq) {
                return;
              }
              this.lastSeenSeq = d._seq;
            }
            if (event.type === "status" && event.data) {
              this.setStatus(event.data as StreamStatus);
            }
            if (event.type === "run_start") {
              this.setRunning(true);
            }
            if (event.type === "run_done") {
              this.setRunning(false);
              void this.refreshThreads?.();
            }
            // error events don't change isRunning — followed by run_done
            for (const h of this.subscribers) h(event);
          },
          ac.signal,
          startSeq,
        );

        if (this.version !== ver) return;
        this.setPhase("error");
      } catch (err) {
        if (this.version !== ver) return;
        console.error("[useThreadStream] connection error:", err);
        this.setPhase("error");
      }
    })();
  }

  /** Abort connection and reset state. */
  disconnect() {
    this.version++; // invalidate all in-flight async callbacks
    this.ac?.abort();
    this.ac = null;
    this.setRunning(false);
    this.setPhase("idle");
  }

  /** runStarted=true path: new run was just posted, connect immediately. */
  initForNewRun(threadId: string) {
    this.threadId = threadId;
    const ver = ++this.version;
    this.setRunning(true);
    this.connect(0);
    void getThreadRuntime(threadId)
      .then((rt) => { if (this.version === ver && rt) this.setStatus(rt); })
      .catch(() => {});
  }

  /** Page refresh / direct URL path: fetch runtime first, then connect. */
  initFromRuntime(threadId: string) {
    this.threadId = threadId;
    const ver = ++this.version;

    void (async () => {
      try {
        const runtime = await getThreadRuntime(threadId);
        if (this.version !== ver) return;
        if (runtime) this.setStatus(runtime);
        if (runtime?.state?.state === "active") {
          this.setRunning(true);
        }
        const startSeq = (runtime?.state?.state === "active" && runtime?.run_start_seq != null)
          ? Math.max(runtime.run_start_seq - 1, 0)
          : (runtime?.last_seq ?? 0);
        this.connect(startSeq);
      } catch (err) {
        if (this.version !== ver) return;
        console.error("[useThreadStream] init failed:", err);
        this.connect(0);
      }
    })();
  }

  subscribe(handler: (event: StreamEvent) => void) {
    this.subscribers.add(handler);
    return () => { this.subscribers.delete(handler); };
  }

  dispose() {
    this.disconnect();
    this.subscribers.clear();
    this.listener = null;
  }
}

// ---------------------------------------------------------------------------
// useThreadStream — thin React wrapper over ThreadConnectionManager
// ---------------------------------------------------------------------------

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
  const [, rerender] = useReducer((x: number) => x + 1, 0);
  const mgrRef = useRef<ThreadConnectionManager | null>(null);
  if (!mgrRef.current) mgrRef.current = new ThreadConnectionManager();
  const mgr = mgrRef.current;

  // Keep refreshThreads callback up-to-date without re-creating the manager
  mgr.setRefreshThreads(refreshThreads);

  // State changes → re-render; dispose on unmount
  useEffect(() => {
    mgr.onChange(rerender);
    return () => mgr.dispose();
  }, [mgr]);

  // Connection lifecycle — driven by threadId/loading/runStarted
  useEffect(() => {
    if (loading) return;
    if (runStarted) {
      mgr.initForNewRun(threadId);
    } else {
      mgr.initFromRuntime(threadId);
    }
    return () => mgr.disconnect();
  }, [mgr, threadId, loading]);

  // Tab visibility: reconnect on error when tab becomes visible
  useEffect(() => {
    const h = () => {
      if (document.visibilityState === "visible" && mgr.phase === "error") {
        mgr.connect(0);
      }
    };
    document.addEventListener("visibilitychange", h);
    return () => document.removeEventListener("visibilitychange", h);
  }, [mgr]);

  // Graceful cleanup on page unload
  useEffect(() => {
    const h = () => mgr.disconnect();
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [mgr]);

  // Stable function references — mgr never changes, so these are created once
  const connectFn = useCallback((seq?: number) => mgr.connect(seq), [mgr]);
  const disconnectFn = useCallback(() => mgr.disconnect(), [mgr]);
  const subscribeFn = useCallback((h: (event: StreamEvent) => void) => mgr.subscribe(h), [mgr]);

  return {
    phase: mgr.phase,
    isRunning: mgr.isRunning,
    runtimeStatus: mgr.runtimeStatus,
    connect: connectFn,
    disconnect: disconnectFn,
    subscribe: subscribeFn,
  };
}
