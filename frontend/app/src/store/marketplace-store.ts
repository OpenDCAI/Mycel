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

interface VersionInfo {
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

interface MarketplaceVersionSnapshot {
  content?: string;
  meta?: Record<string, unknown>;
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
  error: string | null;
  filters: MarketplaceFilters;
  setFilter: <K extends keyof MarketplaceFilters>(key: K, value: MarketplaceFilters[K]) => void;
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

  // Preview
  versionSnapshot: MarketplaceVersionSnapshot | null;
  snapshotLoading: boolean;
  fetchVersionSnapshot: (itemId: string, version: string) => Promise<void>;
  clearSnapshot: () => void;

  // Actions (go through Mycel backend)
  downloading: boolean;
  download: (itemId: string) => Promise<{ resource_id: string; type: string; version: string }>;
  upgrade: (userId: string, itemId: string) => Promise<void>;
  publishAgentUserToMarketplace: (userId: string, bumpType: string, releaseNotes: string, tags: string[], visibility: string) => Promise<unknown>;
}

function isActiveMarketplaceRoute(): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path === "/marketplace" || path.startsWith("/marketplace/");
}

function isActiveMarketplaceDetailRoute(itemId: string): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path === `/marketplace/${encodeURIComponent(itemId)}`;
}

async function hubApi<T = unknown>(path: string): Promise<T> {
  try {
    const res = await fetch(`${HUB_URL}/api/v1${path}`);
    if (!res.ok) {
      if (res.status >= 502) {
        throw new Error("Marketplace Hub unavailable");
      }
      throw new Error(`Hub API error: ${res.status}`);
    }
    return res.json();
  } catch (e) {
    if (e instanceof TypeError) {
      throw new Error("Marketplace Hub unavailable");
    }
    throw e;
  }
}

async function backendApi<T = unknown>(path: string, opts?: RequestInit): Promise<T> {
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
  error: null,
  filters: { type: null, q: "", sort: "downloads", page: 1 },

  setFilter: (key, value) => {
    set((s) => ({ filters: { ...s.filters, [key]: value, ...(key !== "page" ? { page: 1 } : {}) } }));
  },

  fetchItems: async () => {
    set({ error: null, loading: true });
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
      // @@@marketplace-route-teardown - explore fetches can resolve after the
      // user already left /marketplace. Only log if the marketplace route is
      // still active; otherwise this is stale UI noise.
      if (!isActiveMarketplaceRoute()) return;
      console.error("Failed to fetch marketplace items:", e);
      set({ error: e instanceof Error ? e.message : "Unknown error" });
    } finally {
      set({ loading: false });
    }
  },

  detail: null,
  detailLoading: false,

  fetchDetail: async (id) => {
    set({ error: null, detailLoading: true, detail: null });
    try {
      const data = await hubApi<MarketplaceItemDetail>(`/items/${id}`);
      set({ detail: data });
    } catch (e) {
      // @@@marketplace-detail-route-teardown - detail fetches can resolve after
      // the user already left this marketplace detail page. Only log if this
      // item route is still active; otherwise this is stale UI noise.
      if (!isActiveMarketplaceDetailRoute(id)) return;
      console.error("Failed to fetch detail:", e);
      set({ error: e instanceof Error ? e.message : "Unknown error" });
    } finally {
      set({ detailLoading: false });
    }
  },

  clearDetail: () => set({ detail: null }),

  versionSnapshot: null,
  snapshotLoading: false,

  fetchVersionSnapshot: async (itemId, version) => {
    set({ snapshotLoading: true, versionSnapshot: null });
    try {
      const data = await hubApi<{ snapshot: MarketplaceVersionSnapshot | null }>(`/items/${itemId}/versions/${version}`);
      set({ versionSnapshot: data.snapshot ?? null });
    } catch (e) {
      // @@@marketplace-snapshot-route-teardown - snapshot fetches can resolve
      // after the user already left this marketplace detail page. Only log if
      // this item route is still active; otherwise this is stale UI noise.
      if (!isActiveMarketplaceDetailRoute(itemId)) return;
      console.error("Failed to fetch snapshot:", e);
    } finally {
      set({ snapshotLoading: false });
    }
  },

  clearSnapshot: () => set({ versionSnapshot: null }),

  lineage: { ancestors: [], children: [] },

  fetchLineage: async (id) => {
    set({ error: null });
    try {
      const data = await hubApi<{ ancestors: LineageNode[]; children: LineageNode[] }>(`/items/${id}/lineage`);
      set({ lineage: data });
    } catch (e) {
      // @@@marketplace-lineage-route-teardown - lineage fetches can resolve
      // after the user already left this marketplace detail page. Only log if
      // this item route is still active; otherwise this is stale UI noise.
      if (!isActiveMarketplaceDetailRoute(id)) return;
      console.error("Failed to fetch lineage:", e);
      set({ error: e instanceof Error ? e.message : "Unknown error" });
    }
  },

  updates: [],

  checkUpdates: async (installed) => {
    set({ error: null });
    try {
      const data = await backendApi<{ updates: UpdateAvailable[] }>("/check-updates", {
        method: "POST",
        body: JSON.stringify({ items: installed }),
      });
      set({ updates: data.updates || [] });
    } catch (e) {
      // @@@marketplace-updates-route-teardown - installed update checks can
      // resolve after the user already left /marketplace. Only log if the
      // marketplace route is still active; otherwise this is stale UI noise.
      if (!isActiveMarketplaceRoute()) return;
      console.error("Failed to check updates:", e);
      set({ error: e instanceof Error ? e.message : "Unknown error" });
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

  upgrade: async (userId, itemId) => {
    await backendApi("/upgrade", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, item_id: itemId }),
    });
  },

  publishAgentUserToMarketplace: async (userId, bumpType, releaseNotes, tags, visibility) => {
    return backendApi("/publish-agent-user", {
      method: "POST",
      body: JSON.stringify({
        user_id: userId,
        bump_type: bumpType,
        release_notes: releaseNotes,
        tags,
        visibility,
      }),
    });
  },
}));
