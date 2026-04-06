/**
 * AgentProfileSheet — right-side sheet for agent profile + quick relationship actions.
 */

import { useEffect, useState } from "react";
import { MessageSquare, Users, ExternalLink } from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import MemberAvatar from "@/components/MemberAvatar";
import { authFetch, useAuthStore } from "@/store/auth-store";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import type { AgentProfile, Relationship } from "@/api/types";

interface AgentProfileSheetProps {
  userId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function AgentProfileSheet({ userId, open, onOpenChange }: AgentProfileSheetProps) {
  const myUserId = useAuthStore(s => s.userId);
  const navigate = useNavigate();
  const [profile, setProfile] = useState<AgentProfile | null>(null);
  const [relationship, setRelationship] = useState<Relationship | null>(null);
  const [acting, setActing] = useState(false);

  const fetchData = () => {
    if (!userId || !open) return;
    fetch(`/api/entities/${userId}/profile`)
      .then(r => r.ok ? r.json() : null)
      .then(setProfile)
      .catch(() => setProfile(null));

    if (myUserId) {
      authFetch("/api/relationships")
        .then(r => r.json())
        .then((rels: Relationship[]) => {
          setRelationship(rels.find(r => r.other_user_id === userId) ?? null);
        })
        .catch(() => {});
    }
  };

  useEffect(() => { fetchData(); }, [userId, open, myUserId]);

  const handleRequest = async () => {
    if (!userId) return;
    setActing(true);
    try {
      const res = await authFetch("/api/relationships/request", {
        method: "POST",
        body: JSON.stringify({ target_user_id: userId }),
      });
      if (!res.ok) { toast.error("申请失败"); return; }
      toast.success("已发送 Visit 申请");
      // Refresh
      const rels: Relationship[] = await authFetch("/api/relationships").then(r => r.json());
      setRelationship(rels.find(r => r.other_user_id === userId) ?? null);
    } catch { toast.error("网络错误"); }
    finally { setActing(false); }
  };

  const handleCancelRequest = async () => {
    if (!relationship) return;
    setActing(true);
    try {
      const res = await authFetch(`/api/relationships/${relationship.id}/revoke`, { method: "POST" });
      if (!res.ok) { toast.error("操作失败"); return; }
      toast.success("已取消申请");
      setRelationship(null);
    } catch { toast.error("网络错误"); }
    finally { setActing(false); }
  };

  const state = relationship?.state ?? "none";
  const isPending = state.startsWith("pending");
  const isRequester = relationship?.is_requester ?? false;
  const hasActiveRel = state === "hire" || state === "visit";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-80 p-0 flex flex-col">
        <SheetHeader className="p-4 border-b border-border">
          <SheetTitle className="text-sm font-medium">Agent 信息</SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {!profile ? (
            <p className="text-sm text-muted-foreground">加载中...</p>
          ) : (
            <>
              <div className="flex flex-col items-center gap-3 py-2">
                <MemberAvatar name={profile.name} avatarUrl={profile.avatar_url} size="lg" type="agent" />
                <div className="text-center">
                  <p className="font-medium text-foreground">{profile.name}</p>
                  <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">Agent</span>
                </div>
                {profile.description && (
                  <p className="text-xs text-muted-foreground text-center">{profile.description}</p>
                )}
              </div>

              {state !== "none" && (
                <div className="rounded-lg border border-border p-2.5 text-center">
                  {state === "hire" && <span className="text-xs text-success font-medium">Hire 关系</span>}
                  {state === "visit" && <span className="text-xs text-info font-medium">Visit 关系</span>}
                  {isPending && isRequester && <span className="text-xs text-warning font-medium">申请中</span>}
                  {isPending && !isRequester && <span className="text-xs text-info font-medium">等待你确认</span>}
                </div>
              )}

              <div className="space-y-2">
                <button
                  onClick={() => { onOpenChange(false); navigate("/chats"); }}
                  className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-foreground text-background text-sm font-medium hover:opacity-90 transition-opacity duration-fast"
                >
                  <MessageSquare className="w-4 h-4" />发消息
                </button>
                {state === "none" && (
                  <button
                    onClick={handleRequest}
                    disabled={acting}
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-muted disabled:opacity-50 transition-colors duration-fast"
                  >
                    <Users className="w-4 h-4" />申请联系
                  </button>
                )}
                {isPending && isRequester && (
                  <button
                    onClick={handleCancelRequest}
                    disabled={acting}
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:bg-muted disabled:opacity-50 transition-colors duration-fast"
                  >
                    取消申请
                  </button>
                )}
                {hasActiveRel && (
                  <button
                    onClick={() => { onOpenChange(false); navigate("/contacts"); }}
                    className="w-full flex items-center justify-center gap-2 py-2 rounded-lg border border-border text-sm text-foreground hover:bg-muted transition-colors duration-fast"
                  >
                    <ExternalLink className="w-4 h-4" />管理关系
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
