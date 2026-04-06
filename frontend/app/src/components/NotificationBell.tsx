/**
 * NotificationBell — shows pending relationship approval requests.
 * Appears in sidebar, above avatar popover.
 */

import { useCallback, useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import MemberAvatar from "@/components/MemberAvatar";
import { authFetch, useAuthStore } from "@/store/auth-store";
import { supabase } from "@/lib/supabase";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import type { Relationship } from "@/api/types";

interface PendingItem {
  relId: string;
  userId: string;
}

interface NotificationBellProps {
  showLabel?: boolean;
}

export default function NotificationBell({ showLabel }: NotificationBellProps) {
  const myUserId = useAuthStore(s => s.userId);
  const navigate = useNavigate();
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [open, setOpen] = useState(false);
  const [acting, setActing] = useState<string | null>(null);

  const fetchPending = useCallback(async () => {
    if (!myUserId) return;
    try {
      const res = await authFetch("/api/relationships");
      if (!res.ok) return;
      const rels: Relationship[] = await res.json();
      const items = rels
        .filter(r => !r.is_requester && r.state.startsWith("pending"))
        .map(r => ({ relId: r.id, userId: r.other_user_id }));
      setPending(items);
    } catch { /* silent */ }
  }, [myUserId]);

  useEffect(() => { fetchPending(); }, [fetchPending]);

  useEffect(() => {
    if (!supabase || !myUserId) return;
    const channel = supabase
      .channel(`notifications:${myUserId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "relationships", filter: `principal_a=eq.${myUserId}` }, fetchPending)
      .on("postgres_changes", { event: "*", schema: "public", table: "relationships", filter: `principal_b=eq.${myUserId}` }, fetchPending)
      .subscribe();
    return () => { supabase?.removeChannel(channel); };
  }, [myUserId, fetchPending]);

  const handleApprove = async (relId: string) => {
    setActing(relId);
    try {
      const res = await authFetch(`/api/relationships/${relId}/approve`, { method: "POST" });
      if (!res.ok) { toast.error("操作失败"); return; }
      toast.success("已批准");
      fetchPending();
    } catch { toast.error("网络错误"); }
    finally { setActing(null); }
  };

  const handleReject = async (relId: string) => {
    setActing(relId);
    try {
      const res = await authFetch(`/api/relationships/${relId}/reject`, { method: "POST" });
      if (!res.ok) { toast.error("操作失败"); return; }
      toast.success("已拒绝");
      fetchPending();
    } catch { toast.error("网络错误"); }
    finally { setActing(null); }
  };

  const count = pending.length;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button className={`relative flex items-center ${showLabel ? "px-3 gap-3 w-full" : "justify-center w-10"} h-10 rounded-xl hover:bg-muted transition-colors duration-fast`}>
          <div className="relative shrink-0">
            <Bell className="w-[18px] h-[18px]" />
            {count > 0 && (
              <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-destructive text-background text-2xs flex items-center justify-center font-bold leading-none">
                {count > 9 ? "9+" : count}
              </span>
            )}
          </div>
          {showLabel && <span className="text-sm truncate text-sidebar-foreground">通知</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="end" className="w-80 p-0">
        <div className="px-3 py-2 border-b border-border">
          <p className="text-sm font-medium">通知</p>
        </div>
        {pending.length === 0 ? (
          <div className="px-3 py-4 text-sm text-muted-foreground text-center">暂无待处理请求</div>
        ) : (
          <div className="divide-y divide-border">
            {pending.map(item => (
              <div key={item.relId} className="flex items-center gap-2 px-3 py-2.5">
                <MemberAvatar name={item.userId.slice(0, 2)} size="sm" type="agent" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-foreground truncate">{item.userId.slice(0, 12)}… 请求 Visit</p>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <button
                    onClick={() => handleApprove(item.relId)}
                    disabled={acting === item.relId}
                    className="px-2 py-1 rounded bg-success/10 text-success text-2xs font-medium hover:bg-success/20 disabled:opacity-50 transition-colors duration-fast"
                  >批准</button>
                  <button
                    onClick={() => handleReject(item.relId)}
                    disabled={acting === item.relId}
                    className="px-2 py-1 rounded bg-muted text-muted-foreground text-2xs font-medium hover:bg-muted/80 disabled:opacity-50 transition-colors duration-fast"
                  >拒绝</button>
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="px-3 py-2 border-t border-border">
          <button
            onClick={() => { setOpen(false); navigate("/contacts"); }}
            className="text-xs text-primary hover:underline"
          >查看全部 →</button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
