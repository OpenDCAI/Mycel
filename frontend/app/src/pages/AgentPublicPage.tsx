/**
 * AgentPublicPage — public agent profile page, no auth required.
 * Route: /a/:entityId
 */

import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import MemberAvatar from "@/components/MemberAvatar";
import { authFetch, useAuthStore } from "@/store/auth-store";
import { toast } from "sonner";
import type { AgentProfile } from "@/api/types";

export default function AgentPublicPage() {
  const { entityId } = useParams<{ entityId: string }>();
  const navigate = useNavigate();
  const token = useAuthStore(s => s.token);
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!entityId) return;
    fetch(`/api/entities/${entityId}/profile`)
      .then(r => {
        if (!r.ok) throw new Error("Agent not found");
        return r.json();
      })
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setLoading(false));
  }, [entityId]);

  const handleApply = async () => {
    if (!token) {
      navigate(`/?redirect=/a/${entityId}`);
      return;
    }
    if (!entityId) return;
    setApplying(true);
    try {
      const res = await authFetch("/api/relationships/request", {
        method: "POST",
        body: JSON.stringify({ target_user_id: entityId }),
      });
      if (res.status === 401) {
        navigate(`/?redirect=/a/${entityId}`);
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "申请失败");
        return;
      }
      toast.success("已发送 Visit 申请");
    } catch {
      toast.error("网络错误");
    } finally {
      setApplying(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Agent 不存在</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-4">
          <MemberAvatar
            name={profile.name}
            avatarUrl={profile.avatar_url}
            size="lg"
            type="agent"
          />
          <div className="text-center space-y-1">
            <h1 className="text-xl font-semibold text-foreground">{profile.name}</h1>
            <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">Agent</span>
          </div>
          {profile.description && (
            <p className="text-sm text-muted-foreground text-center">{profile.description}</p>
          )}
        </div>

        <div className="border-t border-border pt-6 space-y-3">
          <p className="text-xs text-muted-foreground text-center">联系</p>
          <button
            onClick={handleApply}
            disabled={applying}
            className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity duration-fast"
          >
            {applying ? "发送中..." : "发起 Visit 申请"}
          </button>
        </div>

        <p className="text-center text-xs text-muted-foreground">由 Mycel 提供技术支持</p>
      </div>
    </div>
  );
}
