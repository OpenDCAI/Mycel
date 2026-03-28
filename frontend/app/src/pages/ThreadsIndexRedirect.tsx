import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth-store";

export default function ThreadsIndexRedirect() {
  const agent = useAuthStore((s) => s.agent);
  const navigate = useNavigate();

  useEffect(() => {
    if (!agent?.id) return;
    navigate(`/threads/${encodeURIComponent(agent.id)}`, { replace: true });
  }, [agent?.id, navigate]);

  return null;
}
