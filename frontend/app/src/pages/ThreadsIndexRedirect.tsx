import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getMainThread } from "../api/client";
import { useAuthStore } from "../store/auth-store";

const defaultThreadInflight = new Map<string, Promise<Awaited<ReturnType<typeof getMainThread>>>>();

function loadDefaultThread(memberId: string) {
  const existing = defaultThreadInflight.get(memberId);
  if (existing) return existing;
  const pending = getMainThread(memberId).finally(() => {
    defaultThreadInflight.delete(memberId);
  });
  defaultThreadInflight.set(memberId, pending);
  return pending;
}

export default function ThreadsIndexRedirect() {
  const agent = useAuthStore((s) => s.agent);
  const navigate = useNavigate();

  useEffect(() => {
    if (!agent?.id) return;
    const agentId = agent.id;

    let cancelled = false;

    async function redirectToThread() {
      const memberId = encodeURIComponent(agentId);
      try {
        // @@@threads-index-direct-default-route - /threads is a pure entrypoint; resolve the
        // default thread here so login/setup flows do not bounce through NewChatPage first.
        // @@@threads-index-inflight-dedup - React StrictMode remounts /threads in dev.
        // Reuse the first default-thread request and ignore stale callbacks instead of
        // aborting the first fetch and polluting network/devtools with ERR_ABORTED.
        const thread = await loadDefaultThread(agentId);
        if (cancelled) return;
        navigate(
          thread
            ? `/chat/hire/${memberId}/${encodeURIComponent(thread.thread_id)}`
            : `/chat/hire/${memberId}`,
          { replace: true },
        );
      } catch (error) {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        console.error("[ThreadsIndexRedirect] resolve default thread failed:", error);
        navigate(`/chat/hire/${memberId}`, { replace: true });
      }
    }

    void redirectToThread();
    return () => {
      cancelled = true;
    };
  }, [agent?.id, navigate]);

  return null;
}
