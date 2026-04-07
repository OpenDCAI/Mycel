import { create } from "zustand";
import { authFetch } from "./auth-store";

export interface ChatSummary {
  id: string;
  title: string | null;
  entities: Array<{ id: string; name: string; type: string; avatar_url: string }>;
  last_message: { content: string; sender_name: string; created_at: string } | null;
  unread_count: number;
  pinned: boolean;
  muted: boolean;
  status: string;
  created_at: string | number;
}

interface ChatStore {
  chats: ChatSummary[];
  loading: boolean;
  totalUnread: number;
  fetchChats(): Promise<void>;
  openOrCreateDM(myUserId: string, otherUserId: string): Promise<string>;
  createGroupChat(userIds: string[], title: string): Promise<string>;
  markRead(chatId: string): Promise<void>;
  toggleMute(chatId: string, userId: string, muted: boolean): Promise<void>;
  togglePin(chatId: string, pinned: boolean): Promise<void>;
  renameChat(chatId: string, title: string | null): Promise<void>;
  deleteChat(chatId: string): Promise<void>;
  leaveChat(chatId: string): Promise<void>;
}

export const useChatStore = create<ChatStore>((set, get) => ({
  chats: [],
  loading: false,
  totalUnread: 0,

  fetchChats: async () => {
    set({ loading: true });
    try {
      const res = await authFetch("/api/chats");
      if (!res.ok) throw new Error(`${res.status}`);
      const data: ChatSummary[] = await res.json();
      const totalUnread = data
        .filter(c => !c.muted)
        .reduce((sum, c) => sum + (c.unread_count ?? 0), 0);
      set({ chats: data, totalUnread });
    } catch (err) {
      console.error("[ChatStore] fetchChats failed:", err);
    } finally {
      set({ loading: false });
    }
  },

  openOrCreateDM: async (myUserId: string, otherUserId: string) => {
    const res = await authFetch("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_ids: [myUserId, otherUserId] }),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const data = await res.json();
    await get().fetchChats();
    return data.id as string;
  },

  createGroupChat: async (userIds: string[], title: string) => {
    const res = await authFetch("/api/chats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_ids: userIds, title }),
    });
    if (!res.ok) throw new Error(`${res.status}`);
    const data = await res.json();
    await get().fetchChats();
    return data.id as string;
  },

  markRead: async (chatId: string) => {
    const res = await authFetch(`/api/chats/${chatId}/read`, { method: "POST" });
    if (!res.ok) return;
    set(s => ({
      chats: s.chats.map(c => c.id === chatId ? { ...c, unread_count: 0 } : c),
      totalUnread: Math.max(0, s.totalUnread - (s.chats.find(c => c.id === chatId)?.unread_count ?? 0)),
    }));
  },

  toggleMute: async (chatId: string, userId: string, muted: boolean) => {
    await authFetch(`/api/chats/${chatId}/mute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, muted }),
    });
    set(s => ({
      chats: s.chats.map(c => c.id === chatId ? { ...c, muted } : c),
    }));
  },

  togglePin: async (chatId: string, pinned: boolean) => {
    await authFetch(`/api/chats/${chatId}/pin`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pinned }),
    });
    set(s => ({
      chats: s.chats.map(c => c.id === chatId ? { ...c, pinned } : c),
    }));
  },

  renameChat: async (chatId: string, title: string | null) => {
    await authFetch(`/api/chats/${chatId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    set(s => ({
      chats: s.chats.map(c => c.id === chatId ? { ...c, title } : c),
    }));
  },

  deleteChat: async (chatId: string) => {
    await authFetch(`/api/chats/${chatId}`, { method: "DELETE" });
    set(s => ({
      chats: s.chats.filter(c => c.id !== chatId),
    }));
  },

  leaveChat: async (chatId: string) => {
    await authFetch(`/api/chats/${chatId}/leave`, { method: "POST" });
    set(s => ({
      chats: s.chats.filter(c => c.id !== chatId),
    }));
  },
}));
