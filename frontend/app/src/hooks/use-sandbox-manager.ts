import { useEffect } from "react";
import {
  getThreadLease,
  type SandboxInfo,
} from "../api";

interface SandboxManagerDeps {
  activeThreadId: string | null;
  isStreaming: boolean;
  activeSandbox: SandboxInfo | null;
  setActiveSandbox: React.Dispatch<React.SetStateAction<SandboxInfo | null>>;
}

export function useSandboxManager(deps: SandboxManagerDeps): void {
  const { activeThreadId, isStreaming, activeSandbox, setActiveSandbox } = deps;

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
  }, [isStreaming, activeThreadId, activeSandbox, setActiveSandbox]);
}
