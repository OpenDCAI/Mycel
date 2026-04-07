import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useOutletContext } from "react-router-dom";
import { PanelLeft } from "lucide-react";
import { authFetch, useAuthStore } from "../store/auth-store";
import { UserBubble } from "../components/chat-area/UserBubble";
import { ChatBubble } from "../components/chat-area/ChatBubble";
import { supabase } from "../lib/supabase";
import InputBox from "../components/InputBox";
import type { ChatMember, ChatMessage, ChatDetail } from "../api/types";

// @@@time-gap — only show timestamp when gap >= 5 minutes
function shouldShowTime(prev: ChatMessage | null, curr: ChatMessage): boolean {
  if (!prev) return true;
  return (curr.created_at - prev.created_at) >= 300;
}

function formatMessageTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function chatMemberDisplayName(member: ChatMember | undefined, defaultName: string): string {
  return member?.name || defaultName;
}

export default function ChatConversationPage() {
  const { chatId } = useParams<{ chatId: string }>();
  if (!chatId) return null;
  return <ChatConversationInner key={chatId} chatId={chatId} />;
}

function ChatConversationInner({ chatId }: { chatId: string }) {
  const { setSidebarCollapsed, refreshChatList: _refreshRaw } = useOutletContext<{
    sidebarCollapsed: boolean;
    setSidebarCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
    refreshChatList: () => void;
  }>();

  // Debounce refreshChatList — SSE bursts can fire many times per second
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshChatList = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = setTimeout(() => { refreshTimer.current = null; _refreshRaw(); }, 1000);
  }, [_refreshRaw]);
  useEffect(() => () => { if (refreshTimer.current) clearTimeout(refreshTimer.current); }, []);

  const myUserId = useAuthStore(s => s.userId);
  const myName = useAuthStore(s => s.user?.name) || "You";
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  // read_status: {user_id → last_read_at ISO} for all members
  const [readStatus, setReadStatus] = useState<Record<string, string | null>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  const memberMap = useMemo(() => {
    const m = new Map<string, ChatMember>();
    chat?.entities.forEach(e => m.set(e.id, e));
    return m;
  }, [chat?.entities]);
  // Stable ref so Realtime handler always sees latest memberMap without re-subscribing
  const memberMapRef = useRef(memberMap);
  useEffect(() => { memberMapRef.current = memberMap; }, [memberMap]);
  // Track if user is at bottom for sticky scroll
  const onScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }, []);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  // Load chat detail + messages
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      authFetch(`/api/chats/${chatId}`).then(r => {
        if (!r.ok) throw new Error(`Chat not found (${r.status})`);
        return r.json();
      }),
      authFetch(`/api/chats/${chatId}/messages?limit=100`).then(r => {
        if (!r.ok) throw new Error(`Messages load failed (${r.status})`);
        return r.json();
      }),
    ])
      .then(([chatData, msgsData]) => {
        if (cancelled) return;
        setChat(chatData);
        setReadStatus(chatData.read_status ?? {});
        // Normalize created_at: API may return ISO string or Unix number
        const normalizedMsgs = (msgsData as ChatMessage[]).map(m => ({
          ...m,
          created_at: typeof m.created_at === "string"
            ? new Date(m.created_at).getTime() / 1000
            : m.created_at,
        }));
        setMessages(normalizedMsgs);
        setLoading(false);
        // Mark read + refresh sidebar
        authFetch(`/api/chats/${chatId}/read`, { method: "POST" })
          .then(() => refreshChatList())
          .catch(err => console.warn("[mark_read] failed:", err));
      })
      .catch(err => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [chatId, refreshChatList]);

  // Scroll to bottom on initial load
  useEffect(() => {
    if (!loading && messages.length > 0) {
      setTimeout(() => messagesEndRef.current?.scrollIntoView(), 50);
    }
  }, [loading, messages.length]);

  // Supabase Realtime for incoming DM messages
  // SSE is for agent streaming only — human↔human chat uses Realtime directly
  useEffect(() => {
    if (!supabase || !chatId) return;

    const sub = supabase
      .channel(`chat-messages-${chatId}`)
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "messages", filter: `chat_id=eq.${chatId}` },
        (payload: { new: Record<string, unknown> }) => {
          const raw = payload.new;
          const senderId = String(raw.sender_id ?? "");
          const senderName = memberMapRef.current.get(senderId)?.name ?? "未知";
          const msg: ChatMessage = {
            id: String(raw.id),
            chat_id: String(raw.chat_id),
            sender_id: senderId,
            sender_name: senderName,
            content: String(raw.content ?? ""),
            message_type: String(raw.message_type ?? "human"),
            mentioned_ids: (raw.mentions as string[]) ?? [],
            signal: raw.signal ? String(raw.signal) : null,
            retracted_at: raw.retracted_at ? String(raw.retracted_at) : null,
            created_at: typeof raw.created_at === "string"
              ? new Date(raw.created_at).getTime() / 1000
              : Number(raw.created_at ?? Date.now() / 1000),
          };
          setMessages(prev => {
            if (prev.some(m => m.id === msg.id)) return prev;
            const optimisticIdx = prev.findIndex(
              m => m.id.startsWith("optimistic-") && m.sender_id === msg.sender_id && m.content === msg.content,
            );
            if (optimisticIdx >= 0) {
              const next = [...prev];
              next[optimisticIdx] = msg;
              return next;
            }
            return [...prev, msg];
          });
          if (isAtBottomRef.current) {
            setTimeout(scrollToBottom, 50);
            authFetch(`/api/chats/${chatId}/read`, { method: "POST" }).catch(() => {});
            refreshChatList();
          }
        }
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(sub);
      refreshChatList();
    };
  }, [chatId, scrollToBottom, refreshChatList]);

  // Send message — text comes from InputBox, not internal state
  const handleSend = useCallback(async (text: string) => {
    if (!text.trim() || !myUserId || sending) return;
    setSending(true);

    // Optimistic insert
    const optimisticMsg: ChatMessage = {
      id: `optimistic-${Date.now()}`,
      chat_id: chatId,
      sender_id: myUserId,
      sender_name: useAuthStore.getState().user?.name || "me",
      content: text,
      mentioned_ids: [],
      created_at: Date.now() / 1000,
    };
    setMessages(prev => [...prev, optimisticMsg]);
    setTimeout(scrollToBottom, 50);

    try {
      const res = await authFetch(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content: text,
          sender_id: myUserId,
        }),
      });
      if (!res.ok) {
        console.error("[ChatSend] failed:", res.status);
        // Remove optimistic message on failure
        setMessages(prev => prev.filter(m => m.id !== optimisticMsg.id));
      } else {
        const rawReal = await res.json();
        const real: ChatMessage = {
          ...rawReal,
          created_at: typeof rawReal.created_at === "string"
            ? new Date(rawReal.created_at).getTime() / 1000
            : rawReal.created_at,
        };
        // Replace optimistic with real if it still exists (SSE might have already replaced it)
        setMessages(prev => {
          const hasOptimistic = prev.some(m => m.id === optimisticMsg.id);
          if (!hasOptimistic) return prev; // SSE already handled it
          const hasReal = prev.some(m => m.id === real.id);
          if (hasReal) return prev.filter(m => m.id !== optimisticMsg.id); // SSE added real, remove optimistic
          return prev.map(m => m.id === optimisticMsg.id ? real : m);
        });
      }
    } catch (err) {
      console.error("[ChatSend] error:", err);
      setMessages(prev => prev.filter(m => m.id !== optimisticMsg.id));
    } finally {
      setSending(false);
      refreshChatList(); // update last_message in sidebar
    }
  }, [myUserId, sending, chatId, scrollToBottom, refreshChatList]);

  // Realtime: update read_status when any member opens the chat
  useEffect(() => {
    if (!supabase || !chatId) return;
    const sub = supabase
      .channel(`chat-members-${chatId}`)
      .on(
        "postgres_changes",
        { event: "UPDATE", schema: "public", table: "chat_members", filter: `chat_id=eq.${chatId}` },
        (payload: { new: { user_id?: string; last_read_at?: string | null } }) => {
          const row = payload.new;
          if (row.user_id) {
            setReadStatus(prev => ({ ...prev, [row.user_id!]: row.last_read_at ?? null }));
          }
        }
      )
      .subscribe();
    return () => { void supabase.removeChannel(sub); };
  }, [chatId]);


  // Display name for header
  const chatName = chat
    ? chat.title || chat.entities.filter(e => e.id !== myUserId).map(e => e.name).join(", ") || "聊天"
    : "聊天";

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-2">
        <p className="text-sm text-destructive">{error}</p>
        <Link to="/chat" className="text-xs text-primary hover:underline">返回对话列表</Link>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col min-h-0">
      {/* Header — matches Threads Header.tsx structure */}
      <header className="h-12 flex items-center justify-between px-4 flex-shrink-0 bg-card border-b border-border">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => setSidebarCollapsed(v => !v)}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
          <span className="text-sm font-medium text-foreground truncate max-w-[200px]">
            {chatName}
          </span>
          {chat && chat.entities.length > 2 && (
            <span className="text-2xs px-1.5 py-0.5 rounded-md font-medium border border-border text-muted-foreground bg-muted">
              {chat.entities.length} 位成员
            </span>
          )}
        </div>
      </header>

      {/* Messages */}
      <div
        ref={scrollContainerRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto px-5 py-5 bg-background"
      >
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-muted-foreground">发送一条消息开始对话</p>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto space-y-3.5">
            {messages.map((msg, i) => {
              const isMine = msg.sender_id === myUserId;
              const prev = i > 0 ? messages[i - 1] : null;
              const showTime = shouldShowTime(prev, msg);
              const member = memberMap.get(msg.sender_id);
              const ts = msg.created_at * 1000;

              // Read receipt: check if all other members have last_read_at >= this message
              const isLastMine = isMine && messages.slice(i + 1).every(m => m.sender_id !== myUserId);
              const otherMemberIds = chat?.entities.map(e => e.id).filter(id => id !== myUserId) ?? [];
              const isRead = otherMemberIds.length > 0 && otherMemberIds.every(uid => {
                const lra = readStatus[uid];
                if (!lra) return false;
                return new Date(lra).getTime() >= msg.created_at * 1000;
              });

              return (
                <div key={msg.id}>
                  {showTime && (
                    <div className="text-center my-3">
                      <span className="text-2xs text-muted-foreground/30 bg-muted px-2 py-0.5 rounded-full">
                        {formatMessageTime(msg.created_at)}
                      </span>
                    </div>
                  )}
                  {isMine ? (
                    <div className="flex flex-col items-end gap-0.5">
                      <UserBubble content={msg.content} timestamp={ts} userName={myName} avatarUrl={memberMap.get(myUserId!)?.avatar_url} />
                      {isLastMine && (
                        <span className={`text-2xs px-1 ${isRead ? "text-primary" : "text-muted-foreground/40"}`}>
                          {isRead ? "已读" : "未读"}
                        </span>
                      )}
                    </div>
                  ) : (
                    <ChatBubble
                      content={msg.content}
                      senderName={chatMemberDisplayName(member, msg.sender_name)}
                      avatarUrl={member?.avatar_url}
                      entityType={member?.type}
                      timestamp={ts}
                      showName
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input — same InputBox as Agent workspace */}
      <InputBox
        placeholder="输入消息..."
        disabled={sending}
        onSendMessage={handleSend}
      />
    </div>
  );
}
