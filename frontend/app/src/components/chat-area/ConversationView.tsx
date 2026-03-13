/**
 * @@@contact-view - renders conversation_messages (clean "player" view).
 * Fetches from GET /api/conversations/{id}/messages, subscribes to conversation SSE.
 */
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { listMessages, type ConversationMessage, type ConversationMemberDetail } from "../../api/conversations";
import { authFetch, useAuthStore } from "../../store/auth-store";
import { useStickyScroll } from "../../hooks/use-sticky-scroll";
import { ChatSkeleton } from "./ChatSkeleton";
import { formatTime } from "./utils";

interface ConversationViewProps {
  conversationId: string;
  /** True when the brain thread SSE indicates agent is active. */
  isStreaming?: boolean;
  /** Participant info for resolving sender names. */
  memberDetails?: ConversationMemberDetail[];
}

export default function ConversationView({ conversationId, isStreaming, memberDetails }: ConversationViewProps) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const memberId = useAuthStore(s => s.member?.id);
  const containerRef = useStickyScroll<HTMLDivElement>();
  const seenIds = useRef(new Set<string>());

  // @@@member-name-map - resolve sender_id → display name from member_details
  const memberNameMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of memberDetails || []) map.set(m.id, m.name);
    return map;
  }, [memberDetails]);

  // Fallback name for non-self senders
  const fallbackName = useAuthStore(s => s.agent?.name) || "Leon";

  // Fetch initial messages
  useEffect(() => {
    setLoading(true);
    seenIds.current.clear();
    listMessages(conversationId)
      .then(msgs => {
        setMessages(msgs);
        for (const m of msgs) seenIds.current.add(m.id);
      })
      .catch(err => console.error("[ConversationView] fetch failed:", err))
      .finally(() => setLoading(false));
  }, [conversationId]);

  // @@@conv-sse - subscribe to conversation SSE for real-time messages.
  useEffect(() => {
    const url = `/api/conversations/${encodeURIComponent(conversationId)}/events`;
    const controller = new AbortController();

    (async () => {
      try {
        const res = await authFetch(url, { signal: controller.signal });
        if (!res.ok || !res.body) return;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // Split by double-newline (SSE event separator), handling \r\n
          const chunks = buffer.split(/\r?\n\r?\n/);
          buffer = chunks.pop() ?? "";

          for (const chunk of chunks) {
            const dataLines: string[] = [];
            for (const line of chunk.split(/\r?\n/)) {
              if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
            }
            if (dataLines.length === 0) continue;

            try {
              const evt = JSON.parse(dataLines.join(""));
              if (evt.id && evt.content && !seenIds.current.has(evt.id)) {
                seenIds.current.add(evt.id);
                const msg: ConversationMessage = {
                  id: evt.id,
                  conversation_id: conversationId,
                  sender_id: evt.sender_id,
                  content: evt.content,
                  created_at: evt.created_at,
                };
                setMessages(prev => [...prev, msg]);
              }
            } catch { /* skip malformed */ }
          }
        }
      } catch (err: any) {
        if (err?.name !== "AbortError") {
          console.error("[ConversationView] SSE error:", err);
        }
      }
    })();

    return () => controller.abort();
  }, [conversationId]);

  const resolveSenderName = (senderId: string): string => {
    return memberNameMap.get(senderId) || fallbackName;
  };

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto py-5 bg-white">
      {loading ? (
        <ChatSkeleton />
      ) : messages.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <p className="text-sm text-muted-foreground">暂无消息</p>
        </div>
      ) : (
        <div className="max-w-3xl mx-auto px-5 space-y-3">
          {messages.map(msg => (
            <MessageBubble
              key={msg.id}
              message={msg}
              isSelf={msg.sender_id === memberId}
              senderName={msg.sender_id === memberId ? undefined : resolveSenderName(msg.sender_id)}
            />
          ))}
          {/* @@@typing-indicator - shows while brain thread SSE reports agent is active */}
          {isStreaming && <TypingIndicator name={resolveSenderName("")} />}
        </div>
      )}
    </div>
  );
}

function TypingIndicator({ name }: { name: string }) {
  return (
    <div className="flex justify-start animate-fade-in">
      <div className="flex gap-2.5">
        <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-[11px] font-semibold text-primary shrink-0 mt-0.5">
          {name.slice(0, 1).toUpperCase()}
        </div>
        <div>
          <span className="text-[11px] text-muted-foreground ml-0.5 mb-0.5 block">{name}</span>
          <div className="rounded-xl rounded-bl-sm bg-white border border-border px-4 py-2.5">
            <div className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:0ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:150ms]" />
              <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40 animate-bounce [animation-delay:300ms]" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const MessageBubble = memo(function MessageBubble({
  message,
  isSelf,
  senderName,
}: {
  message: ConversationMessage;
  isSelf: boolean;
  senderName?: string;
}) {
  return (
    <div className={`flex ${isSelf ? "justify-end" : "justify-start"} animate-fade-in`}>
      <div className={`max-w-[78%] ${isSelf ? "" : "flex gap-2.5"}`}>
        {!isSelf && (
          <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center text-[11px] font-semibold text-primary shrink-0 mt-0.5">
            {(senderName || "L").slice(0, 1).toUpperCase()}
          </div>
        )}
        <div>
          {!isSelf && senderName && (
            <span className="text-[11px] text-muted-foreground ml-0.5 mb-0.5 block">{senderName}</span>
          )}
          <div className={`rounded-xl px-3.5 py-2 ${
            isSelf
              ? "rounded-br-sm bg-[#f5f5f5] border border-[#e5e5e5]"
              : "rounded-bl-sm bg-white border border-border"
          }`}>
            <p className="text-[13px] whitespace-pre-wrap leading-[1.55] text-[#171717]">
              {message.content}
            </p>
          </div>
          <div className={`text-[10px] mt-1 ${isSelf ? "text-right pr-1" : "pl-1"} text-[#d4d4d4]`}>
            {formatTime(message.created_at)}
          </div>
        </div>
      </div>
    </div>
  );
});
