import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getMainThread } from "../api/client";
import { useAuthStore } from "../store/auth-store";

export default function ThreadsIndexRedirect() {
  const agent = useAuthStore((s) => s.agent);
  const navigate = useNavigate();

  useEffect(() => {
    if (!agent?.id) return;
    const agentId = agent.id;

    let cancelled = false;
    const ac = new AbortController();

    async function redirectToThread() {
      const memberId = encodeURIComponent(agentId);
      try {
        // @@@threads-index-direct-main-route - /threads is a pure entrypoint; resolve the
        // main thread here so login/setup flows do not bounce through NewChatPage first.
        const thread = await getMainThread(agentId, ac.signal);
        if (cancelled) return;
        navigate(
          thread
            ? `/threads/${memberId}/${encodeURIComponent(thread.thread_id)}`
            : `/threads/${memberId}`,
          { replace: true },
        );
      } catch (error) {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        console.error("[ThreadsIndexRedirect] resolve main thread failed:", error);
        navigate(`/threads/${memberId}`, { replace: true });
      }
    }

    void redirectToThread();
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [agent, navigate]);

  return null;
}
