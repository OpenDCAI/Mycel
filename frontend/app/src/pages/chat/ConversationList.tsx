import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import MemberAvatar from "@/components/MemberAvatar";
import { useConversationStore } from "@/store/conversation-store";
import type { ConversationItem } from "@/types/conversation";
import NewChatDialog from "@/components/NewChatDialog";

function formatTime(dateStr: string | null): string {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  if (diffMs < 60_000) return "刚刚";
  if (diffMs < 3600_000) return `${Math.floor(diffMs / 60_000)}m`;
  if (diffMs < 86400_000) return `${Math.floor(diffMs / 3600_000)}h`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function conversationHref(item: ConversationItem): string {
  if (item.type === "hire" && item.member_id) {
    return `/chat/hire/${encodeURIComponent(item.member_id)}/${encodeURIComponent(item.id)}`;
  }
  return `/chat/visit/${encodeURIComponent(item.id)}`;
}

export default function ConversationList() {
  const { conversations, loading, fetchConversations } = useConversationStore();
  const [search, setSearch] = useState("");
  const [newChatOpen, setNewChatOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    void fetchConversations();
    const timer = setInterval(() => void fetchConversations(), 5000);
    return () => clearInterval(timer);
  }, [fetchConversations]);

  const filtered = search
    ? conversations.filter((c) => c.title.toLowerCase().includes(search.toLowerCase()))
    : conversations;

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      <div className="px-4 pt-3 pb-1 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">对话</span>
        <button
          onClick={() => setNewChatOpen(true)}
          className="text-xs text-muted-foreground/50 hover:text-foreground transition-colors duration-fast"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      <div className="px-3 pb-3">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border">
          <Search className="w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索对话..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none text-foreground placeholder:text-muted-foreground/50"
          />
        </div>
      </div>

      <div className="h-px mx-3 bg-border" />

      <div className="flex-1 min-h-0 overflow-y-auto px-2 pt-2 space-y-0.5 custom-scrollbar">
        {loading && conversations.length === 0 ? (
          <div className="space-y-0.5">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="px-3 py-2.5 rounded-lg animate-pulse">
                <div className="h-4 w-[60%] bg-muted rounded mb-1.5" />
                <div className="h-3 w-[40%] bg-muted rounded" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <p className="text-xs text-muted-foreground mb-2">
              {search ? "无匹配结果" : "暂无对话"}
            </p>
          </div>
        ) : (
          filtered.map((item) => {
            const href = conversationHref(item);
            const isActive =
              location.pathname === href ||
              location.pathname.startsWith(href + "/");
            return (
              <Link
                key={`${item.type}-${item.id}`}
                to={href}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg transition-colors duration-fast ${
                  isActive ? "bg-background shadow-sm" : "hover:bg-muted"
                }`}
              >
                <div className="relative">
                  <MemberAvatar
                    name={item.title}
                    avatarUrl={item.avatar_url ?? undefined}
                    type={item.type === "hire" ? "mycel_agent" : "human"}
                    size="sm"
                  />
                  {item.running && (
                    <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-success border-2 border-card" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`text-sm font-medium truncate ${
                        isActive ? "text-foreground" : "text-foreground"
                      }`}
                    >
                      {item.title}
                    </span>
                  </div>
                  {item.updated_at && (
                    <span className="text-2xs text-muted-foreground/40">
                      {formatTime(item.updated_at)}
                    </span>
                  )}
                </div>
                {item.unread_count > 0 && (
                  <span className="min-w-4 h-4 rounded-full bg-primary text-primary-foreground text-2xs flex items-center justify-center px-1 shrink-0">
                    {item.unread_count > 99 ? "99+" : item.unread_count}
                  </span>
                )}
              </Link>
            );
          })
        )}
      </div>

      {newChatOpen && (
        <NewChatDialog
          open={newChatOpen}
          onOpenChange={setNewChatOpen}
        />
      )}
    </div>
  );
}
