import { create } from "zustand";
import type { ConversationItem } from "@/types/conversation";
import { authFetch } from "./auth-store";

interface ConversationState {
  conversations: ConversationItem[];
  loading: boolean;
  activeId: string | null;
  fetchConversations: () => Promise<void>;
  setActive: (id: string | null) => void;
}

export const useConversationStore = create<ConversationState>((set) => ({
  conversations: [],
  loading: false,
  activeId: null,

  fetchConversations: async () => {
    set({ loading: true });
    try {
      const res = await authFetch("/api/conversations");
      if (!res.ok) throw new Error(`${res.status}`);
      const data: ConversationItem[] = await res.json();
      set({ conversations: data });
    } catch (err) {
      console.error("[ConversationStore] fetch failed:", err);
    } finally {
      set({ loading: false });
    }
  },

  setActive: (id) => set({ activeId: id }),
}));
