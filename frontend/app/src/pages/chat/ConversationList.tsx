/**
 * ConversationList — production chat sidebar
 *
 * Data sources (no duplicates):
 *   • /api/chats  → all active chats with entity info (primary source)
 *       - entities all human      → "消息" section
 *       - any entity is agent     → "Agent" section
 *   • /api/conversations type=hire + member_id  → dedicated agent threads
 *       - NOT shown from visit type (those are the same rows as /api/chats)
 *
 * CRUD:
 *   C — + button → NewChatDialog (create DM or group)
 *   R — list with sort (unread first, pinned first, then by time)
 *   U — context menu: rename, mute/unmute, pin/unpin
 *   D — context menu: delete (1:1) / leave (group)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { MoreHorizontal, Pencil, Pin, PinOff, Bell, BellOff, LogOut, Trash2, Plus, Search, Users, X } from "lucide-react";
import MemberAvatar from "@/components/MemberAvatar";
import { useConversationStore } from "@/store/conversation-store";
import { useChatStore } from "@/store/chat-store";
import { useAuthStore } from "@/store/auth-store";
import { supabase } from "@/lib/supabase";
import type { ChatSummary } from "@/store/chat-store";
import type { ConversationItem } from "@/types/conversation";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(dateStr: string | number | null | undefined): string {
  if (!dateStr) return "";
  const d = typeof dateStr === "number" ? new Date(dateStr * 1000) : new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  if (diffMs < 60_000) return "刚刚";
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}h`;
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function chatDisplayName(chat: ChatSummary, myUserId: string | null): string {
  if (chat.title) return chat.title;
  const others = chat.entities.filter(e => e.id !== myUserId);
  return others.map(e => e.name).join(", ") || "聊天";
}

function isAgentChat(chat: ChatSummary, myUserId: string | null): boolean {
  return chat.entities.some(e => e.id !== myUserId && e.type !== "human");
}

// ---------------------------------------------------------------------------
// Rename dialog
// ---------------------------------------------------------------------------

function RenameDialog({ chatId, currentTitle, onClose }: {
  chatId: string;
  currentTitle: string;
  onClose: () => void;
}) {
  const [value, setValue] = useState(currentTitle);
  const [saving, setSaving] = useState(false);
  const renameChat = useChatStore(s => s.renameChat);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { inputRef.current?.select(); }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!value.trim() || saving) return;
    setSaving(true);
    try {
      await renameChat(chatId, value.trim());
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/40" onClick={onClose} />
      <div className="fixed inset-x-0 top-1/3 z-50 mx-auto w-full max-w-xs bg-card border border-border rounded-xl shadow-2xl overflow-hidden p-4">
        <h3 className="text-sm font-semibold mb-3">重命名对话</h3>
        <form onSubmit={e => void handleSubmit(e)}>
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={e => setValue(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 mb-3"
            maxLength={64}
          />
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={onClose}
              className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors duration-fast">
              取消
            </button>
            <button type="submit" disabled={saving || !value.trim()}
              className="px-3 py-1.5 text-xs bg-primary text-primary-foreground rounded-lg hover:opacity-90 disabled:opacity-50 transition-colors duration-fast">
              {saving ? "保存中..." : "确认"}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Search modal
// ---------------------------------------------------------------------------

function SearchModal({ chats, agentConvs, myUserId, onClose }: {
  chats: ChatSummary[];
  agentConvs: ConversationItem[];
  myUserId: string | null;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const q = query.toLowerCase();
  const matchedChats = q
    ? chats.filter(c => chatDisplayName(c, myUserId).toLowerCase().includes(q))
    : chats;
  const matchedAgents = q
    ? agentConvs.filter(c => c.title.toLowerCase().includes(q))
    : agentConvs;
  const empty = matchedChats.length === 0 && matchedAgents.length === 0;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <div className="fixed inset-x-0 top-20 z-50 mx-auto w-full max-w-md bg-card border border-border rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <Search className="w-4 h-4 text-muted-foreground shrink-0" />
          <input type="text" placeholder="搜索聊天..." value={query} onChange={e => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-sm outline-none text-foreground" autoFocus />
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition-colors duration-fast">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="max-h-72 overflow-y-auto custom-scrollbar">
          {empty ? (
            <p className="text-xs text-muted-foreground text-center py-6">无结果</p>
          ) : (
            <>
              {matchedChats.map(chat => {
                const name = chatDisplayName(chat, myUserId);
                const other = chat.entities.find(e => e.id !== myUserId);
                return (
                  <button key={chat.id} onClick={() => { navigate(`/chat/visit/${chat.id}`); onClose(); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted transition-colors duration-fast text-left">
                    <MemberAvatar name={name} avatarUrl={other?.avatar_url} type={other?.type ?? "human"} size="sm" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{name}</p>
                      {chat.last_message && (
                        <p className="text-xs text-muted-foreground truncate">{chat.last_message.content}</p>
                      )}
                    </div>
                  </button>
                );
              })}
              {matchedAgents.map(item => {
                const href = `/chat/hire/${encodeURIComponent(item.member_id ?? "")}/${encodeURIComponent(item.id)}`;
                return (
                  <button key={item.id} onClick={() => { navigate(href); onClose(); }}
                    className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-muted transition-colors duration-fast text-left">
                    <MemberAvatar name={item.title} avatarUrl={item.avatar_url ?? undefined} type="mycel_agent" size="sm" />
                    <p className="text-sm font-medium truncate flex-1">{item.title}</p>
                  </button>
                );
              })}
            </>
          )}
        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Chat item with context menu (full CRUD)
// ---------------------------------------------------------------------------

function ChatItem({ chat, myUserId, isActive }: {
  chat: ChatSummary;
  myUserId: string | null;
  isActive: boolean;
}) {
  const [renaming, setRenaming] = useState(false);
  const { toggleMute, togglePin, deleteChat, leaveChat, fetchChats } = useChatStore();
  const navigate = useNavigate();
  const isGroup = chat.entities.filter(e => e.id !== myUserId).length > 1;
  const isAgent = isAgentChat(chat, myUserId);
  const others = chat.entities.filter(e => e.id !== myUserId);
  const other = others[0];
  const name = chatDisplayName(chat, myUserId);
  const lastMsg = chat.last_message;
  const href = `/chat/visit/${chat.id}`;

  async function handleDelete() {
    if (!confirm(`确认${isGroup ? "退出" : "删除"}「${name}」？`)) return;
    if (isGroup) {
      await leaveChat(chat.id);
    } else {
      await deleteChat(chat.id);
    }
    if (isActive) navigate("/chat");
  }

  return (
    <>
      <div className={`group/item flex items-center rounded-lg transition-colors duration-fast ${
        isActive ? "bg-background shadow-sm" : "hover:bg-muted"
      }`}>
        {/* Active indicator */}
        <div className="relative w-5 flex-shrink-0 self-stretch flex items-center justify-center">
          {isActive && <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-foreground" />}
        </div>

        <Link to={href} className="flex-1 min-w-0 py-2.5 flex items-center gap-2 pr-1">
          {isGroup ? (
            <div className="relative w-7 h-7 shrink-0">
              <Users className="w-7 h-7 p-1.5 rounded-full bg-muted text-muted-foreground" />
              <span className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-foreground text-background text-3xs font-bold flex items-center justify-center">
                {chat.entities.length}
              </span>
            </div>
          ) : (
            <MemberAvatar name={name} avatarUrl={other?.avatar_url} type={isAgent ? other?.type : "human"} size="xs" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1">
              {chat.pinned && <Pin className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" />}
              <span className="text-sm font-medium truncate text-foreground">{name}</span>
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-xs text-muted-foreground/60 truncate flex-1 min-w-0">
                {lastMsg ? `${lastMsg.sender_name}: ${lastMsg.content}` : "暂无消息"}
              </span>
              {lastMsg?.created_at && (
                <span className="text-2xs text-muted-foreground/40 flex-shrink-0">{formatTime(lastMsg.created_at)}</span>
              )}
            </div>
          </div>
          {chat.unread_count > 0 && (
            <span className={`min-w-4 h-4 rounded-full text-2xs flex items-center justify-center px-1 shrink-0 ${
              chat.muted ? "bg-muted text-muted-foreground" : "bg-primary text-primary-foreground"
            }`}>
              {chat.unread_count > 99 ? "99+" : chat.unread_count}
            </span>
          )}
        </Link>

        {/* Context menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="p-1 rounded text-muted-foreground hover:text-foreground opacity-0 group-hover/item:opacity-100 transition-all duration-fast mr-1 shrink-0">
              <MoreHorizontal className="w-3.5 h-3.5" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem onClick={() => setRenaming(true)}>
              <Pencil className="w-3.5 h-3.5 mr-2" />重命名
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => void togglePin(chat.id, !chat.pinned)}>
              {chat.pinned
                ? <><PinOff className="w-3.5 h-3.5 mr-2" />取消置顶</>
                : <><Pin className="w-3.5 h-3.5 mr-2" />置顶</>}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => void toggleMute(chat.id, myUserId ?? "", !chat.muted)}>
              {chat.muted
                ? <><Bell className="w-3.5 h-3.5 mr-2" />取消免打扰</>
                : <><BellOff className="w-3.5 h-3.5 mr-2" />免打扰</>}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => void handleDelete()}>
              {isGroup
                ? <><LogOut className="w-3.5 h-3.5 mr-2" />退出群聊</>
                : <><Trash2 className="w-3.5 h-3.5 mr-2" />删除对话</>}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {renaming && (
        <RenameDialog
          chatId={chat.id}
          currentTitle={name}
          onClose={() => { setRenaming(false); void fetchChats(); }}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Agent thread item (from /api/conversations hire type)
// ---------------------------------------------------------------------------

function AgentThreadItem({ item, isActive }: { item: ConversationItem; isActive: boolean }) {
  const href = item.member_id
    ? `/chat/hire/${encodeURIComponent(item.member_id)}/${encodeURIComponent(item.id)}`
    : `/chat/visit/${encodeURIComponent(item.id)}`;

  return (
    <div className={`group/item flex items-center rounded-lg transition-colors duration-fast ${
      isActive ? "bg-background shadow-sm" : "hover:bg-muted"
    }`}>
      <div className="relative w-5 flex-shrink-0 self-stretch flex items-center justify-center">
        {isActive && <div className="absolute left-0 top-2 bottom-2 w-0.5 rounded-r-full bg-foreground" />}
      </div>
      <Link to={href} className="flex-1 min-w-0 py-2.5 pr-2 flex items-center gap-2">
        <div className="relative">
          <MemberAvatar name={item.title} avatarUrl={item.avatar_url ?? undefined} type="mycel_agent" size="xs" />
          {item.running && (
            <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-success border-2 border-card" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-sm font-medium truncate text-foreground block">{item.title}</span>
          {item.updated_at && (
            <span className="text-xs text-muted-foreground/60">{formatTime(item.updated_at)}</span>
          )}
        </div>
        {item.unread_count > 0 && (
          <span className="min-w-4 h-4 rounded-full bg-primary text-primary-foreground text-2xs flex items-center justify-center px-1 shrink-0">
            {item.unread_count > 99 ? "99+" : item.unread_count}
          </span>
        )}
      </Link>
    </div>
  );
}

// ---------------------------------------------------------------------------
// New chat dialog wrapper
// ---------------------------------------------------------------------------

function NewChatWrapper({ onClose }: { onClose: (newChatId?: string) => void }) {
  const [Dialog, setDialog] = useState<React.ComponentType<{
    open: boolean;
    onOpenChange: (v: boolean) => void;
  }> | null>(null);

  useEffect(() => {
    import("@/components/NewChatDialog").then(m => setDialog(() => m.default));
  }, []);

  if (!Dialog) return null;
  return <Dialog open onOpenChange={v => { if (!v) onClose(); }} />;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ConversationList() {
  const { conversations, fetchConversations } = useConversationStore();
  const { chats, fetchChats } = useChatStore();
  const myUserId = useAuthStore(s => s.userId);
  const [showSearch, setShowSearch] = useState(false);
  const [showNewChat, setShowNewChat] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  // Poll agent threads
  useEffect(() => {
    void fetchConversations();
    let timer: ReturnType<typeof setInterval> | null = null;
    const start = () => { if (!timer) timer = setInterval(() => void useConversationStore.getState().fetchConversations(), 5000); };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };
    const onVis = () => document.visibilityState === "visible" ? start() : stop();
    start();
    document.addEventListener("visibilitychange", onVis);
    return () => { stop(); document.removeEventListener("visibilitychange", onVis); };
  }, [fetchConversations]);

  // Fetch DM chats
  useEffect(() => { void fetchChats(); }, [fetchChats]);

  // Realtime: refresh on new messages
  useEffect(() => {
    if (!supabase) return;
    const sub = supabase
      .channel("conv-list-messages")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "messages" }, () => {
        void useChatStore.getState().fetchChats();
      })
      .subscribe();
    return () => { void supabase!.removeChannel(sub); };
  }, []);

  // ---------------------------------------------------------------------------
  // Data preparation — /api/chats is the single source for chats
  // /api/conversations only contributes type=hire WITH member_id (true agent threads)
  // visit type from /api/conversations is the same data as /api/chats — skip it
  // ---------------------------------------------------------------------------

  // Human DMs: all entities are human
  const humanChats = chats
    .filter(c => !isAgentChat(c, myUserId))
    .sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      if (a.unread_count > 0 && b.unread_count === 0) return -1;
      if (b.unread_count > 0 && a.unread_count === 0) return 1;
      const at = a.last_message?.created_at ?? String(a.created_at);
      const bt = b.last_message?.created_at ?? String(b.created_at);
      return String(bt).localeCompare(String(at));
    });

  // Agent DM chats: some entity is an agent
  const agentDMChats = chats
    .filter(c => isAgentChat(c, myUserId))
    .sort((a, b) => {
      const at = a.last_message?.created_at ?? String(a.created_at);
      const bt = b.last_message?.created_at ?? String(b.created_at);
      return String(bt).localeCompare(String(at));
    });

  // Dedicated agent threads: hire type with member_id, not already in /api/chats
  const chatIds = new Set(chats.map(c => c.id));
  const agentThreads = conversations.filter(
    c => c.type === "hire" && c.member_id && !chatIds.has(c.id)
  );

  const totalItems = humanChats.length + agentDMChats.length + agentThreads.length;

  const handleNewChatCreated = useCallback((_chatId?: string) => {
    setShowNewChat(false);
    void fetchChats();
    void fetchConversations();
    if (_chatId) navigate(`/chat/visit/${_chatId}`);
  }, [fetchChats, fetchConversations, navigate]);

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="px-4 pt-3 pb-1 flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">对话</span>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground/40">{totalItems}</span>
          <button onClick={() => setShowNewChat(true)}
            className="text-muted-foreground/50 hover:text-foreground transition-colors duration-fast px-1">
            <Plus className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Search trigger */}
      <div className="px-3 pb-3">
        <button
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-muted-foreground/60 hover:bg-muted hover:text-foreground transition-colors duration-fast"
          onClick={() => setShowSearch(true)}
        >
          <Search className="w-4 h-4" />
          <span>搜索聊天...</span>
        </button>
      </div>

      <div className="h-px mx-3 bg-border" />

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto px-2 pt-2 custom-scrollbar">
        {totalItems === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 px-4">
            <p className="text-xs text-muted-foreground mb-2">暂无对话</p>
            <button onClick={() => setShowNewChat(true)} className="text-xs text-primary hover:underline">
              开始第一个对话
            </button>
          </div>
        ) : (
          <>
            {/* Human DMs */}
            {humanChats.length > 0 && (
              <div className="mb-1">
                <div className="px-2 py-1">
                  <span className="text-2xs font-semibold tracking-widest uppercase text-muted-foreground/50">消息</span>
                </div>
                {humanChats.map(chat => (
                  <ChatItem
                    key={chat.id}
                    chat={chat}
                    myUserId={myUserId}
                    isActive={location.pathname === `/chat/visit/${chat.id}`}
                  />
                ))}
              </div>
            )}

            {/* Agent DM chats + agent threads */}
            {(agentDMChats.length > 0 || agentThreads.length > 0) && (
              <div className={humanChats.length > 0 ? "mt-2 pt-2 border-t border-border" : ""}>
                <div className="px-2 py-1">
                  <span className="text-2xs font-semibold tracking-widest uppercase text-muted-foreground/50">Agent</span>
                </div>
                {agentDMChats.map(chat => (
                  <ChatItem
                    key={chat.id}
                    chat={chat}
                    myUserId={myUserId}
                    isActive={location.pathname === `/chat/visit/${chat.id}`}
                  />
                ))}
                {agentThreads.map(item => {
                  const href = `/chat/hire/${encodeURIComponent(item.member_id ?? "")}/${encodeURIComponent(item.id)}`;
                  const isActive = location.pathname === href || location.pathname.startsWith(href + "/");
                  return <AgentThreadItem key={`hire-${item.id}`} item={item} isActive={isActive} />;
                })}
              </div>
            )}
          </>
        )}
      </div>

      {showSearch && (
        <SearchModal
          chats={[...humanChats, ...agentDMChats]}
          agentConvs={agentThreads}
          myUserId={myUserId}
          onClose={() => setShowSearch(false)}
        />
      )}

      {showNewChat && <NewChatWrapper onClose={handleNewChatCreated} />}
    </div>
  );
}
