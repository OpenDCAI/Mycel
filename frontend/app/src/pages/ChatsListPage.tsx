import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus, X, Search } from "lucide-react";
import MemberAvatar from "../components/MemberAvatar";
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

function chatDisplayName(chat: ChatSummary, myEntityId: string | null): string {
  if (chat.title) return chat.title;
  const others = chat.entities.filter(e => e.id !== myEntityId);
  return others.map(e => e.name).join(", ") || "Chat";
}

// @@@new-chat-dialog — inline dialog to pick an entity and create a 1:1 chat
function NewChatDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (chatId: string) => void }) {
  const [entities, setEntities] = useState<ChatEntity[]>([]);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const myEntityId = useAuthStore(s => s.entityId);

  useEffect(() => {
    authFetch("/api/entities")
      .then(r => r.json())
      .then((data: ChatEntity[]) => setEntities(data))
      .catch(console.error);
  }, []);

  const filtered = search
    ? entities.filter(e => e.name.toLowerCase().includes(search.toLowerCase()))
    : entities;

  const handleSelect = useCallback(async (targetEntity: ChatEntity) => {
    if (!myEntityId || creating) return;
    setCreating(true);
    try {
      const res = await authFetch("/api/chats", {
        method: "POST",
        body: JSON.stringify({ entity_ids: [myEntityId, targetEntity.id] }),
      });
      if (!res.ok) throw new Error(`Create chat failed: ${res.status}`);
      const data = await res.json();
      onCreated(data.id);
    } catch (err) {
      console.error("[NewChat] error:", err);
      setCreating(false);
    }
  }, [myEntityId, creating, onCreated]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-sm bg-card rounded-xl shadow-xl border border-border" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold">New Chat</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-4 py-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search entities..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="flex-1 bg-transparent text-sm outline-none"
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-64 overflow-y-auto px-2 pb-2">
          {filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">No entities found</p>
          ) : (
            filtered.map(e => (
              <button
                key={e.id}
                onClick={() => void handleSelect(e)}
                disabled={creating}
                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-left disabled:opacity-50"
              >
                <MemberAvatar name={e.name} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{e.name}</p>
                  <p className="text-[10px] text-muted-foreground">{e.type}</p>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function ChatsListPage() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewChat, setShowNewChat] = useState(false);
  const myEntityId = useAuthStore(s => s.entityId);
  const navigate = useNavigate();

  useEffect(() => {
    authFetch("/api/chats")
      .then(r => r.json())
      .then((data) => { setChats(data); setLoading(false); })
      .catch((err) => { console.error("[ChatsListPage] fetch error:", err); setLoading(false); });
  }, []);

  const handleChatCreated = useCallback((chatId: string) => {
    navigate(`/chats/${chatId}`);
  }, [navigate]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (chats.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-4">
        <p className="text-sm text-muted-foreground">No chats yet</p>
        <button
          onClick={() => setShowNewChat(true)}
          className="mt-3 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90"
        >
          Start a conversation
        </button>
        {showNewChat && <NewChatDialog onClose={() => setShowNewChat(false)} onCreated={handleChatCreated} />}
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
    <div className="h-full flex flex-col min-h-0">
      <div className="px-6 py-4 border-b border-border shrink-0 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-foreground">Chats</h2>
        <button
          onClick={() => setShowNewChat(true)}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sorted.map(chat => (
          <Link
            key={chat.id}
            to={`/chats/${chat.id}`}
            className="flex items-center gap-3 px-6 py-3 hover:bg-muted/50 transition-colors border-b border-border/50"
          >
            <MemberAvatar name={chatDisplayName(chat, myEntityId)} size="md" />
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
      {showNewChat && <NewChatDialog onClose={() => setShowNewChat(false)} onCreated={handleChatCreated} />}
    </div>
  );
}
