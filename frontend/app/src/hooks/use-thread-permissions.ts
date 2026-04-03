import { useCallback, useEffect, useState } from "react";
import {
  getThreadPermissions,
  resolveThreadPermission,
  type PermissionRequest,
} from "../api";

export interface ThreadPermissionsState {
  requests: PermissionRequest[];
  loading: boolean;
  resolvingId: string | null;
}

export interface ThreadPermissionsActions {
  refreshPermissions: () => Promise<void>;
  resolvePermission: (
    requestId: string,
    decision: "allow" | "deny",
    message?: string,
  ) => Promise<void>;
}

export function useThreadPermissions(threadId: string | undefined): ThreadPermissionsState & ThreadPermissionsActions {
  const [requests, setRequests] = useState<PermissionRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);

  const refreshPermissions = useCallback(async () => {
    if (!threadId) {
      setRequests([]);
      return;
    }
    setLoading(true);
    try {
      const payload = await getThreadPermissions(threadId);
      setRequests(payload.requests ?? []);
    } catch (err) {
      console.error("[useThreadPermissions] Failed to load permissions:", err);
    } finally {
      setLoading(false);
    }
  }, [threadId]);

  const resolvePermissionRequest = useCallback(
    async (requestId: string, decision: "allow" | "deny", message?: string) => {
      if (!threadId) return;
      setResolvingId(requestId);
      try {
        await resolveThreadPermission(threadId, requestId, decision, message);
        const payload = await getThreadPermissions(threadId);
        setRequests(payload.requests ?? []);
      } finally {
        setResolvingId(null);
      }
    },
    [threadId],
  );

  useEffect(() => {
    if (!threadId) {
      setRequests([]);
      setLoading(false);
      return;
    }
    void refreshPermissions();

    // @@@permission-poll-bridge - permission requests are thread-scoped runtime
    // state, but they are not first-class SSE events yet. Poll the small
    // thread endpoint so ask-mode is owner-visible without inventing a second
    // client-side state source.
    const timer = window.setInterval(() => {
      void refreshPermissions();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [threadId, refreshPermissions]);

  return {
    requests,
    loading,
    resolvingId,
    refreshPermissions,
    resolvePermission: resolvePermissionRequest,
  };
}
