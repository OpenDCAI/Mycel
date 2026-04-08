import { create } from "zustand";
import type {
  Agent, Task, ResourceItem, UserProfile,
  AgentConfig, TaskStatus, CronJob,
} from "./types";
import { useAuthStore } from "./auth-store";

const API = "/api/panel";
let loadAllInflight: Promise<void> | null = null;

interface AppState {
  // ── Data ──
  agentList: Agent[];
  taskList: Task[];
  cronJobs: CronJob[];
  librarySkills: ResourceItem[];
  libraryMcps: ResourceItem[];
  libraryAgents: ResourceItem[];
  libraryRecipes: ResourceItem[];
  userProfile: UserProfile;
  loaded: boolean;
  error: string | null;

  // ── Init ──
  loadAll: () => Promise<void>;
  retry: () => Promise<void>;
  resetSessionData: () => void;

  // ── Agents ──
  fetchAgents: () => Promise<void>;
  addAgent: (name: string, description?: string) => Promise<Agent>;
  updateAgent: (id: string, fields: Partial<Agent>) => Promise<void>;
  updateAgentConfig: (id: string, patch: Partial<AgentConfig>) => Promise<void>;
  publishAgent: (id: string, bumpType: string) => Promise<Agent>;
  deleteAgent: (id: string) => Promise<void>;
  getAgentById: (id: string) => Agent | undefined;

  // ── Tasks ──
  fetchTasks: () => Promise<void>;
  addTask: (fields?: Partial<Task>) => Promise<Task>;
  updateTask: (id: string, fields: Partial<Task>) => Promise<void>;
  deleteTask: (id: string) => Promise<void>;
  bulkUpdateTaskStatus: (ids: string[], status: TaskStatus) => Promise<void>;
  bulkDeleteTasks: (ids: string[]) => Promise<void>;

  // ── Cron Jobs ──
  fetchCronJobs: () => Promise<void>;
  addCronJob: (fields?: Partial<CronJob>) => Promise<CronJob>;
  updateCronJob: (id: string, fields: Partial<CronJob>) => Promise<void>;
  deleteCronJob: (id: string) => Promise<void>;
  triggerCronJob: (id: string) => Promise<void>;

  // ── Library ──
  fetchLibrary: (type: string) => Promise<void>;
  fetchLibraryNames: (type: string) => Promise<{ name: string; desc: string }[]>;
  addResource: (
    type: string,
    name: string,
    desc?: string,
    extra?: { provider_type?: string; features?: Record<string, boolean> },
  ) => Promise<ResourceItem>;
  updateResource: (type: string, id: string, fields: Partial<ResourceItem>) => Promise<void>;
  deleteResource: (type: string, id: string) => Promise<void>;
  fetchResourceContent: (type: string, id: string) => Promise<string>;
  updateResourceContent: (type: string, id: string, content: string) => Promise<void>;

  // ── Profile ──
  fetchProfile: () => Promise<void>;
  updateProfile: (fields: Partial<UserProfile>) => Promise<void>;

  // ── Helpers ──
  getAgentNames: () => { id: string; name: string }[];
  getResourceUsedBy: (type: string, name: string) => string[];
}

type LibraryType = "skill" | "mcp" | "agent" | "recipe";
type LibraryStateKey = "librarySkills" | "libraryMcps" | "libraryAgents" | "libraryRecipes";

const DEFAULT_PROFILE: UserProfile = { name: "User", initials: "U", email: "" };
const LIBRARY_STATE_KEYS: Record<LibraryType, LibraryStateKey> = {
  skill: "librarySkills",
  mcp: "libraryMcps",
  agent: "libraryAgents",
  recipe: "libraryRecipes",
};

function getLibraryStateKey(type: string): LibraryStateKey {
  const key = LIBRARY_STATE_KEYS[type as LibraryType];
  if (!key) throw new Error(`Unsupported library type: ${type}`);
  return key;
}

function emptySessionState() {
  return {
    agentList: [],
    taskList: [],
    cronJobs: [],
    librarySkills: [],
    libraryMcps: [],
    libraryAgents: [],
    libraryRecipes: [],
    userProfile: DEFAULT_PROFILE,
    loaded: false,
    error: null,
  };
}

async function api<T = unknown>(path: string, opts?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { headers, ...opts });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const useAppStore = create<AppState>()((set, get) => ({
  ...emptySessionState(),

  loadAll: async () => {
    if (get().loaded) return;
    if (loadAllInflight) return loadAllInflight;

    const pending = (async () => {
      set({ error: null });
      try {
        // @@@load-all-singleflight - RootLayout can mount twice in dev StrictMode and /threads
        // index redirect now avoids AppLayout, so keep the global panel bootstrap idempotent
        // instead of firing duplicate agents/tasks/library/profile bursts.
        await Promise.all([
          get().fetchAgents(),
          get().fetchTasks(),
          get().fetchCronJobs(),
          get().fetchLibrary("skill"),
          get().fetchLibrary("mcp"),
          get().fetchLibrary("agent"),
          get().fetchLibrary("recipe"),
          get().fetchProfile(),
        ]);
        set({ loaded: true });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        set({ error: `数据加载失败: ${msg}`, loaded: true });
      }
    })();

    loadAllInflight = pending;
    try {
      await pending;
    } finally {
      if (loadAllInflight === pending) {
        loadAllInflight = null;
      }
    }
  },

  retry: async () => {
    set({ loaded: false, error: null });
    await get().loadAll();
  },

  resetSessionData: () => {
    loadAllInflight = null;
    set(emptySessionState());
  },

  // ── Agents ──
  fetchAgents: async () => {
    const data = await api<{ items: Agent[] }>("/agents");
    set({ agentList: data.items });
  },

  addAgent: async (name, description = "") => {
    const agent = await api<Agent>("/agents", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    });
    set((s) => ({ agentList: [agent, ...s.agentList] }));
    return agent;
  },

  updateAgent: async (id, fields) => {
    const updated = await api<Agent>(`/agents/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    set((s) => ({ agentList: s.agentList.map((x) => (x.id === id ? updated : x)) }));
  },

  updateAgentConfig: async (id, patch) => {
    const updated = await api<Agent>(`/agents/${id}/config`, {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    set((s) => ({ agentList: s.agentList.map((x) => (x.id === id ? updated : x)) }));
  },

  publishAgent: async (id, bumpType) => {
    const updated = await api<Agent>(`/agents/${id}/publish`, {
      method: "PUT",
      body: JSON.stringify({ bump_type: bumpType }),
    });
    set((s) => ({ agentList: s.agentList.map((x) => (x.id === id ? updated : x)) }));
    return updated;
  },

  deleteAgent: async (id) => {
    await api(`/agents/${id}`, { method: "DELETE" });
    set((s) => ({ agentList: s.agentList.filter((x) => x.id !== id) }));
  },

  getAgentById: (id) => get().agentList.find((x) => x.id === id),

  // ── Tasks ──
  fetchTasks: async () => {
    const data = await api<{ items: Task[] }>("/tasks");
    set({ taskList: data.items });
  },

  addTask: async (fields = {}) => {
    const task = await api<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(fields),
    });
    set((s) => ({ taskList: [task, ...s.taskList] }));
    return task;
  },

  updateTask: async (id, fields) => {
    const updated = await api<Task>(`/tasks/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    set((s) => ({ taskList: s.taskList.map((x) => (x.id === id ? updated : x)) }));
  },

  deleteTask: async (id) => {
    await api(`/tasks/${id}`, { method: "DELETE" });
    set((s) => ({ taskList: s.taskList.filter((x) => x.id !== id) }));
  },

  bulkUpdateTaskStatus: async (ids, status) => {
    await api("/tasks/bulk-status", {
      method: "PUT",
      body: JSON.stringify({ ids, status }),
    });
    set((s) => ({
      taskList: s.taskList.map((t) =>
        ids.includes(t.id)
          ? { ...t, status, progress: status === "completed" ? 100 : status === "pending" ? 0 : t.progress }
          : t
      ),
    }));
  },

  bulkDeleteTasks: async (ids) => {
    await api("/tasks/bulk-delete", {
      method: "POST",
      body: JSON.stringify({ ids }),
    });
    set((s) => ({
      taskList: s.taskList.filter((t) => !ids.includes(t.id)),
    }));
  },

  // ── Cron Jobs ──
  fetchCronJobs: async () => {
    const data = await api<{ items: CronJob[] }>("/cron-jobs");
    set({ cronJobs: data.items });
  },

  addCronJob: async (fields = {}) => {
    const data = await api<{ item: CronJob }>("/cron-jobs", {
      method: "POST",
      body: JSON.stringify(fields),
    });
    const item = data.item;
    set((s) => ({ cronJobs: [item, ...s.cronJobs] }));
    return item;
  },

  updateCronJob: async (id, fields) => {
    const data = await api<{ item: CronJob }>(`/cron-jobs/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    const updated = data.item;
    set((s) => ({ cronJobs: s.cronJobs.map((x) => (x.id === id ? updated : x)) }));
  },

  deleteCronJob: async (id) => {
    await api(`/cron-jobs/${id}`, { method: "DELETE" });
    set((s) => ({ cronJobs: s.cronJobs.filter((x) => x.id !== id) }));
  },

  triggerCronJob: async (id) => {
    await api(`/cron-jobs/${id}/run`, { method: "POST" });
  },

  // ── Library ──
  fetchLibrary: async (type) => {
    const data = await api<{ items: ResourceItem[] }>(`/library/${type}`);
    const key = getLibraryStateKey(type);
    set({ [key]: data.items } as Pick<AppState, typeof key>);
  },

  fetchLibraryNames: async (type) => {
    const data = await api<{ items: { name: string; desc: string }[] }>(`/library/${type}/names`);
    return data.items;
  },

  addResource: async (type, name, desc = "", extra = {}) => {
    const item = await api<ResourceItem>(`/library/${type}`, {
      method: "POST",
      body: JSON.stringify({ name, desc, ...extra }),
    });
    const key = getLibraryStateKey(type);
    set((s) => ({ [key]: [...s[key], item] }) as Pick<AppState, typeof key>);
    return item;
  },

  updateResource: async (type, id, fields) => {
    const updated = await api<ResourceItem>(`/library/${type}/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    const key = getLibraryStateKey(type);
    set((s) => ({
      [key]: s[key].map((item) => (item.id === id ? updated : item)),
    }) as Pick<AppState, typeof key>);
  },

  deleteResource: async (type, id) => {
    await api(`/library/${type}/${id}`, { method: "DELETE" });
    if (type === "recipe") {
      const data = await api<{ items: ResourceItem[] }>(`/library/${type}`);
      set({ libraryRecipes: data.items });
      return;
    }
    const key = getLibraryStateKey(type);
    set((s) => ({
      [key]: s[key].filter((item) => item.id !== id),
    }) as Pick<AppState, typeof key>);
  },

  fetchResourceContent: async (type, id) => {
    const data = await api<{ content: string }>(`/library/${type}/${id}/content`);
    return data.content;
  },

  updateResourceContent: async (type, id, content) => {
    await api(`/library/${type}/${id}/content`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    });
  },

  // ── Profile ──
  fetchProfile: async () => {
    const data = await api<UserProfile & { id?: number }>("/profile");
    set({ userProfile: { name: data.name, initials: data.initials, email: data.email } });
  },

  updateProfile: async (fields) => {
    const data = await api<UserProfile & { id?: number }>("/profile", {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    set({ userProfile: { name: data.name, initials: data.initials, email: data.email } });
  },

  // ── Helpers ──
  getAgentNames: () => get().agentList.map((s) => ({ id: s.id, name: s.name })),

  getResourceUsedBy: (type, name) => {
    if (type === "recipe") return [];
    const key = type === "skill" ? "skills" : type === "mcp" ? "mcps" : "subAgents";
    return get().agentList.filter((s) =>
      (s.config?.[key as keyof typeof s.config] as { name: string }[] | undefined)?.some((i) => i.name === name)
    ).map((s) => s.name);
  },
}));
