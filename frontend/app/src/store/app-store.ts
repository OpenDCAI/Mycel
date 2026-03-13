import { create } from "zustand";
import type {
  Member, Task, ResourceItem, UserProfile,
  MemberConfig, TaskStatus, CronJob,
} from "./types";
import { useAuthStore } from "./auth-store";

const API = "/api/panel";

interface AppState {
  // ── Data ──
  memberList: Member[];
  taskList: Task[];
  cronJobs: CronJob[];
  librarySkills: ResourceItem[];
  libraryMcps: ResourceItem[];
  libraryAgents: ResourceItem[];
  userProfile: UserProfile;
  loaded: boolean;
  error: string | null;

  // ── Init ──
  loadAll: () => Promise<void>;
  retry: () => Promise<void>;

  // ── Members ──
  fetchMembers: () => Promise<void>;
  addMember: (name: string, description?: string) => Promise<Member>;
  updateMember: (id: string, fields: Partial<Member>) => Promise<void>;
  updateMemberConfig: (id: string, patch: Partial<MemberConfig>) => Promise<void>;
  publishMember: (id: string, bumpType: string) => Promise<Member>;
  deleteMember: (id: string) => Promise<void>;
  getMemberById: (id: string) => Member | undefined;

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
  addResource: (type: string, name: string, desc?: string) => Promise<ResourceItem>;
  updateResource: (type: string, id: string, fields: Partial<ResourceItem>) => Promise<void>;
  deleteResource: (type: string, id: string) => Promise<void>;
  fetchResourceContent: (type: string, id: string) => Promise<string>;
  updateResourceContent: (type: string, id: string, content: string) => Promise<void>;

  // ── Profile ──
  fetchProfile: () => Promise<void>;
  updateProfile: (fields: Partial<UserProfile>) => Promise<void>;

  // ── Helpers ──
  getMemberNames: () => { id: string; name: string }[];
  getResourceUsedBy: (type: string, name: string) => string[];
}

async function api<T = unknown>(path: string, opts?: RequestInit): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts?.headers as Record<string, string> ?? {}),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API}${path}`, { ...opts, headers });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const useAppStore = create<AppState>()((set, get) => ({
  memberList: [],
  taskList: [],
  cronJobs: [],
  librarySkills: [],
  libraryMcps: [],
  libraryAgents: [],
  userProfile: { name: "User", initials: "U", email: "" },
  loaded: false,
  error: null,

  loadAll: async () => {
    if (get().loaded) return;
    set({ error: null });
    try {
      await Promise.all([
        get().fetchMembers(),
        get().fetchTasks(),
        get().fetchCronJobs(),
        get().fetchLibrary("skill"),
        get().fetchLibrary("mcp"),
        get().fetchLibrary("agent"),
        get().fetchProfile(),
      ]);
      set({ loaded: true });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      set({ error: `数据加载失败: ${msg}`, loaded: true });
    }
  },

  retry: async () => {
    set({ loaded: false, error: null });
    await get().loadAll();
  },

  // ── Members ──
  fetchMembers: async () => {
    const data = await api<{ items: Member[] }>("/members");
    set({ memberList: data.items });
  },

  addMember: async (name, description = "") => {
    const member = await api<Member>("/members", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    });
    set((s) => ({ memberList: [member, ...s.memberList] }));
    return member;
  },

  updateMember: async (id, fields) => {
    const updated = await api<Member>(`/members/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    set((s) => ({ memberList: s.memberList.map((x) => (x.id === id ? updated : x)) }));
  },

  updateMemberConfig: async (id, patch) => {
    const updated = await api<Member>(`/members/${id}/config`, {
      method: "PUT",
      body: JSON.stringify(patch),
    });
    set((s) => ({ memberList: s.memberList.map((x) => (x.id === id ? updated : x)) }));
  },

  publishMember: async (id, bumpType) => {
    const updated = await api<Member>(`/members/${id}/publish`, {
      method: "PUT",
      body: JSON.stringify({ bump_type: bumpType }),
    });
    set((s) => ({ memberList: s.memberList.map((x) => (x.id === id ? updated : x)) }));
    return updated;
  },

  deleteMember: async (id) => {
    await api(`/members/${id}`, { method: "DELETE" });
    set((s) => ({ memberList: s.memberList.filter((x) => x.id !== id) }));
  },

  getMemberById: (id) => get().memberList.find((x) => x.id === id),

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
    if (type === "skill") set({ librarySkills: data.items });
    else if (type === "mcp") set({ libraryMcps: data.items });
    else set({ libraryAgents: data.items });
  },

  fetchLibraryNames: async (type) => {
    const data = await api<{ items: { name: string; desc: string }[] }>(`/library/${type}/names`);
    return data.items;
  },

  addResource: async (type, name, desc = "") => {
    const item = await api<ResourceItem>(`/library/${type}`, {
      method: "POST",
      body: JSON.stringify({ name, desc }),
    });
    if (type === "skill") set((s) => ({ librarySkills: [...s.librarySkills, item] }));
    else if (type === "mcp") set((s) => ({ libraryMcps: [...s.libraryMcps, item] }));
    else set((s) => ({ libraryAgents: [...s.libraryAgents, item] }));
    return item;
  },

  updateResource: async (type, id, fields) => {
    const updated = await api<ResourceItem>(`/library/${type}/${id}`, {
      method: "PUT",
      body: JSON.stringify(fields),
    });
    const updater = (list: ResourceItem[]) => list.map((x) => (x.id === id ? updated : x));
    if (type === "skill") set((s) => ({ librarySkills: updater(s.librarySkills) }));
    else if (type === "mcp") set((s) => ({ libraryMcps: updater(s.libraryMcps) }));
    else set((s) => ({ libraryAgents: updater(s.libraryAgents) }));
  },

  deleteResource: async (type, id) => {
    await api(`/library/${type}/${id}`, { method: "DELETE" });
    const filter = (list: ResourceItem[]) => list.filter((x) => x.id !== id);
    if (type === "skill") set((s) => ({ librarySkills: filter(s.librarySkills) }));
    else if (type === "mcp") set((s) => ({ libraryMcps: filter(s.libraryMcps) }));
    else set((s) => ({ libraryAgents: filter(s.libraryAgents) }));
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
  getMemberNames: () => get().memberList.map((s) => ({ id: s.id, name: s.name })),

  getResourceUsedBy: (type, name) => {
    const key = type === "skill" ? "skills" : type === "mcp" ? "mcps" : "subAgents";
    return get().memberList.filter((s) =>
      (s.config?.[key as keyof typeof s.config] as { name: string }[] | undefined)?.some((i) => i.name === name)
    ).map((s) => s.name);
  },
}));
