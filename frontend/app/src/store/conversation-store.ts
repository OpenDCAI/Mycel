import { create } from "zustand";
import type { ConversationItem } from "@/types/conversation";
import { authFetch } from "./auth-store";

interface ConversationState {
  conversations: ConversationItem[];
  loading: boolean;
  fetchConversations: () => Promise<void>;
}

let inflight: Promise<void> | null = null;

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  loading: false,

  fetchConversations: async () => {
    if (inflight) return;
    set({ loading: true });
    const pending = (async () => {
      try {
        const res = await authFetch("/api/conversations");
        if (!res.ok) throw new Error(`${res.status}`);
        const data: ConversationItem[] = await res.json();
        // Skip no-op update to avoid unnecessary re-renders
        const prev = get().conversations;
        if (prev.length !== data.length || JSON.stringify(prev) !== JSON.stringify(data)) {
          set({ conversations: data });
        }
      } catch (err) {
        console.error("[ConversationStore] fetch failed:", err);
      } finally {
        inflight = null;
        set({ loading: false });
      }
    })();
    inflight = pending;
    await pending;
  },
}));
