import type {
  SandboxSession,
  SandboxType,
  UserLeaseSummary,
  RecipeSnapshot,
  ThreadLaunchConfig,
  ThreadLaunchConfigResponse,
  SessionStatus,
  StreamStatus,
  TerminalStatus,
  LeaseStatus,
  ThreadDetail,
  ThreadSummary,
  ThreadPermissions,
  SandboxChannelFilesResult,
  SandboxFileResult,
  SandboxFilesListResult,
  SandboxUploadResult,
} from "./types";

import { authFetch } from "../store/auth-store";

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await authFetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function toThreads(payload: unknown): ThreadSummary[] {
  if (payload && typeof payload === "object" && Array.isArray((payload as { threads?: unknown }).threads)) {
    return (payload as { threads: ThreadSummary[] }).threads;
  }
  if (Array.isArray(payload)) {
    return payload as ThreadSummary[];
  }
  throw new Error("Unexpected /api/threads response shape");
}

// --- Thread API ---

export async function listThreads(): Promise<ThreadSummary[]> {
  const payload = await request<unknown>("/api/threads");
  return toThreads(payload);
}

export interface CreateThreadOptions {
  sandbox: string;
  recipe?: RecipeSnapshot;
  leaseId?: string;
  cwd?: string;
  memberId: string;
  model?: string;
  agent?: string;
}

export async function createThread(opts: CreateThreadOptions): Promise<ThreadSummary> {
  const body: Record<string, unknown> = { sandbox: opts.sandbox, member_id: opts.memberId };
  if (opts.recipe) body.recipe = opts.recipe;
  if (opts.leaseId) body.lease_id = opts.leaseId;
  if (opts.cwd) body.cwd = opts.cwd;
  if (opts.model) body.model = opts.model;
  if (opts.agent) body.agent = opts.agent;
  return request<ThreadSummary>("/api/threads", { method: "POST", body: JSON.stringify(body) });
}

export async function getMainThread(memberId: string, signal?: AbortSignal): Promise<ThreadSummary | null> {
  const payload = await request<{ thread: ThreadSummary | null }>("/api/threads/main", {
    method: "POST",
    body: JSON.stringify({ member_id: memberId }),
    signal,
  });
  return payload.thread ?? null;
}

export async function getDefaultThreadConfig(memberId: string, signal?: AbortSignal): Promise<ThreadLaunchConfigResponse> {
  return request(`/api/threads/default-config?member_id=${encodeURIComponent(memberId)}`, { signal });
}

export async function saveDefaultThreadConfig(
  memberId: string,
  config: ThreadLaunchConfig,
): Promise<void> {
  await request("/api/threads/default-config", {
    method: "POST",
    body: JSON.stringify({ member_id: memberId, ...config }),
  });
}

export async function deleteThread(threadId: string): Promise<void> {
  await request(`/api/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
}

export async function getThread(threadId: string): Promise<ThreadDetail> {
  return request(`/api/threads/${encodeURIComponent(threadId)}`);
}

export async function getThreadPermissions(threadId: string): Promise<ThreadPermissions> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/permissions`);
}

export async function resolveThreadPermission(
  threadId: string,
  requestId: string,
  decision: "allow" | "deny",
  message?: string,
): Promise<{ ok: boolean; thread_id: string; request_id: string }> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/permissions/${encodeURIComponent(requestId)}/resolve`, {
    method: "POST",
    body: JSON.stringify({ decision, message }),
  });
}

export async function getThreadRuntime(threadId: string): Promise<StreamStatus> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/runtime`);
}

export async function sendMessage(threadId: string, message: string): Promise<{ status: string; routing: string }> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function queueMessage(threadId: string, message: string): Promise<void> {
  await request(`/api/threads/${encodeURIComponent(threadId)}/queue`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function getQueue(threadId: string): Promise<{ messages: Array<{ id: number; content: string; created_at: string }> }> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/queue`);
}

// --- Sandbox API ---

export async function listSandboxTypes(): Promise<SandboxType[]> {
  const payload = await request<{ types: SandboxType[] }>("/api/sandbox/types");
  return payload.types;
}

export async function pickFolder(): Promise<string | null> {
  try {
    const payload = await request<{ path: string }>("/api/sandbox/pick-folder");
    return payload.path;
  } catch (err) {
    console.log("Folder selection cancelled or failed:", err);
    return null;
  }
}

export async function listSandboxSessions(): Promise<SandboxSession[]> {
  const payload = await request<{ sessions: SandboxSession[] }>("/api/sandbox/sessions");
  const toTs = (value?: string): number => {
    if (!value) return 0;
    const ts = Date.parse(value);
    return Number.isFinite(ts) ? ts : 0;
  };
  return [...payload.sessions].sort((a, b) => {
    const createdDiff = toTs(b.created_at) - toTs(a.created_at);
    if (createdDiff !== 0) return createdDiff;
    const activeDiff = toTs(b.last_active) - toTs(a.last_active);
    if (activeDiff !== 0) return activeDiff;
    const providerDiff = a.provider.localeCompare(b.provider);
    if (providerDiff !== 0) return providerDiff;
    const threadDiff = a.thread_id.localeCompare(b.thread_id);
    if (threadDiff !== 0) return threadDiff;
    return a.session_id.localeCompare(b.session_id);
  });
}

export async function listMyLeases(signal?: AbortSignal): Promise<UserLeaseSummary[]> {
  const payload = await request<{ leases: UserLeaseSummary[] }>("/api/sandbox/leases/mine", { signal });
  return payload.leases;
}

export async function pauseThreadSandbox(threadId: string): Promise<void> {
  await request(`/api/threads/${encodeURIComponent(threadId)}/sandbox/pause`, { method: "POST" });
}

export async function resumeThreadSandbox(threadId: string): Promise<void> {
  await request(`/api/threads/${encodeURIComponent(threadId)}/sandbox/resume`, { method: "POST" });
}

export async function destroyThreadSandbox(threadId: string): Promise<void> {
  await request(`/api/threads/${encodeURIComponent(threadId)}/sandbox`, { method: "DELETE" });
}

export async function pauseSandboxSession(sessionId: string, provider: string): Promise<void> {
  await request(
    `/api/sandbox/sessions/${encodeURIComponent(sessionId)}/pause?provider=${encodeURIComponent(provider)}`,
    { method: "POST" },
  );
}

export async function resumeSandboxSession(sessionId: string, provider: string): Promise<void> {
  await request(
    `/api/sandbox/sessions/${encodeURIComponent(sessionId)}/resume?provider=${encodeURIComponent(provider)}`,
    { method: "POST" },
  );
}

export async function destroySandboxSession(sessionId: string, provider: string): Promise<void> {
  await request(
    `/api/sandbox/sessions/${encodeURIComponent(sessionId)}?provider=${encodeURIComponent(provider)}`,
    { method: "DELETE" },
  );
}

// --- Session/Terminal/Lease API ---

export async function getThreadSession(threadId: string): Promise<SessionStatus> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/session`);
}

export async function getThreadTerminal(threadId: string): Promise<TerminalStatus> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/terminal`);
}

export async function getThreadLease(threadId: string): Promise<LeaseStatus> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/lease`);
}

// --- Sandbox Files API ---

function sandboxFilesBase(threadId: string): string {
  return `/api/threads/${encodeURIComponent(threadId)}/files`;
}

export async function listSandboxFiles(threadId: string, path?: string): Promise<SandboxFilesListResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  return request(`${sandboxFilesBase(threadId)}/list${q}`);
}

export async function readSandboxFile(threadId: string, path: string): Promise<SandboxFileResult> {
  return request(`${sandboxFilesBase(threadId)}/read?path=${encodeURIComponent(path)}`);
}

export async function listSandboxChannelFiles(
  threadId: string,
): Promise<SandboxChannelFilesResult> {
  return request(`${sandboxFilesBase(threadId)}/channel-files`);
}

export async function uploadSandboxFile(
  threadId: string,
  opts: { file: File; path?: string },
): Promise<SandboxUploadResult> {
  const query = new URLSearchParams();
  if (opts.path) query.set("path", opts.path);
  const form = new FormData();
  form.set("file", opts.file, opts.file.name);

  const response = await authFetch(`${sandboxFilesBase(threadId)}/upload?${query.toString()}`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return (await response.json()) as SandboxUploadResult;
}

export function getSandboxDownloadUrl(
  threadId: string,
  path: string,
): string {
  const query = new URLSearchParams({ path });
  return `${sandboxFilesBase(threadId)}/download?${query.toString()}`;
}

// --- Settings API ---

export async function listSandboxConfigs(): Promise<Record<string, Record<string, unknown>>> {
  const payload = await request<{ sandboxes: Record<string, Record<string, unknown>> }>("/api/settings/sandboxes");
  return payload.sandboxes;
}

export async function saveSandboxConfig(name: string, config: Record<string, unknown>): Promise<void> {
  await request("/api/settings/sandboxes", {
    method: "POST",
    body: JSON.stringify({ name, config }),
  });
}

// --- Observation API ---

export async function getObservationConfig(): Promise<Record<string, unknown>> {
  return request("/api/settings/observation");
}

export async function saveObservationConfig(
  active: string | null,
  config?: Record<string, unknown>,
): Promise<void> {
  await request("/api/settings/observation", {
    method: "POST",
    body: JSON.stringify({ active, ...config }),
  });
}

export async function verifyObservation(): Promise<{
  success: boolean;
  provider?: string;
  traces?: unknown[];
  error?: string;
}> {
  return request("/api/settings/observation/verify");
}

// --- Member API ---

export async function uploadMemberAvatar(memberId: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const response = await authFetch(`/api/members/${memberId}/avatar`, {
    method: "PUT",
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
}
