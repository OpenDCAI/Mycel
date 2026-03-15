import type {
  SandboxSession,
  SandboxType,
  SessionStatus,
  StreamStatus,
  TerminalStatus,
  LeaseStatus,
  ThreadSummary,
  WorkspaceFileResult,
  WorkspaceListResult,
} from "./types";
import { useAuthStore } from "../store/auth-store";

// @@@auth-header - attach JWT if available so thread/sandbox APIs work with auth-protected endpoints
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };
  const token = useAuthStore.getState().token;
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(url, { ...init, headers });
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

export async function createThread(sandbox: string, cwd?: string, agent?: string): Promise<ThreadSummary> {
  const body: Record<string, string> = { sandbox };
  if (cwd) body.cwd = cwd;
  if (agent) body.agent = agent;
  return request<ThreadSummary>("/api/threads", { method: "POST", body: JSON.stringify(body) });
}

export async function deleteThread(threadId: string): Promise<void> {
  await request(`/api/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
}

export async function getThread(threadId: string): Promise<{ thread_id: string; messages: unknown[]; sandbox: unknown }> {
  return request(`/api/threads/${encodeURIComponent(threadId)}`);
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

// --- Workspace API ---

export async function listWorkspace(threadId: string, path?: string): Promise<WorkspaceListResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  return request(`/api/threads/${encodeURIComponent(threadId)}/workspace/list${q}`);
}

export async function readWorkspaceFile(threadId: string, path: string): Promise<WorkspaceFileResult> {
  return request(`/api/threads/${encodeURIComponent(threadId)}/workspace/read?path=${encodeURIComponent(path)}`);
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
