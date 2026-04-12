import { useCallback, useEffect, useState } from "react";
import {
  createThread,
  getDefaultThread,
  listSandboxTypes,
  listThreads,
  type SandboxType,
  type ThreadSummary,
} from "../api";

let bootstrapInflight: Promise<{
  sandboxTypes: SandboxType[];
  threads: ThreadSummary[];
}> | null = null;

export interface ThreadManagerState {
  threads: ThreadSummary[];
  sandboxTypes: SandboxType[];
  selectedSandbox: string;
  loading: boolean;
  bootstrapError: string | null;
}

export interface ThreadManagerActions {
  refreshThreads: () => Promise<void>;
  handleCreateThread: (
    sandbox?: string,
    cwd?: string,
    agentUserId?: string,
    model?: string,
    leaseId?: string,
    recipeId?: string,
  ) => Promise<string>;
  handleGetDefaultThread: (agentUserId: string, signal?: AbortSignal) => Promise<ThreadSummary | null>;
}

function upsertThread(prev: ThreadSummary[], thread: ThreadSummary): ThreadSummary[] {
  const next = prev.filter((item) => item.thread_id !== thread.thread_id);
  return [thread, ...next];
}

function loadThreadBootstrap() {
  if (bootstrapInflight) return bootstrapInflight;
  bootstrapInflight = Promise.all([listSandboxTypes(), listThreads()])
    .then(([sandboxTypes, threads]) => ({ sandboxTypes, threads }))
    .finally(() => {
      bootstrapInflight = null;
    });
  return bootstrapInflight;
}

export function useThreadManager(): ThreadManagerState & ThreadManagerActions {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [sandboxTypes, setSandboxTypes] = useState<SandboxType[]>([{ name: "local", available: true }]);
  const [selectedSandbox, setSelectedSandbox] = useState("local");
  const [loading, setLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  const refreshThreads = useCallback(async () => {
    const rows = await listThreads();
    setThreads(rows);
  }, []);

  // Bootstrap: load sandbox types + threads on mount
  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        // @@@thread-bootstrap-singleflight - /threads now redirects before AppLayout mounts,
        // but dev StrictMode still double-mounts the thread shell. Reuse the first
        // bootstrap request so sidebar threads/provider inventory do not refetch twice.
        const { sandboxTypes: types, threads: rows } = await loadThreadBootstrap();
        if (cancelled) return;
        setThreads(rows);
        setSandboxTypes(types);
        setBootstrapError(null);
        const preferred = types.find((t) => t.available)?.name ?? "local";
        setSelectedSandbox(preferred);
      } catch (err) {
        if (!cancelled) {
          setBootstrapError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleCreateThread = useCallback(async (
    sandbox?: string,
    cwd?: string,
    agentUserId?: string,
    model?: string,
    leaseId?: string,
    recipeId?: string,
  ): Promise<string> => {
    const type = sandbox ?? selectedSandbox;
    const thread = await createThread({ sandbox: type, cwd, agentUserId: agentUserId ?? "", model, leaseId, recipeId });
    setThreads((prev) => upsertThread(prev, thread));
    setSelectedSandbox(type);
    return thread.thread_id;
  }, [selectedSandbox]);

  // @@@template-default-thread-entry - this hook resolves a template entry to its
  // current default thread without changing the existing backend wire name yet.
  const handleGetDefaultThread = useCallback(async (agentUserId: string, signal?: AbortSignal): Promise<ThreadSummary | null> => {
    const thread = await getDefaultThread(agentUserId, signal);
    if (thread) {
      setThreads((prev) => upsertThread(prev, thread));
    }
    return thread;
  }, []);

  return {
    threads, sandboxTypes, selectedSandbox, loading, bootstrapError,
    refreshThreads, handleCreateThread, handleGetDefaultThread,
  };
}
