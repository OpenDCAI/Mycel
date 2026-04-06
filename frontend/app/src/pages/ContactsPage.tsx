/**
 * ContactsPage — 通讻录
 * Three tabs: 待确认 | 联系人 | 已屏蔽
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, X, MessageSquare, ShieldOff } from "lucide-react";
import MemberAvatar from "@/components/MemberAvatar";
import { authFetch } from "@/store/auth-store";
import { toast } from "sonner";
import type { Relationship, Contact } from "@/api/types";

type Tab = "pending" | "contacts" | "blocked";

export default function ContactsPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("pending");
  const [relationships, setRelationships] = useState<Relationship[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [acting, setActing] = useState<string | null>(null);

  const fetchRelationships = useCallback(async () => {
    try {
      const res = await authFetch("/api/relationships");
      if (res.ok) setRelationships(await res.json());
    } catch { /* silent */ }
  }, []);

  const fetchContacts = useCallback(async () => {
    try {
      const res = await authFetch("/api/contacts");
      if (res.ok) setContacts(await res.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchRelationships();
    fetchContacts();
  }, [fetchRelationships, fetchContacts]);

  const pendingForMe = relationships.filter(r => !r.is_requester && r.state.startsWith("pending"));
  const activeContacts = relationships
    .filter(r => r.state === "hire" || r.state === "visit")
    .sort((a, b) => (a.state === "hire" ? -1 : b.state === "hire" ? 1 : 0));
  const blockedContacts = contacts.filter(c => c.relation === "blocked");

  const act = async (fn: () => Promise<Response>, successMsg: string, onDone: () => void) => {
    try {
      const res = await fn();
      if (!res.ok) { toast.error("操作失败"); return; }
      toast.success(successMsg);
      onDone();
    } catch { toast.error("网络错误"); }
  };

  const handleApprove = (relId: string) => {
    setActing(relId);
    act(
      () => authFetch(`/api/relationships/${relId}/approve`, { method: "POST" }),
      "已批准",
      fetchRelationships,
    ).finally(() => setActing(null));
  };

  const handleReject = (relId: string) => {
    setActing(relId);
    act(
      () => authFetch(`/api/relationships/${relId}/reject`, { method: "POST" }),
      "已拒绝",
      fetchRelationships,
    ).finally(() => setActing(null));
  };

  const handleRevoke = (relId: string) => {
    setActing(relId);
    act(
      () => authFetch(`/api/relationships/${relId}/revoke`, { method: "POST" }),
      "已撤回",
      fetchRelationships,
    ).finally(() => setActing(null));
  };

  const handleUnblock = (targetId: string) => {
    setActing(targetId);
    act(
      () => authFetch(`/api/contacts/${targetId}`, { method: "DELETE" }),
      "已解除屏蔽",
      fetchContacts,
    ).finally(() => setActing(null));
  };

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: "pending", label: "待确认", count: pendingForMe.length },
    { id: "contacts", label: "联系人" },
    { id: "blocked", label: "已屏蔽" },
  ];

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Header */}
      <div className="px-4 pt-4 pb-0 border-b border-border">
        <h1 className="text-lg font-semibold text-foreground mb-3">通讻录</h1>
        <div className="flex gap-1">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm border-b-2 transition-colors duration-fast ${
                tab === t.id
                  ? "border-primary text-primary font-medium"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.label}
              {t.count !== undefined && t.count > 0 && (
                <span className="px-1.5 py-0.5 rounded-full bg-destructive text-background text-2xs font-bold">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "pending" && (
          <div className="divide-y divide-border">
            {pendingForMe.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">暂无待确认请求</div>
            )}
            {pendingForMe.map(rel => (
              <div key={rel.id} className="flex items-center gap-3 px-4 py-3">
                <MemberAvatar name={rel.other_user_id.slice(0, 2)} size="md" type="agent" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{rel.other_user_id}</p>
                  <p className="text-xs text-muted-foreground">申请 Visit 权限</p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => handleApprove(rel.id)}
                    disabled={acting === rel.id}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-success/10 text-success text-xs font-medium hover:bg-success/20 disabled:opacity-50 transition-colors duration-fast"
                  >
                    <Check className="w-3.5 h-3.5" />批准
                  </button>
                  <button
                    onClick={() => handleReject(rel.id)}
                    disabled={acting === rel.id}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs font-medium hover:bg-muted/80 disabled:opacity-50 transition-colors duration-fast"
                  >
                    <X className="w-3.5 h-3.5" />拒绝
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "contacts" && (
          <div className="divide-y divide-border">
            {activeContacts.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">暂无联系人</div>
            )}
            {activeContacts.map(rel => (
              <div key={rel.id} className="flex items-center gap-3 px-4 py-3">
                <MemberAvatar name={rel.other_user_id.slice(0, 2)} size="md" type="agent" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-foreground truncate">{rel.other_user_id}</p>
                    {rel.state === "hire" && (
                      <span className="text-2xs px-1.5 py-0.5 rounded bg-success/10 text-success font-medium shrink-0">Hire</span>
                    )}
                    {rel.state === "visit" && (
                      <span className="text-2xs px-1.5 py-0.5 rounded bg-info/10 text-info font-medium shrink-0">Visit</span>
                    )}
                  </div>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <button
                    onClick={() => navigate("/chats")}
                    className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors duration-fast"
                    title="发消息"
                  >
                    <MessageSquare className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleRevoke(rel.id)}
                    disabled={acting === rel.id}
                    className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors duration-fast disabled:opacity-50"
                    title="撤回关系"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "blocked" && (
          <div className="divide-y divide-border">
            {blockedContacts.length === 0 && (
              <div className="p-8 text-center text-sm text-muted-foreground">暂无屏蔽记录</div>
            )}
            {blockedContacts.map(c => (
              <div key={c.target_user_id} className="flex items-center gap-3 px-4 py-3 opacity-70">
                <MemberAvatar name={c.target_user_id.slice(0, 2)} size="md" type="agent" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{c.target_user_id}</p>
                  <p className="text-xs text-muted-foreground">已屏蔽</p>
                </div>
                <button
                  onClick={() => handleUnblock(c.target_user_id)}
                  disabled={acting === c.target_user_id}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs font-medium hover:bg-muted/80 disabled:opacity-50 transition-colors duration-fast"
                >
                  <ShieldOff className="w-3.5 h-3.5" />解除屏蔽
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
