import { useEffect, useState, useCallback } from "react";
import { Link, Outlet, useParams, useNavigate } from "react-router-dom";
import { Plus, Search, X } from "lucide-react";
import MemberAvatar from "../components/MemberAvatar";
import { authFetch, useAuthStore } from "../store/auth-store";

interface ChatEntity {
  id: string;
  name: string;
  type: string;
  avatar?: string | null;
}

interface ChatSummary {
  id: string;
  title: string | null;
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
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function chatDisplayName(chat: ChatSummary, myEntityId: string | null): string {
  if (chat.title) return chat.title;
  const others = chat.entities.filter(e => e.id !== myEntityId);
  return others.map(e => e.name).join(", ") || "Chat";
}

// @@@new-chat-dialog — entity picker for creating 1:1 chat
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

  const handleSelect = useCallback(async (target: ChatEntity) => {
    if (!myEntityId || creating) return;
    setCreating(true);
    try {
      const res = await authFetch("/api/chats", {
        method: "POST",
        body: JSON.stringify({ entity_ids: [myEntityId, target.id] }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `${res.status}`);
      }
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
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>
        <div className="px-4 py-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input type="text" placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)}
              className="flex-1 bg-transparent text-sm outline-none" autoFocus />
          </div>
        </div>
        <div className="max-h-64 overflow-y-auto px-2 pb-2">
          {filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">
              {entities.length === 0 ? "No other users registered yet" : "No matches"}
            </p>
          ) : filtered.map(e => (
            <button key={e.id} onClick={() => void handleSelect(e)} disabled={creating}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-left disabled:opacity-50">
              <MemberAvatar name={e.name} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{e.name}</p>
                <p className="text-[10px] text-muted-foreground">{e.type}</p>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ChatsLayout() {
  const { chatId } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const myEntityId = useAuthStore(s => s.entityId);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewChat, setShowNewChat] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const refresh = useCallback(() => {
    authFetch("/api/chats")
      .then(r => r.json())
      .then(setChats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCreated = useCallback((newChatId: string) => {
    setShowNewChat(false);
    refresh();
    navigate(`/chats/${newChatId}`);
  }, [navigate, refresh]);

  // Filter by search + sort: unread first, then by time
  const filtered = searchQuery
    ? chats.filter(c => chatDisplayName(c, myEntityId).toLowerCase().includes(searchQuery.toLowerCase()))
    : chats;
  const sorted = [...filtered].sort((a, b) => {
    if (a.unread_count > 0 && b.unread_count === 0) return -1;
    if (b.unread_count > 0 && a.unread_count === 0) return 1;
    const ta = a.last_message?.created_at ?? 0;
    const tb = b.last_message?.created_at ?? 0;
    return tb - ta;
  });

  return (
    <div className="h-full w-full flex overflow-hidden">
      {/* Sidebar — chat list */}
      <div className="w-72 h-full flex flex-col border-r border-border bg-card shrink-0">
        <div className="px-4 pt-3 pb-1 flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">Chats</span>
          <button onClick={() => setShowNewChat(true)}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground">
            <Plus className="w-4 h-4" />
          </button>
        </div>

        {/* Search — matches Threads sidebar style */}
        <div className="px-3 pb-3">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground/60 bg-muted/30 border border-transparent focus-within:border-primary/40">
            <Search className="w-4 h-4 shrink-0" />
            <input
              type="text"
              placeholder="Search chats..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="flex-1 bg-transparent outline-none text-foreground placeholder:text-muted-foreground/60 text-sm"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <p className="text-xs text-muted-foreground text-center py-8">Loading...</p>
          ) : sorted.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <p className="text-xs text-muted-foreground mb-2">No chats yet</p>
              <button onClick={() => setShowNewChat(true)}
                className="text-xs text-primary hover:underline">Start a conversation</button>
            </div>
          ) : sorted.map(chat => {
            const isActive = chatId === chat.id;
            const name = chatDisplayName(chat, myEntityId);
            return (
              <Link key={chat.id} to={`/chats/${chat.id}`}
                className={`flex items-center gap-3 px-4 py-2.5 transition-colors ${isActive ? "bg-background" : "hover:bg-muted/50"}`}>
                <MemberAvatar name={name} size="sm" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className={`text-sm truncate ${chat.unread_count > 0 ? "font-semibold" : "font-medium"} text-foreground`}>
                      {name}
                    </span>
                    {chat.last_message && (
                      <span className="text-[10px] text-muted-foreground/50 shrink-0 ml-1">
                        {formatTime(chat.last_message.created_at)}
                      </span>
                    )}
                  </div>
                  {chat.last_message && (
                    <p className="text-[11px] text-muted-foreground truncate mt-0.5">
                      {chat.last_message.content}
                    </p>
                  )}
                </div>
                {chat.has_mention ? (
                  <span className="w-4 h-4 rounded-full bg-destructive text-destructive-foreground text-[9px] font-bold flex items-center justify-center shrink-0">@</span>
                ) : chat.unread_count > 0 ? (
                  <span className="min-w-4 h-4 rounded-full bg-primary text-primary-foreground text-[9px] flex items-center justify-center px-1 shrink-0">
                    {chat.unread_count > 99 ? "99+" : chat.unread_count}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </div>
      </div>

      {/* Main content — conversation or empty state */}
      <div className="flex-1 min-w-0">
        <Outlet />
      </div>

      {showNewChat && <NewChatDialog onClose={() => setShowNewChat(false)} onCreated={handleCreated} />}
    </div>
  );
}
