import { useCallback, useEffect, useState } from "react";
import {
  getThread,
  type ChatEntry,
  type SandboxInfo,
  type ThreadDetail,
} from "../api";

export interface ThreadDataState {
  entries: ChatEntry[];
  activeSandbox: SandboxInfo | null;
  loading: boolean;
  /** Current display_seq from backend — deltas with _display_seq <= this are stale. */
  displaySeq: number;
}

export interface ThreadDataActions {
  setEntries: React.Dispatch<React.SetStateAction<ChatEntry[]>>;
  setActiveSandbox: React.Dispatch<React.SetStateAction<SandboxInfo | null>>;
  loadThread: (threadId: string) => Promise<void>;
  refreshThread: () => Promise<void>;
}

const threadDetailInflight = new Map<string, Promise<ThreadDetail>>();

function isActiveThreadRoute(threadId: string): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path.startsWith("/chat/hire/thread/") && path.endsWith(`/${encodeURIComponent(threadId)}`);
}

function loadThreadDetail(threadId: string): Promise<ThreadDetail> {
  const existing = threadDetailInflight.get(threadId);
  if (existing) return existing;
  const pending = getThread(threadId).finally(() => {
    threadDetailInflight.delete(threadId);
  });
  threadDetailInflight.set(threadId, pending);
  return pending;
}

export function useThreadData(threadId: string | undefined, skipInitialLoad = false, initialEntries?: ChatEntry[]): ThreadDataState & ThreadDataActions {
  const [entries, setEntries] = useState<ChatEntry[]>(initialEntries ?? []);
  const [activeSandbox, setActiveSandbox] = useState<SandboxInfo | null>(null);
  const [loading, setLoading] = useState(!skipInitialLoad);
  const [displaySeq, setDisplaySeq] = useState(0);

  const loadThread = useCallback(async (id: string, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const thread = await loadThreadDetail(id);
      // @@@display-builder — backend returns pre-computed entries + display_seq
      setEntries(thread.entries ?? []);
      setDisplaySeq(thread.display_seq ?? 0);
      const sandbox = thread.sandbox;
      setActiveSandbox(sandbox);
    } catch (err) {
      // @@@thread-route-teardown - browser navigation can leave an abandoned
      // thread fetch resolving after the chat page already moved elsewhere.
      // Only log if this thread page is still the active route.
      if (!isActiveThreadRoute(id)) return;
      console.error("[useThreadData] Failed to load thread:", err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const refreshThread = useCallback(async () => {
    if (!threadId) return;
    await loadThread(threadId, true);
  }, [threadId, loadThread]);

  // Load thread data when threadId changes
  useEffect(() => {
    if (!threadId) {
      setEntries([]);
      setActiveSandbox(null);
      setLoading(false);
      return;
    }
    if (skipInitialLoad) {
      setLoading(false);
      // @@@skip-entries-not-sandbox — skipInitialLoad skips ENTRIES (to avoid
      // overwriting optimistic entries), but we still need sandbox status so
      // TaskProgress shows the correct indicator from the start.
      loadThreadDetail(threadId).then(thread => {
        const sandbox = thread.sandbox;
        setActiveSandbox(sandbox && typeof sandbox === "object" ? (sandbox as SandboxInfo) : null);
      }).catch(() => {});
      return;
    }
    void loadThread(threadId);
  }, [threadId, loadThread, skipInitialLoad]);

  return {
    entries,
    activeSandbox,
    loading,
    displaySeq,
    setEntries,
    setActiveSandbox,
    loadThread,
    refreshThread,
  };
}
