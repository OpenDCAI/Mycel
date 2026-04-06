import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Outlet, useParams, useNavigate } from "react-router-dom";
import { Check, Plus, Search, Users, X } from "lucide-react";
import MemberAvatar from "../components/MemberAvatar";
import { authFetch, useAuthStore } from "../store/auth-store";
import type { ChatMember, ChatSummary } from "../api/types";

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  if (diffMs < 60_000) return "刚刚";
  if (diffMs < 3600_000) return `${Math.floor(diffMs / 60_000)}m`;
  if (diffMs < 86400_000) return `${Math.floor(diffMs / 3600_000)}h`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function chatDisplayName(chat: ChatSummary, myUserId: string | null): string {
  if (chat.title) return chat.title;
  const others = chat.entities.filter(e => e.id !== myUserId);
  return others.map(e => e.name).join(", ") || "Chat";
}

// @@@new-chat-dialog — member picker with multi-select for 1:1 and group chat
function NewChatDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (chatId: string) => void }) {
  const [members, setMembers] = useState<ChatMember[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const myUserId = useAuthStore(s => s.userId);

  useEffect(() => {
    authFetch("/api/entities")
      .then(r => r.json())
      .then((data: ChatMember[]) => setMembers(data))
      .catch(console.error);
  }, []);

  const filtered = search
    ? members.filter((e) => {
      const haystack = [e.name, e.owner_name || "", e.member_name || ""].join(" ").toLowerCase();
      return haystack.includes(search.toLowerCase());
    })
    : members;

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const isGroup = selected.size >= 2;
  const selectedEntities = members.filter(e => selected.has(e.id));

  const handleCreate = useCallback(async () => {
    if (!myUserId || selected.size === 0 || creating) return;
    setCreating(true);
    try {
      const body: Record<string, unknown> = { user_ids: [myUserId, ...selected] };
      if (isGroup && title.trim()) body.title = title.trim();
      const res = await authFetch("/api/chats", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `${res.status}`);
      }
      const data = await res.json();
      onCreated(data.id);
    } catch (err) {
      console.error("[NewChat] error:", err);
      setCreating(false);
    }
  }, [myUserId, selected, isGroup, title, creating, onCreated]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div className="w-full max-w-sm bg-card rounded-xl shadow-xl border border-border" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold">新建聊天</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </div>

        {/* Selected chips */}
        {selectedEntities.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-4 py-2 border-b border-border">
            {selectedEntities.map(e => (
              <button key={e.id} onClick={() => toggle(e.id)}
                className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs">
                {e.name} <X className="w-3 h-3" />
              </button>
            ))}
          </div>
        )}

        {/* Group title input — only when 2+ selected */}
        {isGroup && (
          <div className="px-4 py-2 border-b border-border">
            <input type="text" placeholder="群组名称（可选）" value={title}
              onChange={e => setTitle(e.target.value)}
              className="w-full text-sm bg-transparent outline-none text-foreground placeholder:text-muted-foreground/50" />
          </div>
        )}

        <div className="px-4 py-2">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border">
            <Search className="w-4 h-4 text-muted-foreground" />
            <input type="text" placeholder="搜索..." value={search} onChange={e => setSearch(e.target.value)}
              className="flex-1 bg-transparent text-sm outline-none" autoFocus />
          </div>
        </div>
        <div className="max-h-56 overflow-y-auto px-2 pb-2">
          {filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">
              {members.length === 0 ? "暂无其他用户" : "无匹配结果"}
            </p>
          ) : filtered.map(e => {
            const isSelected = selected.has(e.id);
            return (
              <button key={e.id} onClick={() => toggle(e.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg transition-colors duration-fast text-left ${
                  isSelected ? "bg-primary/5" : "hover:bg-muted"
                }`}>
                <MemberAvatar name={e.name} avatarUrl={e.avatar_url} type={e.type} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{e.name}</p>
                  <p className="text-2xs text-muted-foreground truncate">
                    {e.owner_name ? `owner: ${e.owner_name}` : "human"}
                  </p>
                </div>
                {isSelected && <Check className="w-4 h-4 text-primary shrink-0" />}
              </button>
            );
          })}
        </div>

        {/* Create button */}
        {selected.size > 0 && (
          <div className="px-4 py-3 border-t border-border">
            <button onClick={() => void handleCreate()} disabled={creating}
              className="w-full py-2 rounded-lg bg-foreground text-background text-sm font-medium hover:bg-foreground/90 disabled:opacity-50 transition-colors duration-fast">
              {creating ? "创建中..." : isGroup ? `创建群组 (${selected.size + 1})` : "开始对话"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// @@@chat-search-modal — same pattern as Threads SearchModal
function ChatSearchModal({ chats, myUserId, onSelect, onClose }: {
  chats: ChatSummary[];
  myUserId: string | null;
  onSelect: (chatId: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = query
    ? chats.filter(c => chatDisplayName(c, myUserId).toLowerCase().includes(query.toLowerCase()))
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
            placeholder="搜索聊天..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none text-foreground"
            autoFocus
          />
        </div>
        <div className="max-h-64 overflow-y-auto">
          {filtered.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">无结果</p>
          ) : filtered.map(chat => {
            const name = chatDisplayName(chat, myUserId);
            const otherMember = chat.entities.find(e => e.id !== myUserId);
            return (
              <button
                key={chat.id}
                onClick={() => { onSelect(chat.id); onClose(); }}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted transition-colors duration-fast text-left"
              >
                <MemberAvatar name={name} avatarUrl={otherMember?.avatar_url} type={otherMember?.type} size="sm" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{name}</p>
                  {chat.last_message && (
                    <p className="text-xs text-muted-foreground truncate">{chat.last_message.content}</p>
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
  const myUserId = useAuthStore(s => s.userId);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewChat, setShowNewChat] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const chatsRef = useRef(chats);
  useEffect(() => {
    chatsRef.current = chats;
  }, [chats]);

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
          <span className="text-sm font-semibold text-foreground">对话</span>
        </div>

        {/* Search button — same style as Sidebar.tsx, opens modal */}
        <div className="px-3 pb-3">
          <button
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground/60 hover:bg-muted hover:text-foreground"
            onClick={() => setShowSearch(true)}
          >
            <Search className="w-4 h-4" />
            <span>搜索聊天...</span>
          </button>
        </div>

        <div className="h-px mx-3 bg-border" />

        {/* Chat list — same spacing as Sidebar.tsx thread list */}
        <div className="flex-1 min-h-0 px-3 pt-3 flex flex-col">
          <div className="flex items-center justify-between px-2 mb-2 flex-shrink-0">
            <span className="text-xs font-medium tracking-wider uppercase text-muted-foreground/60">聊天</span>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground/40">{chats.length}</span>
              <button
                onClick={() => setShowNewChat(true)}
                className="text-xs text-muted-foreground/50 hover:text-foreground transition-colors duration-fast px-1"
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
                <p className="text-xs text-muted-foreground mb-2">暂无聊天</p>
                <button onClick={() => setShowNewChat(true)}
                  className="text-xs text-primary hover:underline">开始对话</button>
              </div>
            ) : sorted.map(chat => {
              const isActive = chatId === chat.id;
              const name = chatDisplayName(chat, myUserId);
              const others = chat.entities.filter(e => e.id !== myUserId);
              const isGroupChat = others.length > 1;
              return (
                <div key={chat.id} className={`group/item flex items-center rounded-lg transition-colors duration-fast ${
                  isActive ? "bg-background shadow-sm" : "hover:bg-muted"
                }`}>
                  {/* Active indicator — same as Sidebar.tsx ThreadItem */}
                  <div className="relative w-7 flex-shrink-0 self-stretch flex items-center justify-center">
                    {isActive && (
                      <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-foreground" />
                    )}
                  </div>

                  <Link to={`/chats/${chat.id}`} className="flex-1 min-w-0 py-2.5 pr-2 flex items-center gap-2">
                    {isGroupChat ? (
                      <div className="relative w-7 h-7 shrink-0">
                        <Users className="w-7 h-7 p-1.5 rounded-full bg-muted text-muted-foreground" />
                        <span className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-foreground text-background text-3xs font-bold flex items-center justify-center">
                          {others.length + 1}
                        </span>
                      </div>
                    ) : (
                      <MemberAvatar name={name} avatarUrl={others[0]?.avatar_url} type={others[0]?.type} size="xs" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className={`text-sm font-medium truncate ${isActive ? "text-foreground" : ""}`}>
                          {name}
                        </span>
                      </div>
                      <div className="flex items-center gap-1 mt-0.5">
                        <span className="text-xs text-muted-foreground/60 truncate flex-1 min-w-0">
                          {chat.last_message?.content || "暂无消息"}
                        </span>
                        {chat.last_message && (
                          <span className="text-2xs text-muted-foreground/40 flex-shrink-0">
                            {formatTime(chat.last_message.created_at)}
                          </span>
                        )}
                      </div>
                    </div>
                    {chat.has_mention ? (
                      <span className="w-4 h-4 rounded-full bg-destructive text-destructive-foreground text-2xs font-bold flex items-center justify-center shrink-0">@</span>
                    ) : chat.unread_count > 0 ? (
                      <span className="min-w-4 h-4 rounded-full bg-primary text-primary-foreground text-2xs flex items-center justify-center px-1 shrink-0">
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
          myUserId={myUserId}
          onSelect={(id) => navigate(`/chats/${id}`)}
          onClose={() => setShowSearch(false)}
        />
      )}
    </div>
  );
}
