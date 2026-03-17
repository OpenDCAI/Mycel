import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { authFetch } from "../store/auth-store";
import { useAuthStore } from "../store/auth-store";

interface ChatEntity {
  id: string;
  name: string;
  type: string;
  avatar?: string | null;
}

interface ChatSummary {
  id: string;
  title: string | null;
  status: string;
  created_at: number;
  entities: ChatEntity[];
  last_message?: { content: string; sender_name: string; created_at: number };
  unread_count: number;
  has_mention: boolean;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  if (diffMs < 60_000) return "just now";
  if (diffMs < 3600_000) return `${Math.floor(diffMs / 60_000)}m`;
  if (diffMs < 86400_000) return `${Math.floor(diffMs / 3600_000)}h`;
  if (diffMs < 604800_000) return `${Math.floor(diffMs / 86400_000)}d`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function ChatAvatar({ entities, myEntityId }: { entities: ChatEntity[]; myEntityId: string | null }) {
  const others = entities.filter(e => e.id !== myEntityId);
  const isGroup = entities.length >= 3;

  if (isGroup) {
    // Stacked avatars for group
    const show = others.slice(0, 2);
    return (
      <div className="relative w-10 h-10 shrink-0">
        {show.map((e, i) => (
          <div
            key={e.id}
            className="absolute w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-[10px] font-semibold text-primary border-2 border-card"
            style={{ top: i * 6, left: i * 6, zIndex: show.length - i }}
          >
            {e.name.charAt(0).toUpperCase()}
          </div>
        ))}
      </div>
    );
  }

  // 1:1 — show the other person
  const other = others[0];
  if (!other) return <div className="w-10 h-10 rounded-full bg-muted shrink-0" />;
  return (
    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-sm font-semibold text-primary shrink-0">
      {other.name.charAt(0).toUpperCase()}
    </div>
  );
}

function chatDisplayName(chat: ChatSummary, myEntityId: string | null): string {
  if (chat.title) return chat.title;
  const others = chat.entities.filter(e => e.id !== myEntityId);
  return others.map(e => e.name).join(", ") || "Chat";
}

export default function ChatsListPage() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const myEntityId = useAuthStore(s => s.entityId);

  useEffect(() => {
    authFetch("/api/chats")
      .then(r => r.json())
      .then((data) => { setChats(data); setLoading(false); })
      .catch((err) => { console.error("[ChatsListPage] fetch error:", err); setLoading(false); });
  }, []);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (chats.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-4">
        <p className="text-sm text-muted-foreground">No chats yet</p>
        <p className="text-xs text-muted-foreground/60 mt-1">Start a conversation to see it here</p>
      </div>
    );
  }

  // Sort: unread first, then by last_message time
  const sorted = [...chats].sort((a, b) => {
    if (a.unread_count > 0 && b.unread_count === 0) return -1;
    if (b.unread_count > 0 && a.unread_count === 0) return 1;
    const ta = a.last_message?.created_at ?? a.created_at;
    const tb = b.last_message?.created_at ?? b.created_at;
    return tb - ta;
  });

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-6 py-4 border-b border-border shrink-0">
        <h2 className="text-lg font-semibold text-foreground">Chats</h2>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sorted.map(chat => (
          <Link
            key={chat.id}
            to={`/chats/${chat.id}`}
            className="flex items-center gap-3 px-6 py-3 hover:bg-muted/50 transition-colors border-b border-border/50"
          >
            <ChatAvatar entities={chat.entities} myEntityId={myEntityId} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className={`text-sm truncate ${chat.unread_count > 0 ? "font-semibold text-foreground" : "font-medium text-foreground"}`}>
                  {chatDisplayName(chat, myEntityId)}
                </span>
                {chat.last_message && (
                  <span className="text-[10px] text-muted-foreground/60 shrink-0 ml-2">
                    {formatTime(chat.last_message.created_at)}
                  </span>
                )}
              </div>
              {chat.last_message && (
                <p className={`text-xs mt-0.5 truncate ${chat.unread_count > 0 ? "text-foreground/70" : "text-muted-foreground"}`}>
                  {chat.entities.length >= 3 && `${chat.last_message.sender_name}: `}
                  {chat.last_message.content}
                </p>
              )}
            </div>
            {/* Unread badge / @mention indicator */}
            {chat.has_mention ? (
              <span className="w-5 h-5 rounded-full bg-destructive text-destructive-foreground text-[10px] font-bold flex items-center justify-center shrink-0">
                @
              </span>
            ) : chat.unread_count > 0 ? (
              <span className="min-w-5 h-5 rounded-full bg-primary text-primary-foreground text-[10px] font-medium flex items-center justify-center px-1.5 shrink-0">
                {chat.unread_count > 99 ? "99+" : chat.unread_count}
              </span>
            ) : null}
          </Link>
        ))}
      </div>
    </div>
  );
}
