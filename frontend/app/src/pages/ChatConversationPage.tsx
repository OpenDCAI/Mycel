import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Send } from "lucide-react";
import { authFetch, useAuthStore } from "../store/auth-store";

interface ChatEntity {
  id: string;
  name: string;
  type: string;
  avatar?: string | null;
}

interface ChatMessage {
  id: string;
  chat_id: string;
  sender_entity_id: string;
  sender_name: string;
  content: string;
  mentioned_entity_ids: string[];
  created_at: number;
}

interface ChatDetail {
  id: string;
  title: string | null;
  status: string;
  created_at: number;
  entities: ChatEntity[];
}

// @@@time-gap — only show timestamp when gap >= 5 minutes
function shouldShowTime(prev: ChatMessage | null, curr: ChatMessage): boolean {
  if (!prev) return true;
  return (curr.created_at - prev.created_at) >= 300;
}

function formatMessageTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function ChatConversationPage() {
  const { chatId } = useParams<{ chatId: string }>();
  if (!chatId) return null;
  return <ChatConversationInner key={chatId} chatId={chatId} />;
}

function ChatConversationInner({ chatId }: { chatId: string }) {
  const myEntityId = useAuthStore(s => s.entityId);
  const [chat, setChat] = useState<ChatDetail | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

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
        setMessages(msgsData);
        setLoading(false);
        // Mark read
        authFetch(`/api/chats/${chatId}/read`, { method: "POST" }).catch(() => {});
      })
      .catch(err => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [chatId]);

  // Scroll to bottom on initial load
  useEffect(() => {
    if (!loading && messages.length > 0) {
      setTimeout(() => messagesEndRef.current?.scrollIntoView(), 50);
    }
  }, [loading]);

  // SSE for real-time messages
  useEffect(() => {
    const token = useAuthStore.getState().token;
    if (!token) return;

    const es = new EventSource(`/api/chats/${chatId}/events?token=${encodeURIComponent(token)}`);

    // @@@sse-dedup — SSE message dedup: skip if real id exists, replace optimistic if content matches
    es.addEventListener("message", (e) => {
      try {
        const msg: ChatMessage = JSON.parse(e.data);
        setMessages(prev => {
          // Skip if we already have this exact message id
          if (prev.some(m => m.id === msg.id)) return prev;
          // Replace optimistic message if sender+content matches
          const optimisticIdx = prev.findIndex(
            m => m.id.startsWith("optimistic-") && m.sender_entity_id === msg.sender_entity_id && m.content === msg.content,
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
        }
      } catch (err) {
        console.error("[ChatSSE] parse error:", err);
      }
    });

    es.addEventListener("typing_start", (e) => {
      try {
        const data = JSON.parse(e.data);
        setTypingEntities(prev => new Set([...prev, data.entity_id]));
      } catch {}
    });

    es.addEventListener("typing_stop", (e) => {
      try {
        const data = JSON.parse(e.data);
        setTypingEntities(prev => {
          const next = new Set(prev);
          next.delete(data.entity_id);
          return next;
        });
      } catch {}
    });

    es.onerror = () => {
      console.warn("[ChatSSE] connection error, will auto-reconnect");
    };

    return () => es.close();
  }, [chatId, scrollToBottom]);

  // Typing indicator state
  const [typingEntities, setTypingEntities] = useState<Set<string>>(new Set());

  const isGroup = (chat?.entities.length ?? 0) >= 3;

  // Send message
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || !myEntityId || sending) return;

    setInput("");
    setSending(true);

    // Optimistic insert
    const optimisticMsg: ChatMessage = {
      id: `optimistic-${Date.now()}`,
      chat_id: chatId,
      sender_entity_id: myEntityId,
      sender_name: useAuthStore.getState().member?.name || "me",
      content: text,
      mentioned_entity_ids: [],
      created_at: Date.now() / 1000,
    };
    setMessages(prev => [...prev, optimisticMsg]);
    setTimeout(scrollToBottom, 50);

    try {
      const res = await authFetch(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content: text,
          sender_entity_id: myEntityId,
        }),
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
    }
  }, [input, myEntityId, sending, chatId, scrollToBottom]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  // Typing indicator display — only 1:1
  const typingDisplay = !isGroup && typingEntities.size > 0 ? (
    <div className="flex items-center gap-2 px-4 py-1">
      <div className="flex gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
      <span className="text-xs text-muted-foreground">typing</span>
    </div>
  ) : null;

  // Display name for header
  const chatName = chat
    ? chat.title || chat.entities.filter(e => e.id !== myEntityId).map(e => e.name).join(", ") || "Chat"
    : "Chat";

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2">
        <p className="text-sm text-destructive">{error}</p>
        <Link to="/chats" className="text-xs text-primary hover:underline">Back to chats</Link>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center gap-3 shrink-0">
        <Link to="/chats" className="text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-foreground truncate">{chatName}</h2>
          {chat && (
            <p className="text-[11px] text-muted-foreground">
              {chat.entities.length} member{chat.entities.length !== 1 ? "s" : ""}
            </p>
          )}
        </div>
      </div>

      {/* Messages */}
      <div
        ref={scrollContainerRef}
        onScroll={onScroll}
        className="flex-1 overflow-y-auto px-4 py-3"
      >
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-sm text-muted-foreground">Send a message to start the conversation</p>
          </div>
        ) : (
          messages.map((msg, i) => {
            const isMine = msg.sender_entity_id === myEntityId;
            const prev = i > 0 ? messages[i - 1] : null;
            const showTime = shouldShowTime(prev, msg);

            return (
              <div key={msg.id}>
                {showTime && (
                  <div className="text-center my-3">
                    <span className="text-[10px] text-muted-foreground/50 bg-muted/50 px-2 py-0.5 rounded-full">
                      {formatMessageTime(msg.created_at)}
                    </span>
                  </div>
                )}
                <div className={`flex mb-1 ${isMine ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[70%] ${isMine ? "order-1" : ""}`}>
                    {/* Show sender name in group chats for non-self messages */}
                    {!isMine && isGroup && (
                      <p className="text-[10px] text-muted-foreground mb-0.5 px-1">{msg.sender_name}</p>
                    )}
                    <div
                      className={`px-3 py-2 rounded-2xl text-sm break-words whitespace-pre-wrap ${
                        isMine
                          ? "bg-primary text-primary-foreground rounded-br-md"
                          : "bg-muted text-foreground rounded-bl-md"
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
        {typingDisplay}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-border shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            className="flex-1 resize-none px-3 py-2 rounded-lg border border-border bg-card text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 max-h-32"
            style={{ minHeight: "38px" }}
          />
          <button
            onClick={() => void handleSend()}
            disabled={!input.trim() || sending}
            className="w-9 h-9 rounded-lg bg-primary text-primary-foreground flex items-center justify-center hover:opacity-90 disabled:opacity-40 transition-opacity shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
