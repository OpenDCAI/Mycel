import { useCallback, useEffect, useRef, useState } from "react";
import {
  getThread,
  type ChatEntry,
  type SandboxInfo,
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

export function useThreadData(threadId: string | undefined, skipInitialLoad = false, initialEntries?: ChatEntry[], _showHidden = false): ThreadDataState & ThreadDataActions {
  const [entries, setEntries] = useState<ChatEntry[]>(initialEntries ?? []);
  const [activeSandbox, setActiveSandbox] = useState<SandboxInfo | null>(null);
  const [loading, setLoading] = useState(!skipInitialLoad);
  const [displaySeq, setDisplaySeq] = useState(0);

  const loadThread = useCallback(async (id: string, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const thread = await getThread(id);
      // @@@display-builder — backend returns pre-computed entries + display_seq
      setEntries((thread.entries ?? []) as ChatEntry[]);
      setDisplaySeq((thread as any).display_seq ?? 0);
      const sandbox = thread.sandbox;
      setActiveSandbox(sandbox && typeof sandbox === "object" ? (sandbox as SandboxInfo) : null);
    } catch (err) {
      console.error("[useThreadData] Failed to load thread:", err);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  const refreshThread = useCallback(async () => {
    if (!threadId) return;
    await loadThread(threadId, true);
  }, [threadId, loadThread]);

  // Load thread data when threadId or showHidden changes
  useEffect(() => {
    if (!threadId) {
      setEntries([]);
      setActiveSandbox(null);
      setLoading(false);
      return;
    }
    if (skipInitialLoad) {
      console.log('[useThreadData] Skipping initial load for new thread');
      setLoading(false);
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
