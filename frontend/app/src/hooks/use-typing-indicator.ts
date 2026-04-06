import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

interface UseTypingIndicatorOptions {
  chatId: string;
  userId: string | null;
  enabled?: boolean;
}

export function useTypingIndicator({ chatId, userId, enabled = true }: UseTypingIndicatorOptions) {
  const [typingUsers, setTypingUsers] = useState<Set<string>>(new Set());
  const channelRef = useRef<ReturnType<NonNullable<typeof supabase>["channel"]> | null>(null);
  const typingTimeoutsRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    if (!enabled || !supabase || !chatId) return;

    const channel = supabase.channel(`typing:${chatId}`);

    channel
      .on("broadcast", { event: "typing" }, (payload) => {
        const uid = payload.payload?.user_id as string | undefined;
        if (!uid || uid === userId) return;

        setTypingUsers((prev) => {
          const next = new Set(prev);
          next.add(uid);
          return next;
        });

        // Clear after 3s timeout
        const existing = typingTimeoutsRef.current.get(uid);
        if (existing) clearTimeout(existing);
        typingTimeoutsRef.current.set(
          uid,
          setTimeout(() => {
            setTypingUsers((prev) => {
              const next = new Set(prev);
              next.delete(uid);
              return next;
            });
            typingTimeoutsRef.current.delete(uid);
          }, 3000),
        );
      })
      .subscribe();

    channelRef.current = channel;

    return () => {
      void supabase!.removeChannel(channel);
      channelRef.current = null;
      // Clear all timeouts
      for (const t of typingTimeoutsRef.current.values()) clearTimeout(t);
      typingTimeoutsRef.current.clear();
    };
  }, [enabled, chatId, userId]);

  const sendTyping = useCallback(() => {
    if (!channelRef.current || !userId) return;
    void channelRef.current.send({
      type: "broadcast",
      event: "typing",
      payload: { user_id: userId },
    });
  }, [userId]);

  return { typingUsers, sendTyping };
}
