import { useCallback, useEffect, useState } from "react";
import {
  createThread,
  deleteThread,
  listSandboxTypes,
  listThreads,
  type SandboxType,
  type ThreadSummary,
} from "../api";

export interface ThreadManagerState {
  threads: ThreadSummary[];
  sandboxTypes: SandboxType[];
  selectedSandbox: string;
  loading: boolean;
}

export interface ThreadManagerActions {
  setSelectedSandbox: (name: string) => void;
  setThreads: React.Dispatch<React.SetStateAction<ThreadSummary[]>>;
  refreshThreads: () => Promise<void>;
  handleCreateThread: (sandbox?: string, cwd?: string, agent?: string) => Promise<string>;
  handleDeleteThread: (threadId: string) => Promise<void>;
}

export function useThreadManager(): ThreadManagerState & ThreadManagerActions {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [sandboxTypes, setSandboxTypes] = useState<SandboxType[]>([{ name: "local", available: true }]);
  const [selectedSandbox, setSelectedSandbox] = useState("local");
  const [loading, setLoading] = useState(true);

  const refreshThreads = useCallback(async () => {
    const rows = await listThreads();
    setThreads(rows);
  }, []);

  // Bootstrap: load sandbox types + threads on mount
  useEffect(() => {
    void (async () => {
      try {
        const [types] = await Promise.all([listSandboxTypes(), refreshThreads()]);
        setSandboxTypes(types);
        const preferred = types.find((t) => t.available)?.name ?? "local";
        setSelectedSandbox(preferred);
      } catch {
        // ignore bootstrap errors in UI; user can retry by action
      } finally {
        setLoading(false);
      }
    })();
  }, [refreshThreads]);

  const handleCreateThread = useCallback(async (sandbox?: string, cwd?: string, agent?: string): Promise<string> => {
    const type = sandbox ?? selectedSandbox;
    const thread = await createThread(type, cwd, agent);
    setThreads((prev) => [thread, ...prev]);
    setSelectedSandbox(type);
    return thread.thread_id;
  }, [selectedSandbox]);

  const handleDeleteThread = useCallback(
    async (threadId: string) => {
      await deleteThread(threadId);
      setThreads(prev => prev.filter((t) => t.thread_id !== threadId));
    },
    [],
  );

  return {
    threads, sandboxTypes, selectedSandbox, loading,
    setSelectedSandbox, setThreads,
    refreshThreads, handleCreateThread, handleDeleteThread,
  };
}
