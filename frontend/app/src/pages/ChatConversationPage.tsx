import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link, useOutletContext } from "react-router-dom";
import { Check, Clipboard, PanelLeft, Send, UserPlus, X } from "lucide-react";
import { authFetch, useAuthStore } from "../store/auth-store";
import { parseChatMessageEventData, parseChatTypingUserId, streamChatEvents } from "../api/chat-events";
import { UserBubble } from "../components/chat-area/UserBubble";
import { ChatBubble } from "../components/chat-area/ChatBubble";
import type { ChatMember, ChatMessage, ChatDetail, ChatJoinRequest, ChatJoinTarget } from "../api/types";

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
  const [joinTarget, setJoinTarget] = useState<ChatJoinTarget | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [joinMessage, setJoinMessage] = useState("");
  const [joinSubmitting, setJoinSubmitting] = useState(false);
  const [joinSubmitError, setJoinSubmitError] = useState<string | null>(null);
  const [joinRequests, setJoinRequests] = useState<ChatJoinRequest[]>([]);
  const [joinRequestError, setJoinRequestError] = useState<string | null>(null);
  const [joinRequestBusyId, setJoinRequestBusyId] = useState<string | null>(null);
  const [shareStatus, setShareStatus] = useState<string | null>(null);
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  const memberMap = useMemo(() => {
    const m = new Map<string, ChatMember>();
    chat?.members.forEach(member => m.set(member.id, member));
    return m;
  }, [chat?.members]);

  const isGroupOwner = Boolean(chat && chat.type === "group" && chat.created_by_user_id === myUserId);
  const pendingJoinRequests = useMemo(
    () => joinRequests.filter(request => request.state === "pending"),
    [joinRequests],
  );

  const loadJoinRequests = useCallback(async () => {
    if (!isGroupOwner) {
      setJoinRequests([]);
      setJoinRequestError(null);
      return;
    }
    const res = await authFetch(`/api/chats/${chatId}/join-requests`);
    if (!res.ok) {
      const body = await res.text();
      throw new Error(body || `Join requests load failed (${res.status})`);
    }
    setJoinRequests(await res.json());
    setJoinRequestError(null);
  }, [chatId, isGroupOwner]);

  useEffect(() => {
    loadJoinRequests().catch(err => setJoinRequestError(err.message));
  }, [loadJoinRequests]);
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
    setJoinSubmitError(null);

    async function load() {
      const chatRes = await authFetch(`/api/chats/${chatId}`);
      if (chatRes.status === 403) {
        const targetRes = await authFetch(`/api/chats/${chatId}/join-target`);
        if (!targetRes.ok) {
          const body = await targetRes.text();
          throw new Error(body || `Join target load failed (${targetRes.status})`);
        }
        const targetData: ChatJoinTarget = await targetRes.json();
        if (cancelled) return;
        if (targetData.is_member) {
          setError("当前会话状态已变化，请刷新页面");
          setLoading(false);
          return;
        }
        setChat(null);
        setMessages([]);
        setJoinTarget(targetData);
        setLoading(false);
        return;
      }
      if (!chatRes.ok) throw new Error(`Chat not found (${chatRes.status})`);
      const chatData: ChatDetail = await chatRes.json();
      const msgsRes = await authFetch(`/api/chats/${chatId}/messages?limit=100`);
      if (!msgsRes.ok) throw new Error(`Messages load failed (${msgsRes.status})`);
      const msgsData: ChatMessage[] = await msgsRes.json();
      if (!cancelled) {
        setChat(chatData);
        setJoinTarget(null);
        setMessages(msgsData);
        setLoading(false);
        // Mark read + refresh sidebar
        authFetch(`/api/chats/${chatId}/read`, { method: "POST" })
          .then(() => refreshChatList())
          .catch(err => console.warn("[mark_read] failed:", err));
      }
    }

    load()
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

  // SSE for real-time messages
  useEffect(() => {
    if (!chat) return;
    const ac = new AbortController();
    // @@@pagehide-abort — browser-level navigation can destroy the page before React unmount finishes
    const handlePageHide = () => ac.abort();
    window.addEventListener("pagehide", handlePageHide);

    void streamChatEvents(
      chatId,
      (event) => {
        if (event.type === "message") {
          const msg = parseChatMessageEventData(event.data);
          setMessages(prev => {
            // Skip if we already have this exact message id
            if (prev.some(m => m.id === msg.id)) return prev;
            // Replace optimistic message if sender+content matches
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
            // User is viewing → mark read + refresh sidebar
            authFetch(`/api/chats/${chatId}/read`, { method: "POST" }).catch(err => console.warn("[mark_read] failed:", err));
            refreshChatList();
          }
          return;
        }
        if (event.type === "typing_start") {
          const userId = parseChatTypingUserId(event.data);
          if (userId) setTypingUsers(prev => new Set([...prev, userId]));
          return;
        }
        if (event.type === "typing_stop") {
          const userId = parseChatTypingUserId(event.data);
          if (!userId) return;
          setTypingUsers(prev => {
            const next = new Set(prev);
            next.delete(userId);
            return next;
          });
        }
      },
      ac.signal,
    ).catch((err) => {
      if (!ac.signal.aborted) console.error("[ChatSSE] connection failed:", err);
    });

    return () => {
      window.removeEventListener("pagehide", handlePageHide);
      ac.abort();
      refreshChatList(); // refresh sidebar on leave
    };
  }, [chat, chatId, scrollToBottom, refreshChatList]);

  // Send message
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || !myUserId || sending) return;

    setInput("");
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
        body: JSON.stringify({ content: text }),
      });
      if (!res.ok) {
        console.error("[ChatSend] failed:", res.status);
        // Remove optimistic message on failure
        setMessages(prev => prev.filter(m => m.id !== optimisticMsg.id));
      } else {
        const real: ChatMessage = await res.json();
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
  }, [input, myUserId, sending, chatId, scrollToBottom, refreshChatList]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const decideJoinRequest = useCallback(async (requestId: string, decision: "approve" | "reject") => {
    setJoinRequestBusyId(requestId);
    setJoinRequestError(null);
    try {
      const res = await authFetch(
        `/api/chats/${chatId}/join-requests/${encodeURIComponent(requestId)}/${decision}`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `Join request ${decision} failed (${res.status})`);
      }
      const updated: ChatJoinRequest = await res.json();
      setJoinRequests(prev => prev.map(request => request.id === updated.id ? updated : request));
      const chatRes = await authFetch(`/api/chats/${chatId}`);
      if (!chatRes.ok) {
        const body = await chatRes.text();
        throw new Error(body || `Chat reload failed (${chatRes.status})`);
      }
      setChat(await chatRes.json());
      refreshChatList();
    } catch (err) {
      setJoinRequestError(err instanceof Error ? err.message : "Join request action failed");
    } finally {
      setJoinRequestBusyId(null);
    }
  }, [chatId, refreshChatList]);

  const submitJoinRequest = useCallback(async () => {
    if (!joinTarget || joinSubmitting || joinTarget.current_request?.state === "pending") return;
    setJoinSubmitting(true);
    setJoinSubmitError(null);
    try {
      const message = joinMessage.trim();
      const res = await authFetch(`/api/chats/${chatId}/join-requests`, {
        method: "POST",
        body: JSON.stringify({ message: message || null }),
      });
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `Join request failed (${res.status})`);
      }
      const current_request: ChatJoinRequest = await res.json();
      setJoinTarget({ ...joinTarget, current_request });
      setJoinMessage("");
    } catch (err) {
      setJoinSubmitError(err instanceof Error ? err.message : "Join request failed");
    } finally {
      setJoinSubmitting(false);
    }
  }, [chatId, joinMessage, joinSubmitting, joinTarget]);

  const copyGroupLink = useCallback(async () => {
    setShareStatus(null);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(`${window.location.origin}/chat/visit/${chatId}`);
      setShareStatus("已复制");
    } catch (err) {
      console.error("[ChatShare] copy failed:", err);
      setShareStatus("复制失败");
    }
  }, [chatId]);

  // Typing indicator display — works for both 1:1 and group
  const typingNames = [...typingUsers]
    .map(id => memberMap.get(id)?.name)
    .filter(Boolean);
  const typingDisplay = typingUsers.size > 0 ? (
    <div className="flex items-center gap-2 px-4 py-1">
      <div className="flex gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "var(--duration-fast)" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "var(--duration-normal)" }} />
      </div>
      <span className="text-xs text-muted-foreground">
        {typingNames.length > 0 ? `${typingNames.join("、")} 正在输入` : "正在输入"}
      </span>
    </div>
  ) : null;

  // Display name for header
  const chatName = chat
    ? chat.title || chat.members.filter(member => member.id !== myUserId).map(member => member.name).join(", ") || "聊天"
    : joinTarget
      ? joinTarget.title || "群聊"
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

  if (joinTarget) {
    const pendingRequest = joinTarget.current_request?.state === "pending" ? joinTarget.current_request : null;
    return (
      <div className="h-full flex flex-col min-h-0">
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
            <span className="text-2xs px-1.5 py-0.5 rounded-md font-medium border border-border text-muted-foreground bg-muted">
              等待入群
            </span>
          </div>
        </header>
        <div className="flex-1 overflow-y-auto bg-background px-5 py-8">
          <div className="mx-auto max-w-md rounded-lg border border-border bg-card p-4">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-muted text-muted-foreground">
                <UserPlus className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold text-foreground">申请加入群聊</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  群主批准后，你就能读取新消息并参与对话。
                </p>
              </div>
            </div>
            {pendingRequest ? (
              <div className="mt-4 rounded-md border border-border bg-muted/40 px-3 py-2">
                <p className="text-xs font-medium text-foreground">申请已发送</p>
                {pendingRequest.message && (
                  <p className="mt-1 text-xs text-muted-foreground">{pendingRequest.message}</p>
                )}
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                <textarea
                  value={joinMessage}
                  onChange={e => setJoinMessage(e.target.value)}
                  placeholder="写一句申请理由..."
                  rows={3}
                  className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground/10"
                />
                {joinSubmitError && (
                  <p className="text-xs text-destructive">{joinSubmitError}</p>
                )}
                <button
                  type="button"
                  onClick={() => void submitJoinRequest()}
                  disabled={joinSubmitting}
                  className="inline-flex h-9 items-center gap-2 rounded-lg bg-foreground px-3 text-sm font-medium text-background hover:bg-foreground/90 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Send className="h-4 w-4" />
                  {joinSubmitting ? "发送中..." : "发送申请"}
                </button>
              </div>
            )}
          </div>
        </div>
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
          {chat && (
            <span className="text-2xs px-1.5 py-0.5 rounded-md font-medium border border-border text-muted-foreground bg-muted">
              {chat.members.length} 位成员
            </span>
          )}
        </div>
        {chat?.type === "group" && (
          <div className="flex shrink-0 items-center gap-2">
            {shareStatus && (
              <span className="text-2xs text-muted-foreground">{shareStatus}</span>
            )}
            <button
              type="button"
              aria-label="复制群链接"
              onClick={() => void copyGroupLink()}
              className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-2 text-2xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <Clipboard className="h-3.5 w-3.5" />
              复制群链接
            </button>
          </div>
        )}
      </header>

      {isGroupOwner && (pendingJoinRequests.length > 0 || joinRequestError) && (
        <section className="shrink-0 border-b border-border bg-muted/20 px-4 py-2.5">
          <div className="max-w-3xl mx-auto space-y-2">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-xs font-semibold text-foreground">入群申请</h2>
                <p className="text-2xs text-muted-foreground">
                  {pendingJoinRequests.length} 个待处理申请
                </p>
              </div>
            </div>
            {joinRequestError && (
              <p className="text-2xs text-destructive">{joinRequestError}</p>
            )}
            {pendingJoinRequests.map(request => {
              const requesterLabel = request.requester_name || request.requester_user_id;
              return (
                <div
                  key={request.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-foreground">{requesterLabel}</p>
                    {request.message && (
                      <p className="mt-0.5 truncate text-2xs text-muted-foreground">{request.message}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <button
                      type="button"
                      aria-label={`同意 ${requesterLabel} 入群`}
                      disabled={joinRequestBusyId === request.id}
                      onClick={() => void decideJoinRequest(request.id, "approve")}
                      className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-2xs font-medium text-foreground hover:bg-muted disabled:opacity-50"
                    >
                      <Check className="h-3.5 w-3.5" />
                      同意
                    </button>
                    <button
                      type="button"
                      aria-label={`拒绝 ${requesterLabel} 入群`}
                      disabled={joinRequestBusyId === request.id}
                      onClick={() => void decideJoinRequest(request.id, "reject")}
                      className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-2xs font-medium text-muted-foreground hover:bg-muted disabled:opacity-50"
                    >
                      <X className="h-3.5 w-3.5" />
                      拒绝
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

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
                    <UserBubble content={msg.content} timestamp={ts} userName={myName} avatarUrl={memberMap.get(myUserId!)?.avatar_url} />
                  ) : (
                    <ChatBubble
                      content={msg.content}
                      senderName={chatMemberDisplayName(member, msg.sender_name)}
                      avatarUrl={member?.avatar_url}
                      actorType={member?.type}
                      timestamp={ts}
                      showName
                    />
                  )}
                </div>
              );
            })}
          </div>
        )}
        {typingDisplay}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-border shrink-0">
        <div className="max-w-3xl mx-auto flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息..."
            rows={1}
            className="flex-1 resize-none px-3.5 py-2.5 rounded-xl border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-foreground/10 max-h-32"
            style={{ minHeight: "38px" }}
          />
          <button
            onClick={() => void handleSend()}
            disabled={!input.trim() || sending}
            className="w-9 h-9 rounded-xl bg-foreground text-white flex items-center justify-center hover:bg-foreground/80 disabled:opacity-30 transition-colors duration-fast shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
