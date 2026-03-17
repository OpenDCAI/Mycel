import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore, authFetch } from "../store/auth-store";

export default function WorkspaceLanding() {
  const navigate = useNavigate();
  const agent = useAuthStore(s => s.agent);
  const entityId = useAuthStore(s => s.entityId);

  useEffect(() => {
    if (!entityId) return;
    authFetch(`/api/entities/${entityId}/agent-thread`)
      .then(r => {
        if (r.status === 404) {
          // @@@stale-token — entity doesn't exist in DB, force re-login
          useAuthStore.getState().logout();
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(data => {
        if (data?.thread_id) {
          navigate(`/threads/${data.thread_id}`, { replace: true });
        }
      })
      .catch(() => {});
  }, [entityId, navigate]);

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <h2 className="text-lg font-semibold mb-2">Welcome</h2>
        <p className="text-sm text-muted-foreground">
          {agent ? `${agent.name} is ready.` : "Setting up workspace..."}
        </p>
      </div>
    </div>
  );
}
