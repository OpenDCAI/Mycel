import { useCallback, useEffect, useRef, useState } from "react";
import { supabase, type ChatMessagePayload } from "@/lib/supabase";
import { authFetch } from "@/store/auth-store";

export interface RealtimeMessage {
  id: string;
  chat_id: string;
  sender_id: string;
  sender_name: string;
  content: string;
  message_type: string;
  mentioned_ids: string[];
  signal: string | null;
  retracted_at: string | null;
  created_at: string;
}

interface UseRealtimeMessagesOptions {
  chatId: string;
  enabled?: boolean;
}

export function useRealtimeMessages({ chatId, enabled = true }: UseRealtimeMessagesOptions) {
  const [messages, setMessages] = useState<RealtimeMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const channelRef = useRef<ReturnType<NonNullable<typeof supabase>["channel"]> | null>(null);

  // Initial load via REST API
  const loadMessages = useCallback(async () => {
    if (!chatId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`/api/chats/${chatId}/messages?limit=100`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data: RealtimeMessage[] = await res.json();
      setMessages(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load messages");
    } finally {
      setLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    if (!enabled) return;
    void loadMessages();
  }, [enabled, loadMessages]);

  // Supabase Realtime subscription for incremental updates
  useEffect(() => {
    if (!enabled || !supabase || !chatId) return;

    const channel = supabase
      .channel(`messages:${chatId}`)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "messages",
          filter: `chat_id=eq.${chatId}`,
        },
        (payload) => {
          const row = payload.new as ChatMessagePayload;
          const msg: RealtimeMessage = {
            id: row.id,
            chat_id: row.chat_id,
            sender_id: row.sender_id,
            sender_name: "", // will be enriched by caller
            content: row.content,
            message_type: row.message_type,
            mentioned_ids: row.mentions || [],
            signal: row.signal,
            retracted_at: row.retracted_at,
            created_at: row.created_at,
          };
          setMessages((prev) => {
            // Dedup by id
            if (prev.some((m) => m.id === msg.id)) return prev;
            return [...prev, msg];
          });
        },
      )
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "messages",
          filter: `chat_id=eq.${chatId}`,
        },
        (payload) => {
          const row = payload.new as ChatMessagePayload;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === row.id
                ? { ...m, content: row.content, retracted_at: row.retracted_at }
                : m,
            ),
          );
        },
      )
      .subscribe();

    channelRef.current = channel;

    return () => {
      void supabase!.removeChannel(channel);
      channelRef.current = null;
    };
  }, [enabled, chatId]);

  const sendMessage = useCallback(
    async (content: string, senderId: string, options?: { signal?: string; messageType?: string }) => {
      const res = await authFetch(`/api/chats/${chatId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          content,
          sender_id: senderId,
          message_type: options?.messageType ?? "human",
          signal: options?.signal ?? null,
        }),
      });
      if (!res.ok) throw new Error(`Send failed: ${res.status}`);
      return res.json() as Promise<RealtimeMessage>;
    },
    [chatId],
  );

  return { messages, loading, error, sendMessage, refresh: loadMessages };
}
