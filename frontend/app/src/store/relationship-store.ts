import { create } from "zustand";
import { authFetch } from "./auth-store";

export interface RelationshipItem {
  id: string;
  other_user_id: string;
  other_name: string;
  other_mycel_id: number | null;
  other_avatar_url: string | null;
  state: string;
  is_requester: boolean;
  created_at: string;
}

export interface UserSearchResult {
  id: string;
  name: string;
  mycel_id: number | null;
  avatar_url: string | null;
  description: string | null;
}

interface RelationshipStore {
  relationships: RelationshipItem[];
  loading: boolean;
  searchResults: UserSearchResult[];
  searchLoading: boolean;
  fetchRelationships(): Promise<void>;
  sendRequest(targetUserId: string): Promise<void>;
  approve(relationshipId: string): Promise<void>;
  reject(relationshipId: string): Promise<void>;
  remove(relationshipId: string): Promise<void>;
  searchUsers(q: string): Promise<void>;
  clearSearch(): void;
}

export const useRelationshipStore = create<RelationshipStore>((set, get) => ({
  relationships: [],
  loading: false,
  searchResults: [],
  searchLoading: false,

  fetchRelationships: async () => {
    set({ loading: true });
    try {
      const res = await authFetch("/api/relationships");
      if (!res.ok) throw new Error(`${res.status}`);
      const rows: Array<{
        id: string;
        other_user_id: string;
        state: string;
        is_requester: boolean;
        created_at: string;
      }> = await res.json();

      // Enrich each relationship with member info
      const enriched = await Promise.all(
        rows.map(async (row) => {
          try {
            const memberRes = await authFetch(`/api/panel/users/${row.other_user_id}`);
            if (memberRes.ok) {
              const member = await memberRes.json();
              return {
                ...row,
                other_name: member.name ?? "未知用户",
                other_mycel_id: member.mycel_id ?? null,
                other_avatar_url: member.avatar_url ?? null,
              } as RelationshipItem;
            }
          } catch {
            // ignore
          }
          return {
            ...row,
            other_name: "未知用户",
            other_mycel_id: null,
            other_avatar_url: null,
          } as RelationshipItem;
        })
      );
      set({ relationships: enriched });
    } catch (err) {
      console.error("[RelationshipStore] fetch failed:", err);
    } finally {
      set({ loading: false });
    }
  },

  sendRequest: async (targetUserId: string) => {
    await authFetch("/api/relationships/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_user_id: targetUserId }),
    });
    await get().fetchRelationships();
  },

  approve: async (relationshipId: string) => {
    await authFetch(`/api/relationships/${relationshipId}/approve`, { method: "POST" });
    await get().fetchRelationships();
  },

  reject: async (relationshipId: string) => {
    await authFetch(`/api/relationships/${relationshipId}/reject`, { method: "POST" });
    await get().fetchRelationships();
  },

  remove: async (relationshipId: string) => {
    await authFetch(`/api/relationships/${relationshipId}/remove`, { method: "POST" });
    await get().fetchRelationships();
  },

  searchUsers: async (q: string) => {
    if (!q.trim()) { set({ searchResults: [] }); return; }
    set({ searchLoading: true });
    try {
      const res = await authFetch(`/api/panel/users/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      set({ searchResults: data.items as UserSearchResult[] });
    } catch (err) {
      console.error("[RelationshipStore] search failed:", err);
    } finally {
      set({ searchLoading: false });
    }
  },

  clearSearch: () => set({ searchResults: [], searchLoading: false }),
}));
