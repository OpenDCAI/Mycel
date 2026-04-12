import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Bot, MessageSquare, User } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchUserChatCandidates, type UserChatCandidate } from "@/api/users";
import ActorAvatar from "@/components/ActorAvatar";
import { Button } from "@/components/ui/button";
import { authFetch, useAuthStore } from "@/store/auth-store";

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

async function createDirectChat(currentUserId: string, targetUserId: string): Promise<string> {
  const response = await authFetch("/api/chats", {
    method: "POST",
    body: JSON.stringify({ user_ids: [currentUserId, targetUserId] }),
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  const payload = await response.json();
  if (!payload || typeof payload !== "object" || typeof (payload as Record<string, unknown>).id !== "string") {
    throw new Error("Malformed chat create response");
  }
  return (payload as { id: string }).id;
}

function relationshipLabel(contact: UserChatCandidate): string {
  if (contact.relationship_state === "visit" || contact.relationship_state === "hire") return contact.relationship_state;
  if (contact.can_chat) return "联系人";
  return contact.relationship_state;
}

export default function ContactDetailPage() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const myUserId = useAuthStore((s) => s.userId);
  const [chatCandidates, setChatCandidates] = useState<UserChatCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    fetchUserChatCandidates()
      .then((items) => {
        if (!cancelled) setChatCandidates(items);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorText(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const contact = useMemo(() => chatCandidates.find((item) => item.user_id === userId), [chatCandidates, userId]);

  const openConversation = async () => {
    if (!contact || opening) return;
    setOpening(true);
    setOpenError(null);
    try {
      if (!myUserId) throw new Error("当前用户未登录");
      const chatId = await createDirectChat(myUserId, contact.user_id);
      navigate(`/chat/visit/${chatId}`);
    } catch (err) {
      setOpenError(errorText(err));
    } finally {
      setOpening(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载联系人...</p>
      </div>
    );
  }

  if (loadError || !contact) {
    return (
      <div className="h-full flex items-center justify-center px-6 text-center">
        <p className="text-sm text-destructive">
          {loadError ? `联系人加载失败：${loadError}` : "联系人不存在或不可访问"}
        </p>
      </div>
    );
  }

  const isAgent = contact.type === "agent";
  const relationshipStatus = relationshipLabel(contact);

  return (
    <div className="h-full flex flex-col bg-background">
      <div className="flex items-center gap-3 px-4 py-3 border-b shrink-0">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        {isAgent ? <Bot className="h-5 w-5 text-primary" /> : <User className="h-5 w-5 text-primary" />}
        <h1 className="text-sm font-semibold text-foreground">{contact.name}</h1>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{contact.type}</span>
        <div className="flex-1" />
        {contact.can_chat && (
          <Button size="sm" onClick={() => void openConversation()} disabled={opening}>
            <MessageSquare className="h-3.5 w-3.5 mr-1" />
            {opening ? "打开中..." : "发起对话"}
          </Button>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-6">
        <div className="max-w-2xl space-y-4">
          <section className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-start gap-4">
              <ActorAvatar
                name={contact.name}
                avatarUrl={contact.avatar_url ?? undefined}
                type={isAgent ? "mycel_agent" : "human"}
                size="lg"
              />
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold text-foreground">{contact.name}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {contact.owner_name ? `由 ${contact.owner_name} 拥有` : isAgent ? "Agent 用户" : "Human 用户"}
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-border bg-card p-5">
            <h2 className="text-sm font-semibold text-foreground mb-4">关系</h2>
            <dl className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <dt className="text-xs text-muted-foreground">关系状态</dt>
                <dd className="mt-1 text-foreground">{relationshipStatus}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">可对话</dt>
                <dd className="mt-1 text-foreground">{contact.can_chat ? "是" : "否"}</dd>
              </div>
              {isAgent && (
                <>
                  <div>
                    <dt className="text-xs text-muted-foreground">默认线程</dt>
                    <dd className="mt-1 break-all text-foreground">{contact.default_thread_id ?? "未配置"}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">分支</dt>
                    <dd className="mt-1 text-foreground">
                      {contact.branch_index == null ? "未配置" : contact.is_default_thread ? "默认" : `#${contact.branch_index}`}
                    </dd>
                  </div>
                </>
              )}
            </dl>
          </section>

          {openError && (
            <p className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {openError}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
