import { create } from "zustand";
import { useAuthStore } from "./auth-store";

const HUB_URL = import.meta.env.VITE_MYCEL_HUB_URL || "http://localhost:8090";
const API = "/api/marketplace";

export interface MarketplaceItemSummary {
  id: string;
  slug: string;
  type: string;
  name: string;
  description: string | null;
  avatar_url: string | null;
  publisher_user_id: string;
  publisher_username: string;
  parent_id: string | null;
  download_count: number;
  visibility: string;
  featured: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface VersionInfo {
  id: string;
  version: string;
  release_notes: string | null;
  created_at: string;
}

export interface MarketplaceItemDetail extends MarketplaceItemSummary {
  versions: VersionInfo[];
  parent: MarketplaceItemSummary | null;
}

export interface LineageNode {
  id: string;
  name: string;
  publisher_username: string;
  parent_id: string | null;
}

export interface UpdateAvailable {
  marketplace_item_id: string;
  installed_version: string;
  latest_version: string;
  release_notes: string;
}

interface MarketplaceFilters {
  type: string | null;
  q: string;
  sort: string;
  page: number;
}

interface MarketplaceState {
  // Explore
  items: MarketplaceItemSummary[];
  total: number;
  loading: boolean;
  filters: MarketplaceFilters;
  setFilter: (key: keyof MarketplaceFilters, value: any) => void;
  fetchItems: () => Promise<void>;

  // Detail
  detail: MarketplaceItemDetail | null;
  detailLoading: boolean;
  fetchDetail: (id: string) => Promise<void>;
  clearDetail: () => void;

  // Lineage
  lineage: { ancestors: LineageNode[]; children: LineageNode[] };
  fetchLineage: (id: string) => Promise<void>;

  // Updates
  updates: UpdateAvailable[];
  checkUpdates: (installed: { marketplace_item_id: string; installed_version: string }[]) => Promise<void>;

  // Actions (go through Mycel backend)
  downloading: boolean;
  download: (itemId: string) => Promise<{ resource_id: string; type: string; version: string }>;
  upgrade: (memberId: string, itemId: string) => Promise<void>;
  publishToMarketplace: (memberId: string, type: string, bumpType: string, releaseNotes: string, tags: string[], visibility: string) => Promise<any>;
}

async function hubApi<T = any>(path: string): Promise<T> {
  const res = await fetch(`${HUB_URL}/api/v1${path}`);
  if (!res.ok) throw new Error(`Hub API error: ${res.status}`);
  return res.json();
}

async function backendApi<T = any>(path: string, opts?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { headers, ...opts });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const useMarketplaceStore = create<MarketplaceState>()((set, get) => ({
  items: [],
  total: 0,
  loading: false,
  filters: { type: null, q: "", sort: "downloads", page: 1 },

  setFilter: (key, value) => {
    set((s) => ({ filters: { ...s.filters, [key]: value, ...(key !== "page" ? { page: 1 } : {}) } }));
  },

  fetchItems: async () => {
    set({ loading: true });
    try {
      const { type, q, sort, page } = get().filters;
      const params = new URLSearchParams();
      if (type) params.set("type", type);
      if (q) params.set("q", q);
      params.set("sort", sort);
      params.set("page", String(page));
      params.set("page_size", "20");
      const data = await hubApi<{ items: MarketplaceItemSummary[]; total: number }>(`/items?${params}`);
      set({ items: data.items, total: data.total });
    } catch (e) {
      console.error("Failed to fetch marketplace items:", e);
    } finally {
      set({ loading: false });
    }
  },

  detail: null,
  detailLoading: false,

  fetchDetail: async (id) => {
    set({ detailLoading: true, detail: null });
    try {
      const data = await hubApi<MarketplaceItemDetail>(`/items/${id}`);
      set({ detail: data });
    } catch (e) {
      console.error("Failed to fetch detail:", e);
    } finally {
      set({ detailLoading: false });
    }
  },

  clearDetail: () => set({ detail: null }),

  lineage: { ancestors: [], children: [] },

  fetchLineage: async (id) => {
    try {
      const data = await hubApi<{ ancestors: LineageNode[]; children: LineageNode[] }>(`/items/${id}/lineage`);
      set({ lineage: data });
    } catch (e) {
      console.error("Failed to fetch lineage:", e);
    }
  },

  updates: [],

  checkUpdates: async (installed) => {
    try {
      const data = await backendApi<{ updates: UpdateAvailable[] }>("/check-updates", {
        method: "POST",
        body: JSON.stringify({ items: installed }),
      });
      set({ updates: data.updates || [] });
    } catch (e) {
      console.error("Failed to check updates:", e);
    }
  },

  downloading: false,

  download: async (itemId) => {
    set({ downloading: true });
    try {
      const data = await backendApi<{ resource_id: string; type: string; version: string }>("/download", {
        method: "POST",
        body: JSON.stringify({ item_id: itemId }),
      });
      return data;
    } finally {
      set({ downloading: false });
    }
  },

  upgrade: async (memberId, itemId) => {
    const data = await backendApi("/upgrade", {
      method: "POST",
      body: JSON.stringify({ member_id: memberId, item_id: itemId }),
    });
    return data;
  },

  publishToMarketplace: async (memberId, type, bumpType, releaseNotes, tags, visibility) => {
    return backendApi("/publish", {
      method: "POST",
      body: JSON.stringify({
        member_id: memberId,
        type,
        bump_type: bumpType,
        release_notes: releaseNotes,
        tags,
        visibility,
      }),
    });
  },
}));
