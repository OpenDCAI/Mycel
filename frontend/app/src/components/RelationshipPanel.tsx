/**
 * RelationshipPanel — Hire/Visit relationship management for an agent.
 *
 * Shows on AgentDetailPage. Uses entity_id (not member_id) for relationships.
 * Supports: request Visit, approve/reject pending, upgrade to Hire, revoke.
 */

import { useCallback, useEffect, useState } from "react";
import { Users, ArrowUpCircle, ArrowDownCircle, XCircle, CheckCircle, Clock } from "lucide-react";
import { authFetch, useAuthStore } from "@/store/auth-store";
import { supabase } from "@/lib/supabase";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

type RelationshipState = "none" | "pending_a_to_b" | "pending_b_to_a" | "visit" | "hire";

interface Relationship {
  id: string;
  other_user_id: string;
  state: RelationshipState;
  direction: string | null;
  hire_granted_at: string | null;
  updated_at: string;
}

interface Props {
  agentMemberId: string;
}

const STATE_LABEL: Record<RelationshipState, string> = {
  none: "无关系",
  pending_a_to_b: "申请中",
  pending_b_to_a: "待审批",
  visit: "Visit",
  hire: "Hire",
};

const STATE_COLOR: Record<RelationshipState, string> = {
  none: "text-muted-foreground",
  pending_a_to_b: "text-warning",
  pending_b_to_a: "text-info",
  visit: "text-success",
  hire: "text-success",
};

export default function RelationshipPanel({ agentMemberId }: Props) {
  const myEntityId = useAuthStore(s => s.entityId);
  const [agentEntityId, setAgentEntityId] = useState<string | null>(null);
  const [relationship, setRelationship] = useState<Relationship | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    label: string;
    desc: string;
    fn: () => void;
  } | null>(null);

  // Resolve agent entity_id from member_id
  useEffect(() => {
    authFetch("/api/entities")
      .then(r => r.json())
      .then((entities: { id: string; member_id: string; type: string }[]) => {
        const match = entities.find(e => e.member_id === agentMemberId && e.type === "agent");
        setAgentEntityId(match?.id ?? null);
      })
      .catch(() => setAgentEntityId(null));
  }, [agentMemberId]);

  const fetchRelationship = useCallback(() => {
    if (!agentEntityId || !myEntityId) { setLoading(false); return; }
    authFetch("/api/relationships")
      .then(r => r.json())
      .then((rows: Relationship[]) => {
        const rel = rows.find(r => r.other_user_id === agentEntityId) ?? null;
        setRelationship(rel);
      })
      .catch(() => setRelationship(null))
      .finally(() => setLoading(false));
  }, [agentEntityId, myEntityId]);

  useEffect(() => { fetchRelationship(); }, [fetchRelationship]);

  // Realtime: subscribe to relationship changes for instant approval notifications
  useEffect(() => {
    if (!supabase || !myEntityId) return;
    // Filter by principal_a to avoid reacting to unrelated relationship changes
    const channel = supabase
      .channel(`relationships_watch:${myEntityId}`)
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "relationships", filter: `principal_a=eq.${myEntityId}` },
        () => { fetchRelationship(); },
      )
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "relationships", filter: `principal_b=eq.${myEntityId}` },
        () => { fetchRelationship(); },
      )
      .subscribe();
    return () => { supabase?.removeChannel(channel); };
  }, [myEntityId, fetchRelationship]);

  const act = useCallback(async (action: () => Promise<Response>, successMsg: string) => {
    setActing(true);
    try {
      const res = await action();
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || `操作失败 (${res.status})`);
        return;
      }
      toast.success(successMsg);
      fetchRelationship();
    } catch {
      toast.error("网络错误");
    } finally {
      setActing(false);
    }
  }, [fetchRelationship]);

  const handleRequest = () =>
    act(
      () => authFetch("/api/relationships/request", { method: "POST", body: JSON.stringify({ target_user_id: agentEntityId }) }),
      "已发送 Visit 申请",
    );

  const handleApprove = () =>
    act(
      () => authFetch(`/api/relationships/${relationship!.id}/approve`, { method: "POST" }),
      "已批准",
    );

  const handleReject = () =>
    act(
      () => authFetch(`/api/relationships/${relationship!.id}/reject`, { method: "POST" }),
      "已拒绝",
    );

  const handleUpgrade = () =>
    act(
      () => authFetch(`/api/relationships/${relationship!.id}/upgrade`, { method: "POST", body: JSON.stringify({}) }),
      "已升级为 Hire",
    );

  const handleRevoke = () =>
    act(
      () => authFetch(`/api/relationships/${relationship!.id}/revoke`, { method: "POST" }),
      "已收回授权",
    );

  const handleDowngrade = () =>
    act(
      () => authFetch(`/api/relationships/${relationship!.id}/downgrade`, { method: "POST" }),
      "已降级为 Visit",
    );

  if (!myEntityId || !agentEntityId) return null;
  if (loading) {
    return (
      <div className="p-4 text-xs text-muted-foreground">加载关系状态...</div>
    );
  }

  const state: RelationshipState = relationship?.state ?? "none";
  // Determine if current user is the "approver" (other side of a pending request)
  const isPendingIncoming = (
    (state === "pending_a_to_b" && relationship?.direction === "a_to_b" && agentEntityId < myEntityId) ||
    (state === "pending_b_to_a" && relationship?.direction === "b_to_a" && agentEntityId > myEntityId)
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 px-1">
        <Users className="w-4 h-4 text-muted-foreground" />
        <span className="text-sm font-medium">关系状态</span>
        <span className={`text-xs font-medium ml-auto ${STATE_COLOR[state]}`}>
          {STATE_LABEL[state]}
        </span>
      </div>

      {/* Relationship description */}
      <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-muted-foreground space-y-1">
        {state === "none" && (
          <p>申请 Visit 后，此 Agent 的消息将进入通知队列（不直接唤醒）。</p>
        )}
        {(state === "pending_a_to_b" || state === "pending_b_to_a") && !isPendingIncoming && (
          <p className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-warning" /> 申请已发出，等待对方确认。</p>
        )}
        {isPendingIncoming && (
          <p className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-info" /> 对方申请了 Visit，请审批。</p>
        )}
        {state === "visit" && (
          <p>Visit 已授予：此 Agent 的消息进入通知队列。升级为 Hire 可直接唤醒。</p>
        )}
        {state === "hire" && (
          <p>Hire 已授予：此 Agent 消息直达主线程，立即唤醒响应。</p>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-2">
        {state === "none" && (
          <button
            onClick={handleRequest}
            disabled={acting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-foreground text-background text-xs font-medium hover:bg-foreground/90 disabled:opacity-50 transition-colors duration-fast"
          >
            <Users className="w-3.5 h-3.5" />
            申请 Visit
          </button>
        )}

        {isPendingIncoming && (
          <>
            <button
              onClick={handleApprove}
              disabled={acting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success/10 text-success text-xs font-medium hover:bg-success/20 disabled:opacity-50 transition-colors duration-fast"
            >
              <CheckCircle className="w-3.5 h-3.5" />
              批准
            </button>
            <button
              onClick={handleReject}
              disabled={acting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-destructive/10 text-destructive text-xs font-medium hover:bg-destructive/20 disabled:opacity-50 transition-colors duration-fast"
            >
              <XCircle className="w-3.5 h-3.5" />
              拒绝
            </button>
          </>
        )}

        {state === "visit" && (
          <>
            <button
              onClick={handleUpgrade}
              disabled={acting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-success/10 text-success text-xs font-medium hover:bg-success/20 disabled:opacity-50 transition-colors duration-fast"
            >
              <ArrowUpCircle className="w-3.5 h-3.5" />
              升级为 Hire
            </button>
            <button
              onClick={() => setConfirmAction({
                label: "收回关系",
                desc: "确定撤回 Visit 关系吗？",
                fn: handleRevoke,
              })}
              disabled={acting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs font-medium hover:bg-muted/80 disabled:opacity-50 transition-colors duration-fast"
            >
              <XCircle className="w-3.5 h-3.5" />
              收回
            </button>
          </>
        )}

        {state === "hire" && (
          <>
            <button
              onClick={() => setConfirmAction({
                label: "降级为 Visit",
                desc: "确定将关系降级为 Visit 吗？Agent 消息将不再直接唤醒。",
                fn: handleDowngrade,
              })}
              disabled={acting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs font-medium hover:bg-muted/80 disabled:opacity-50 transition-colors duration-fast"
            >
              <ArrowDownCircle className="w-3.5 h-3.5" />
              降级为 Visit
            </button>
            <button
              onClick={() => setConfirmAction({
                label: "收回授权",
                desc: "确定收回对此 Agent 的 Hire 授权吗？收回后消息将回到通知队列。",
                fn: handleRevoke,
              })}
              disabled={acting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-destructive/10 text-destructive text-xs font-medium hover:bg-destructive/20 disabled:opacity-50 transition-colors duration-fast"
            >
              <XCircle className="w-3.5 h-3.5" />
              收回全部授权
            </button>
          </>
        )}
      </div>

      <AlertDialog open={!!confirmAction} onOpenChange={() => setConfirmAction(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmAction?.label}</AlertDialogTitle>
            <AlertDialogDescription>{confirmAction?.desc}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { confirmAction?.fn(); setConfirmAction(null); }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              确认
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
