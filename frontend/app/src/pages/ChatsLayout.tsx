import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Outlet, useParams, useNavigate } from "react-router-dom";
import { Plus, Search, X } from "lucide-react";
import MemberAvatar from "../components/MemberAvatar";
import { authFetch, useAuthStore } from "../store/auth-store";
import type { ChatEntity, ChatSummary } from "../api/types";

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
              <MemberAvatar name={e.name} avatarUrl={e.avatar_url} type={e.type} size="sm" />
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

// @@@chat-search-modal — same pattern as Threads SearchModal
function ChatSearchModal({ chats, myEntityId, onSelect, onClose }: {
  chats: ChatSummary[];
  myEntityId: string | null;
  onSelect: (chatId: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = query
    ? chats.filter(c => chatDisplayName(c, myEntityId).toLowerCase().includes(query.toLowerCase()))
    : chats;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <div className="fixed inset-x-0 top-20 z-50 mx-auto w-full max-w-md bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input
            type="text"
            placeholder="Search chats..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none text-foreground"
            autoFocus
          />
        </div>
        <div className="max-h-64 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">No results</p>
          ) : filtered.map(chat => {
            const name = chatDisplayName(chat, myEntityId);
            const otherEntity = chat.entities.find(e => e.id !== myEntityId);
            return (
              <button
                key={chat.id}
                onClick={() => { onSelect(chat.id); onClose(); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted transition-colors text-left"
              >
                <MemberAvatar name={name} avatarUrl={otherEntity?.avatar_url} type={otherEntity?.type} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{name}</p>
                  {chat.last_message && (
                    <p className="text-[11px] text-muted-foreground truncate">{chat.last_message.content}</p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

export default function ChatsLayout() {
  const { chatId } = useParams<{ chatId?: string }>();
  const navigate = useNavigate();
  const myEntityId = useAuthStore(s => s.entityId);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewChat, setShowNewChat] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const chatsRef = useRef(chats);
  chatsRef.current = chats;
  const refresh = useCallback(() => {
    authFetch("/api/chats")
      .then(r => r.json())
      .then((data: ChatSummary[]) => {
        // Skip re-render if data unchanged (polling no-op guard)
        const prev = chatsRef.current;
        if (prev.length === data.length && JSON.stringify(prev) === JSON.stringify(data)) return;
        setChats(data);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // Poll every 5s while tab is visible
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    const start = () => { if (!timer) timer = setInterval(refresh, 5000); };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
    const onVis = () => document.visibilityState === "visible" ? start() : stop();
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
  }, [refresh]);

  const handleCreated = useCallback((newChatId: string) => {
    setShowNewChat(false);
    refresh();
    navigate(`/chats/${newChatId}`);
  }, [navigate, refresh]);

  // Sort: unread first, then by time
  const sorted = [...chats].sort((a, b) => {
    if (a.unread_count > 0 && b.unread_count === 0) return -1;
    if (b.unread_count > 0 && a.unread_count === 0) return 1;
    const ta = a.last_message?.created_at ?? 0;
    const tb = b.last_message?.created_at ?? 0;
    return tb - ta;
  });

  return (
    <div className="h-full w-full flex overflow-hidden">
      {/* Sidebar — mirrors Sidebar.tsx structure. Collapsible via header toggle. */}
      {!sidebarCollapsed && (
      <div className="w-72 h-full flex flex-col bg-card border-r border-border shrink-0">
        {/* Header — same as Sidebar.tsx */}
        <div className="px-4 pt-3 pb-1 flex items-center justify-between">
          <span className="text-sm font-semibold text-foreground">Chats</span>
        </div>

        {/* Search button — same style as Sidebar.tsx, opens modal */}
        <div className="px-3 pb-3">
          <button
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground/60 hover:bg-muted hover:text-foreground"
            onClick={() => setShowSearch(true)}
          >
            <Search className="w-4 h-4" />
            <span>Search chats...</span>
          </button>
        </div>

        <div className="h-px mx-3 bg-border" />

        {/* Chat list — same spacing as Sidebar.tsx thread list */}
        <div className="flex-1 min-h-0 px-3 pt-3 flex flex-col">
          <div className="flex items-center justify-between px-2 mb-2 flex-shrink-0">
            <span className="text-[11px] font-medium tracking-wider uppercase text-muted-foreground/60">Chats</span>
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] text-muted-foreground/40">{chats.length}</span>
              <button
                onClick={() => setShowNewChat(true)}
                className="text-[11px] text-muted-foreground/50 hover:text-foreground transition-colors px-1"
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto space-y-0.5 custom-scrollbar">
            {loading ? (
              <div className="space-y-0.5">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="px-3 py-2.5 rounded-lg animate-pulse">
                    <div className="h-4 w-[60%] bg-muted rounded mb-1.5" />
                    <div className="h-3 w-[40%] bg-muted rounded" />
                  </div>
                ))}
              </div>
            ) : sorted.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 px-4">
                <p className="text-xs text-muted-foreground mb-2">No chats yet</p>
                <button onClick={() => setShowNewChat(true)}
                  className="text-xs text-primary hover:underline">Start a conversation</button>
              </div>
            ) : sorted.map(chat => {
              const isActive = chatId === chat.id;
              const name = chatDisplayName(chat, myEntityId);
              const otherEntity = chat.entities.find(e => e.id !== myEntityId);
              return (
                <div key={chat.id} className={`group/item flex items-center rounded-lg transition-colors ${
                  isActive ? "bg-background shadow-sm" : "hover:bg-muted"
                }`}>
                  {/* Active indicator — same as Sidebar.tsx ThreadItem */}
                  <div className="relative w-7 flex-shrink-0 self-stretch flex items-center justify-center">
                    {isActive && (
                      <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-foreground" />
                    )}
                  </div>

                  <Link to={`/chats/${chat.id}`} className="flex-1 min-w-0 py-2.5 pr-2 flex items-center gap-2">
                    <MemberAvatar name={name} avatarUrl={otherEntity?.avatar_url} type={otherEntity?.type} size="xs" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-sm font-medium truncate ${isActive ? "text-foreground" : ""}`}>
                          {name}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className="text-[11px] text-muted-foreground/60 truncate flex-1 min-w-0">
                          {chat.last_message?.content || "No messages"}
                        </span>
                        {chat.last_message && (
                          <span className="text-[10px] text-muted-foreground/40 flex-shrink-0">
                            {formatTime(chat.last_message.created_at)}
                          </span>
                        )}
                      </div>
                    </div>
                    {chat.has_mention ? (
                      <span className="w-4 h-4 rounded-full bg-destructive text-destructive-foreground text-[9px] font-bold flex items-center justify-center shrink-0">@</span>
                    ) : chat.unread_count > 0 ? (
                      <span className="min-w-4 h-4 rounded-full bg-primary text-primary-foreground text-[9px] flex items-center justify-center px-1 shrink-0">
                        {chat.unread_count > 99 ? "99+" : chat.unread_count}
                      </span>
                    ) : null}
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      )}

      {/* Main content */}
      <div className="flex-1 min-w-0">
        <Outlet context={{ sidebarCollapsed, setSidebarCollapsed, refreshChatList: refresh }} />
      </div>

      {showNewChat && <NewChatDialog onClose={() => setShowNewChat(false)} onCreated={handleCreated} />}
      {showSearch && (
        <ChatSearchModal
          chats={chats}
          myEntityId={myEntityId}
          onSelect={(id) => navigate(`/chats/${id}`)}
          onClose={() => setShowSearch(false)}
        />
      )}
    </div>
  );
}
