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
  ThreadPermissionRules,
  PermissionRuleBehavior,
  AskUserAnswer,
  SandboxFileEntry,
  SandboxFileResult,
  SandboxFilesListResult,
  SandboxUploadResult,
} from "./types";

import { authFetch } from "../store/auth-store";
import { asRecord, recordString } from "../lib/records";

async function checkedResponse(url: string, init?: RequestInit): Promise<Response> {
  const response = await authFetch(url, init);
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return response;
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await checkedResponse(url, init);
  return (await response.json()) as T;
}

export async function requestOk(url: string, init?: RequestInit): Promise<void> {
  await checkedResponse(url, init);
}

// --- Thread API ---

export async function listThreads(): Promise<ThreadSummary[]> {
  const payload = asRecord(await request("/api/threads"));
  const threads = payload?.threads;
  if (!Array.isArray(threads)) throw new Error("Malformed thread summaries");
  return threads.map(parseThreadSummary);
}

export interface CreateThreadOptions {
  sandbox: string;
  recipe?: RecipeSnapshot;
  leaseId?: string;
  cwd?: string;
  agentUserId: string;
  model?: string;
  agent?: string;
}

export async function createThread(opts: CreateThreadOptions): Promise<ThreadSummary> {
  const body: Record<string, unknown> = { sandbox: opts.sandbox, agent_user_id: opts.agentUserId };
  if (opts.recipe) body.recipe = opts.recipe;
  if (opts.leaseId) body.lease_id = opts.leaseId;
  if (opts.cwd) body.cwd = opts.cwd;
  if (opts.model) body.model = opts.model;
  if (opts.agent) body.agent = opts.agent;
  return parseThreadSummary(await request("/api/threads", { method: "POST", body: JSON.stringify(body) }));
}

export async function getDefaultThread(agentUserId: string, signal?: AbortSignal): Promise<ThreadSummary | null> {
  // @@@default-thread-wire-main-route - frontend now treats this as a template ->
  // default-thread resolver, but the backend endpoint name stays `/threads/main`
  // until the route contract is renamed in a later slice.
  const payload = await request<{ thread: ThreadSummary | null }>("/api/threads/main", {
    method: "POST",
    body: JSON.stringify({ agent_user_id: agentUserId }),
    signal,
  });
  return payload.thread ? parseThreadSummary(payload.thread) : null;
}

function parseThreadSummary(value: unknown): ThreadSummary {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  if (!payload || !thread_id) throw new Error("Malformed thread summaries");
  return { ...payload, thread_id } as ThreadSummary;
}

export async function getDefaultThreadConfig(agentUserId: string, signal?: AbortSignal): Promise<ThreadLaunchConfigResponse> {
  return parseDefaultThreadConfig(await request(`/api/threads/default-config?agent_user_id=${encodeURIComponent(agentUserId)}`, { signal }));
}

function isDefaultConfigSource(value: unknown): value is ThreadLaunchConfigResponse["source"] {
  return value === "last_successful" || value === "last_confirmed" || value === "derived";
}

function isLaunchCreateMode(value: unknown): value is ThreadLaunchConfig["create_mode"] {
  return value === "new" || value === "existing";
}

function isStringOrNullish(value: unknown): value is string | null | undefined {
  return value === undefined || value === null || typeof value === "string";
}

function parseThreadLaunchConfig(value: unknown): ThreadLaunchConfig | null {
  const payload = asRecord(value);
  const create_mode = payload?.create_mode;
  const provider_config = payload ? recordString(payload, "provider_config") : undefined;
  const recipe = payload?.recipe;
  const lease_id = payload?.lease_id;
  const model = payload?.model;
  const workspace = payload?.workspace;
  if (
    !payload ||
    !isLaunchCreateMode(create_mode) ||
    !provider_config ||
    (recipe !== undefined && recipe !== null && asRecord(recipe) === null) ||
    !isStringOrNullish(lease_id) ||
    !isStringOrNullish(model) ||
    !isStringOrNullish(workspace)
  ) {
    return null;
  }
  return { ...payload, create_mode, provider_config, recipe, lease_id, model, workspace } as ThreadLaunchConfig;
}

function parseDefaultThreadConfig(value: unknown): ThreadLaunchConfigResponse {
  const payload = asRecord(value);
  const source = payload?.source;
  const config = parseThreadLaunchConfig(payload?.config);
  if (!payload || !isDefaultConfigSource(source) || !config) {
    throw new Error("Malformed default thread config");
  }
  return { source, config };
}

export async function saveDefaultThreadConfig(
  agentUserId: string,
  config: ThreadLaunchConfig,
): Promise<void> {
  await requestOk("/api/threads/default-config", {
    method: "POST",
    body: JSON.stringify({ agent_user_id: agentUserId, ...config }),
  });
}

export async function deleteThread(threadId: string): Promise<void> {
  await requestOk(`/api/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
}

export async function getThread(threadId: string): Promise<ThreadDetail> {
  return parseThreadDetail(await request(`/api/threads/${encodeURIComponent(threadId)}`));
}

function parseThreadDetail(value: unknown): ThreadDetail {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const entries = payload?.entries;
  const display_seq = payload?.display_seq;
  const sandbox = payload?.sandbox;
  if (
    !payload ||
    !thread_id ||
    !Array.isArray(entries) ||
    typeof display_seq !== "number" ||
    (sandbox !== null && asRecord(sandbox) === null)
  ) {
    throw new Error("Malformed thread detail");
  }
  return { ...payload, thread_id, entries, display_seq, sandbox } as ThreadDetail;
}

export async function getThreadPermissions(threadId: string, signal?: AbortSignal): Promise<ThreadPermissions> {
  return parseThreadPermissions(await request(`/api/threads/${encodeURIComponent(threadId)}/permissions`, { signal }));
}

function stringArray(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value : null;
}

function parseThreadPermissionRules(value: unknown): ThreadPermissionRules | null {
  const payload = asRecord(value);
  const allow = payload ? stringArray(payload.allow) : null;
  const deny = payload ? stringArray(payload.deny) : null;
  const ask = payload ? stringArray(payload.ask) : null;
  if (!payload || !allow || !deny || !ask) return null;
  return { allow, deny, ask };
}

function parseThreadPermissions(value: unknown): ThreadPermissions {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const requests = payload?.requests;
  const session_rules = parseThreadPermissionRules(payload?.session_rules);
  const managed_only = payload?.managed_only;
  if (!payload || !thread_id || !Array.isArray(requests) || !session_rules || typeof managed_only !== "boolean") {
    throw new Error("Malformed thread permissions");
  }
  return { ...payload, thread_id, requests, session_rules, managed_only } as ThreadPermissions;
}

export async function resolveThreadPermission(
  threadId: string,
  requestId: string,
  decision: "allow" | "deny",
  message?: string,
  answers?: AskUserAnswer[],
  annotations?: Record<string, unknown>,
): Promise<{ ok: boolean; thread_id: string; request_id: string }> {
  return parsePermissionMutation(await request(
    `/api/threads/${encodeURIComponent(threadId)}/permissions/${encodeURIComponent(requestId)}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ decision, message, answers, annotations }),
    },
  ));
}

function parsePermissionMutation(value: unknown): { ok: boolean; thread_id: string; request_id: string } {
  const payload = asRecord(value);
  const ok = payload?.ok;
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const request_id = payload ? recordString(payload, "request_id") : undefined;
  if (!payload || typeof ok !== "boolean" || !thread_id || !request_id) {
    throw new Error("Malformed permission mutation");
  }
  return { ok, thread_id, request_id };
}

export async function addThreadPermissionRule(
  threadId: string,
  behavior: PermissionRuleBehavior,
  toolName: string,
): Promise<{ ok: boolean; thread_id: string; scope: string; rules: ThreadPermissionRules; managed_only: boolean }> {
  return parsePermissionRulesMutation(await request(`/api/threads/${encodeURIComponent(threadId)}/permissions/rules`, {
    method: "POST",
    body: JSON.stringify({ behavior, tool_name: toolName }),
  }));
}

export async function removeThreadPermissionRule(
  threadId: string,
  behavior: PermissionRuleBehavior,
  toolName: string,
): Promise<{ ok: boolean; thread_id: string; scope: string; rules: ThreadPermissionRules; managed_only: boolean }> {
  return parsePermissionRulesMutation(await request(
    `/api/threads/${encodeURIComponent(threadId)}/permissions/rules/${encodeURIComponent(behavior)}/${encodeURIComponent(toolName)}`,
    { method: "DELETE" },
  ));
}

function parsePermissionRulesMutation(
  value: unknown,
): { ok: boolean; thread_id: string; scope: string; rules: ThreadPermissionRules; managed_only: boolean } {
  const payload = asRecord(value);
  const ok = payload?.ok;
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const scope = payload ? recordString(payload, "scope") : undefined;
  const rules = parseThreadPermissionRules(payload?.rules);
  const managed_only = payload?.managed_only;
  if (!payload || typeof ok !== "boolean" || !thread_id || !scope || !rules || typeof managed_only !== "boolean") {
    throw new Error("Malformed permission rules mutation");
  }
  return { ok, thread_id, scope, rules, managed_only };
}

export async function getThreadRuntime(threadId: string): Promise<StreamStatus> {
  return parseRuntimeStatus(await request(`/api/threads/${encodeURIComponent(threadId)}/runtime`));
}

function booleanMap(value: unknown): Record<string, boolean> | null {
  const payload = asRecord(value);
  if (!payload) return null;
  return Object.values(payload).every((item) => typeof item === "boolean") ? payload as Record<string, boolean> : null;
}

function parseRuntimeStatus(value: unknown): StreamStatus {
  const payload = asRecord(value);
  const state = asRecord(payload?.state);
  const tokens = asRecord(payload?.tokens);
  const context = asRecord(payload?.context);
  const stateValue = state ? recordString(state, "state") : undefined;
  const flags = booleanMap(state?.flags);
  const last_seq = payload?.last_seq;
  const run_start_seq = payload?.run_start_seq;
  if (
    !payload ||
    !stateValue ||
    !flags ||
    !tokens ||
    typeof tokens.total_tokens !== "number" ||
    typeof tokens.input_tokens !== "number" ||
    typeof tokens.output_tokens !== "number" ||
    typeof tokens.cost !== "number" ||
    !context ||
    typeof context.message_count !== "number" ||
    typeof context.estimated_tokens !== "number" ||
    typeof context.usage_percent !== "number" ||
    typeof context.near_limit !== "boolean" ||
    (payload.model !== undefined && typeof payload.model !== "string") ||
    (payload.current_tool !== undefined && typeof payload.current_tool !== "string") ||
    (last_seq !== undefined && typeof last_seq !== "number") ||
    (run_start_seq !== undefined && typeof run_start_seq !== "number")
  ) {
    throw new Error("Malformed runtime status");
  }
  return {
    ...payload,
    state: { ...state, state: stateValue, flags },
    tokens: {
      total_tokens: tokens.total_tokens,
      input_tokens: tokens.input_tokens,
      output_tokens: tokens.output_tokens,
      cost: tokens.cost,
    },
    context: {
      message_count: context.message_count,
      estimated_tokens: context.estimated_tokens,
      usage_percent: context.usage_percent,
      near_limit: context.near_limit,
    },
  } as StreamStatus;
}

export async function sendMessage(threadId: string, message: string): Promise<{ status: string; routing: string }> {
  return parseSendMessageResult(await request(`/api/threads/${encodeURIComponent(threadId)}/messages`, {
    method: "POST",
    body: JSON.stringify({ message }),
  }));
}

function parseSendMessageResult(value: unknown): { status: string; routing: string; thread_id: string; run_id?: string } {
  const payload = asRecord(value);
  const status = payload ? recordString(payload, "status") : undefined;
  const routing = payload ? recordString(payload, "routing") : undefined;
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const run_id = payload?.run_id;
  if (!payload || !status || !routing || !thread_id || (run_id !== undefined && typeof run_id !== "string")) {
    throw new Error("Malformed send message result");
  }
  return run_id === undefined ? { status, routing, thread_id } : { status, routing, thread_id, run_id };
}

// --- Sandbox API ---

export async function listSandboxTypes(): Promise<SandboxType[]> {
  return parseSandboxTypes(await request("/api/sandbox/types"));
}

function parseSandboxTypes(value: unknown): SandboxType[] {
  const payload = asRecord(value);
  const types = payload?.types;
  if (!Array.isArray(types)) throw new Error("Malformed sandbox types");
  return types.map((type) => {
    const data = asRecord(type);
    const name = data ? recordString(data, "name") : undefined;
    const available = data?.available;
    if (!data || !name || typeof available !== "boolean") {
      throw new Error("Malformed sandbox types");
    }
    return { ...data, name, available } as SandboxType;
  });
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
  const sessions = parseSandboxSessions(await request("/api/sandbox/sessions"));
  const toTs = (value?: string): number => {
    if (!value) return 0;
    const ts = Date.parse(value);
    return Number.isFinite(ts) ? ts : 0;
  };
  return [...sessions].sort((a, b) => {
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

function parseSandboxSessions(value: unknown): SandboxSession[] {
  const payload = asRecord(value);
  const sessions = payload?.sessions;
  if (!Array.isArray(sessions)) throw new Error("Malformed sandbox sessions");
  return sessions.map((session) => {
    const data = asRecord(session);
    const session_id = data ? recordString(data, "session_id") : undefined;
    const thread_id = data ? recordString(data, "thread_id") : undefined;
    const provider = data ? recordString(data, "provider") : undefined;
    const status = data ? recordString(data, "status") : undefined;
    if (!data || !session_id || !thread_id || !provider || !status) {
      throw new Error("Malformed sandbox sessions");
    }
    return { ...data, session_id, thread_id, provider, status } as SandboxSession;
  });
}

export async function listMyLeases(signal?: AbortSignal): Promise<UserLeaseSummary[]> {
  return parseUserLeases(await request("/api/sandbox/leases/mine", { signal }));
}

function parseUserLeases(value: unknown): UserLeaseSummary[] {
  const payload = asRecord(value);
  const leases = payload?.leases;
  if (!Array.isArray(leases)) throw new Error("Malformed user leases");
  return leases.map((lease) => {
    const data = asRecord(lease);
    const lease_id = data ? recordString(data, "lease_id") : undefined;
    const provider_name = data ? recordString(data, "provider_name") : undefined;
    const recipe_id = data ? recordString(data, "recipe_id") : undefined;
    const recipe_name = data ? recordString(data, "recipe_name") : undefined;
    const thread_ids = data?.thread_ids;
    const agents = data?.agents;
    if (
      !data ||
      !lease_id ||
      !provider_name ||
      !recipe_id ||
      !recipe_name ||
      !Array.isArray(thread_ids) ||
      !thread_ids.every((id) => typeof id === "string") ||
      !Array.isArray(agents)
    ) {
      throw new Error("Malformed user leases");
    }
    const admittedAgents = agents.map((agent) => {
      const agentData = asRecord(agent);
      const thread_id = agentData ? recordString(agentData, "thread_id") : undefined;
      const agent_name = agentData ? recordString(agentData, "agent_name") : undefined;
      if (!agentData || !thread_id || !agent_name) throw new Error("Malformed user leases");
      return { ...agentData, thread_id, agent_name };
    });
    return { ...data, lease_id, provider_name, recipe_id, recipe_name, thread_ids, agents: admittedAgents } as UserLeaseSummary;
  });
}

export async function destroySandboxSession(sessionId: string, provider: string): Promise<void> {
  await requestOk(
    `/api/sandbox/sessions/${encodeURIComponent(sessionId)}?provider=${encodeURIComponent(provider)}`,
    { method: "DELETE" },
  );
}

// --- Session/Terminal/Lease API ---

export async function getThreadSession(threadId: string): Promise<SessionStatus> {
  return parseSessionStatus(await request(`/api/threads/${encodeURIComponent(threadId)}/session`));
}

function parseSessionStatus(value: unknown): SessionStatus {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const session_id = payload ? recordString(payload, "session_id") : undefined;
  const terminal_id = payload ? recordString(payload, "terminal_id") : undefined;
  const status = payload ? recordString(payload, "status") : undefined;
  const started_at = payload ? recordString(payload, "started_at") : undefined;
  const last_active_at = payload ? recordString(payload, "last_active_at") : undefined;
  const expires_at = payload ? recordString(payload, "expires_at") : undefined;
  if (!payload || !thread_id || !session_id || !terminal_id || !status || !started_at || !last_active_at || !expires_at) {
    throw new Error("Malformed session status");
  }
  return { ...payload, thread_id, session_id, terminal_id, status, started_at, last_active_at, expires_at } as SessionStatus;
}

export async function getThreadTerminal(threadId: string): Promise<TerminalStatus> {
  return parseTerminalStatus(await request(`/api/threads/${encodeURIComponent(threadId)}/terminal`));
}

function stringMap(value: unknown): Record<string, string> | null {
  const payload = asRecord(value);
  if (!payload) return null;
  return Object.values(payload).every((item) => typeof item === "string") ? payload as Record<string, string> : null;
}

function parseTerminalStatus(value: unknown): TerminalStatus {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const terminal_id = payload ? recordString(payload, "terminal_id") : undefined;
  const lease_id = payload ? recordString(payload, "lease_id") : undefined;
  const cwd = payload ? recordString(payload, "cwd") : undefined;
  const env_delta = stringMap(payload?.env_delta);
  const version = payload?.version;
  const created_at = payload ? recordString(payload, "created_at") : undefined;
  const updated_at = payload ? recordString(payload, "updated_at") : undefined;
  if (!payload || !thread_id || !terminal_id || !lease_id || !cwd || !env_delta || typeof version !== "number" || !created_at || !updated_at) {
    throw new Error("Malformed terminal status");
  }
  return { ...payload, thread_id, terminal_id, lease_id, cwd, env_delta, version, created_at, updated_at } as TerminalStatus;
}

export async function getThreadLease(threadId: string): Promise<LeaseStatus | null> {
  const response = await authFetch(`/api/threads/${encodeURIComponent(threadId)}/lease`);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return parseLeaseStatus(await response.json());
}

function parseLeaseStatus(value: unknown): LeaseStatus {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const lease_id = payload ? recordString(payload, "lease_id") : undefined;
  const provider_name = payload ? recordString(payload, "provider_name") : undefined;
  const created_at = payload ? recordString(payload, "created_at") : undefined;
  const updated_at = payload ? recordString(payload, "updated_at") : undefined;
  if (!payload || !thread_id || !lease_id || !provider_name || !created_at || !updated_at) {
    throw new Error("Malformed lease status");
  }
  return { ...payload, thread_id, lease_id, provider_name, created_at, updated_at } as LeaseStatus;
}

// --- Sandbox Files API ---

function sandboxFilesBase(threadId: string): string {
  return `/api/threads/${encodeURIComponent(threadId)}/files`;
}

export async function listSandboxFiles(threadId: string, path?: string): Promise<SandboxFilesListResult> {
  const q = path ? `?path=${encodeURIComponent(path)}` : "";
  return parseSandboxFilesList(await request(`${sandboxFilesBase(threadId)}/list${q}`));
}

function parseSandboxFilesList(value: unknown): SandboxFilesListResult {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const path = payload ? recordString(payload, "path") : undefined;
  const entries = payload?.entries;
  if (!payload || !thread_id || !path || !Array.isArray(entries)) {
    throw new Error("Malformed sandbox file list");
  }
  return { thread_id, path, entries: entries.map(parseSandboxFileEntry) };
}

function parseSandboxFileEntry(value: unknown): SandboxFileEntry {
  const payload = asRecord(value);
  const name = payload ? recordString(payload, "name") : undefined;
  const is_dir = payload?.is_dir;
  const size = payload?.size;
  const children_count = payload?.children_count;
  if (
    !payload ||
    !name ||
    typeof is_dir !== "boolean" ||
    typeof size !== "number" ||
    (children_count !== undefined && children_count !== null && typeof children_count !== "number")
  ) {
    throw new Error("Malformed sandbox file list");
  }
  return children_count === undefined ? { name, is_dir, size } : { name, is_dir, size, children_count };
}

export async function readSandboxFile(threadId: string, path: string): Promise<SandboxFileResult> {
  return parseSandboxFileRead(await request(`${sandboxFilesBase(threadId)}/read?path=${encodeURIComponent(path)}`));
}

function parseSandboxFileRead(value: unknown): SandboxFileResult {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const path = payload ? recordString(payload, "path") : undefined;
  const content = payload ? recordString(payload, "content") : undefined;
  const size = payload?.size;
  if (!payload || !thread_id || !path || content === undefined || typeof size !== "number") {
    throw new Error("Malformed sandbox file read");
  }
  return { thread_id, path, content, size };
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
  return parseSandboxUploadResult(await response.json());
}

function parseSandboxUploadResult(value: unknown): SandboxUploadResult {
  const payload = asRecord(value);
  const thread_id = payload ? recordString(payload, "thread_id") : undefined;
  const relative_path = payload ? recordString(payload, "relative_path") : undefined;
  const absolute_path = payload ? recordString(payload, "absolute_path") : undefined;
  const size_bytes = payload?.size_bytes;
  const sha256 = payload ? recordString(payload, "sha256") : undefined;
  if (!payload || !thread_id || !relative_path || !absolute_path || typeof size_bytes !== "number" || !sha256) {
    throw new Error("Malformed sandbox upload result");
  }
  return { thread_id, relative_path, absolute_path, size_bytes, sha256 };
}

export function getSandboxDownloadUrl(
  threadId: string,
  path: string,
): string {
  const query = new URLSearchParams({ path });
  return `${sandboxFilesBase(threadId)}/download?${query.toString()}`;
}

// --- Settings API ---

export async function saveSandboxConfig(name: string, config: Record<string, unknown>): Promise<void> {
  await requestOk("/api/settings/sandboxes", {
    method: "POST",
    body: JSON.stringify({ name, config }),
  });
}

// --- Observation API ---

export async function saveObservationConfig(
  active: string | null,
  config?: Record<string, unknown>,
): Promise<void> {
  await requestOk("/api/settings/observation", {
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

// --- Invite Code API ---

export interface InviteCode {
  code: string;
  used: boolean;
  used_by?: string | null;
  expires_at?: string | null;
  created_at: string;
}

export async function fetchInviteCodes(): Promise<InviteCode[]> {
  const payload = await request<{ codes: InviteCode[] }>("/api/invite-codes");
  return payload.codes;
}

export async function generateInviteCode(expiresDays = 7): Promise<InviteCode> {
  return request<InviteCode>("/api/invite-codes", {
    method: "POST",
    body: JSON.stringify({ expires_days: expiresDays }),
  });
}

export async function revokeInviteCode(code: string): Promise<void> {
  await requestOk(`/api/invite-codes/${encodeURIComponent(code)}`, { method: "DELETE" });
}

// --- User Avatar API ---

export async function uploadUserAvatar(userId: string, file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const response = await authFetch(`/api/users/${userId}/avatar`, {
    method: "PUT",
    body: form,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
}
