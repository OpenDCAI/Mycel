import { useCallback, useEffect, useState } from "react";
import {
  getThreadLease,
  pauseThreadSandbox,
  resumeThreadSandbox,
  type SandboxInfo,
} from "../api";

interface SandboxManagerDeps {
  activeThreadId: string | null;
  isStreaming: boolean;
  activeSandbox: SandboxInfo | null;
  setActiveSandbox: React.Dispatch<React.SetStateAction<SandboxInfo | null>>;
  loadThread: (threadId: string) => Promise<void>;
}

export interface SandboxManagerState {
  sandboxActionError: string | null;
}

export interface SandboxManagerActions {
  handlePauseSandbox: () => Promise<void>;
  handleResumeSandbox: () => Promise<void>;
}

export function useSandboxManager(deps: SandboxManagerDeps): SandboxManagerState & SandboxManagerActions {
  const { activeThreadId, isStreaming, activeSandbox, setActiveSandbox, loadThread } = deps;
  const [sandboxActionError, setSandboxActionError] = useState<string | null>(null);

  // Poll sandbox status while streaming (remote sandboxes only)
  useEffect(() => {
    if (!isStreaming || !activeThreadId || !activeSandbox || activeSandbox.type === "local") return;
    let cancelled = false;
    const threadId = activeThreadId;

    const refreshSandboxStatus = async () => {
      try {
        const lease = await getThreadLease(threadId);
        if (cancelled) return;
        const status = lease.instance?.state ?? null;
        setActiveSandbox((prev) => {
          if (!prev) return prev;
          if (prev.type === "local") return prev;
          if (prev.status === status) return prev;
          return { ...prev, status };
        });
      } catch {
        // ignore transient polling errors
      }
    };

    void refreshSandboxStatus();
    const timer = window.setInterval(() => {
      void refreshSandboxStatus();
    }, 1500);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isStreaming, activeThreadId, activeSandbox?.type, setActiveSandbox]);

  const handlePauseSandbox = useCallback(async () => {
    if (!activeThreadId) return;
    setSandboxActionError(null);
    try {
      await pauseThreadSandbox(activeThreadId);
      await loadThread(activeThreadId);
    } catch (e) {
      setSandboxActionError(e instanceof Error ? e.message : String(e));
    }
  }, [activeThreadId, loadThread]);

  const handleResumeSandbox = useCallback(async () => {
    if (!activeThreadId) return;
    setSandboxActionError(null);
    try {
      await resumeThreadSandbox(activeThreadId);
      await loadThread(activeThreadId);
    } catch (e) {
      setSandboxActionError(e instanceof Error ? e.message : String(e));
    }
  }, [activeThreadId, loadThread]);

  return { sandboxActionError, handlePauseSandbox, handleResumeSandbox };
}
