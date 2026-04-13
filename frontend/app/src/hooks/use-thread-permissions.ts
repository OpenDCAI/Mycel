import { useCallback, useEffect, useRef, useState } from "react";
import {
  addThreadPermissionRule,
  getThreadPermissions,
  removeThreadPermissionRule,
  resolveThreadPermission,
  type AskUserAnswer,
  type PermissionRequest,
  type ThreadPermissionRules,
  type PermissionRuleBehavior,
} from "../api";

interface ThreadPermissionsState {
  requests: PermissionRequest[];
  sessionRules: ThreadPermissionRules;
  managedOnly: boolean;
  loading: boolean;
  resolvingId: string | null;
}

interface ThreadPermissionsActions {
  refreshPermissions: () => Promise<void>;
  resolvePermission: (
    requestId: string,
    decision: "allow" | "deny",
    message?: string,
    answers?: AskUserAnswer[],
    annotations?: Record<string, unknown>,
  ) => Promise<void>;
  addSessionRule: (behavior: PermissionRuleBehavior, toolName: string) => Promise<void>;
  removeSessionRule: (behavior: PermissionRuleBehavior, toolName: string) => Promise<void>;
}

function isActiveThreadRoute(threadId: string): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path.startsWith("/chat/hire/thread/") && path.endsWith(`/${encodeURIComponent(threadId)}`);
}

export function useThreadPermissions(threadId: string | undefined): ThreadPermissionsState & ThreadPermissionsActions {
  const [requests, setRequests] = useState<PermissionRequest[]>([]);
  const [sessionRules, setSessionRules] = useState<ThreadPermissionRules>({ allow: [], deny: [], ask: [] });
  const [managedOnly, setManagedOnly] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const refreshGenerationRef = useRef(0);
  const requestAbortRef = useRef<AbortController | null>(null);

  const refreshPermissions = useCallback(async () => {
    if (!threadId) {
      setRequests([]);
      setSessionRules({ allow: [], deny: [], ask: [] });
      setManagedOnly(false);
      return;
    }
    // @@@permission-refresh-generation - route switches can leave an old
    // permissions fetch resolving after the chat page has already unmounted.
    // Only the latest in-scope refresh is allowed to touch state or logs.
    const generation = ++refreshGenerationRef.current;
    requestAbortRef.current?.abort();
    const controller = new AbortController();
    requestAbortRef.current = controller;
    setLoading(true);
    try {
      const payload = await getThreadPermissions(threadId, controller.signal);
      if (refreshGenerationRef.current !== generation) return;
      setRequests(payload.requests);
      setSessionRules(payload.session_rules);
      setManagedOnly(payload.managed_only);
    } catch (err) {
      if (controller.signal.aborted) return;
      if (refreshGenerationRef.current !== generation) return;
      // @@@permission-route-teardown - browser navigation can tear down the old
      // thread page before React cleanup runs, which surfaces as a generic
      // Failed to fetch from the abandoned route. Only log if this thread page
      // is still the active route.
      if (!isActiveThreadRoute(threadId)) return;
      console.error("[useThreadPermissions] Failed to load permissions:", err);
    } finally {
      if (requestAbortRef.current === controller) {
        requestAbortRef.current = null;
      }
      if (refreshGenerationRef.current === generation) {
        setLoading(false);
      }
    }
  }, [threadId]);

  const resolvePermissionRequest = useCallback(
    async (
      requestId: string,
      decision: "allow" | "deny",
      message?: string,
      answers?: AskUserAnswer[],
      annotations?: Record<string, unknown>,
    ) => {
      if (!threadId) return;
      setResolvingId(requestId);
      try {
        await resolveThreadPermission(threadId, requestId, decision, message, answers, annotations);
        await refreshPermissions();
      } finally {
        setResolvingId(null);
      }
    },
    [refreshPermissions, threadId],
  );

  const addSessionRule = useCallback(
    async (behavior: PermissionRuleBehavior, toolName: string) => {
      if (!threadId) return;
      await addThreadPermissionRule(threadId, behavior, toolName);
      await refreshPermissions();
    },
    [refreshPermissions, threadId],
  );

  const removeSessionRule = useCallback(
    async (behavior: PermissionRuleBehavior, toolName: string) => {
      if (!threadId) return;
      await removeThreadPermissionRule(threadId, behavior, toolName);
      await refreshPermissions();
    },
    [refreshPermissions, threadId],
  );

  useEffect(() => {
    if (!threadId) {
      refreshGenerationRef.current += 1;
      setRequests([]);
      setSessionRules({ allow: [], deny: [], ask: [] });
      setManagedOnly(false);
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
    return () => {
      refreshGenerationRef.current += 1;
      requestAbortRef.current?.abort();
      requestAbortRef.current = null;
      window.clearInterval(timer);
    };
  }, [threadId, refreshPermissions]);

  return {
    requests,
    sessionRules,
    managedOnly,
    loading,
    resolvingId,
    refreshPermissions,
    resolvePermission: resolvePermissionRequest,
    addSessionRule,
    removeSessionRule,
  };
}
