import type { BrowseItem, ProviderOrphanSessionsResponse, ResourceOverviewResponse } from "./types";

function ensureProviderCardContract(payload: ResourceOverviewResponse): ResourceOverviewResponse {
  if (!payload || !payload.summary || !Array.isArray(payload.providers)) {
    throw new Error("Unexpected /api/monitor/resources response shape");
  }
  return payload;
}

function ensureProviderOrphanContract(payload: ProviderOrphanSessionsResponse): ProviderOrphanSessionsResponse {
  if (!payload || !Array.isArray(payload.sessions)) {
    throw new Error("Unexpected /api/monitor/provider-sessions response shape");
  }
  return payload;
}

async function readJsonOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }
  return (await response.json()) as T;
}

export async function fetchJsonOrThrow<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  return readJsonOrThrow<T>(await fetch(input, init));
}

export async function fetchMonitorResources(): Promise<ResourceOverviewResponse> {
  const payload = await fetchJsonOrThrow<ResourceOverviewResponse>("/api/monitor/resources", {
    headers: { "Content-Type": "application/json" },
  });
  return ensureProviderCardContract(payload);
}

export async function refreshMonitorResources(): Promise<ResourceOverviewResponse> {
  const payload = await fetchJsonOrThrow<ResourceOverviewResponse>("/api/monitor/resources/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return ensureProviderCardContract(payload);
}

export async function fetchMonitorProviderSessions(): Promise<ProviderOrphanSessionsResponse> {
  const payload = await fetchJsonOrThrow<ProviderOrphanSessionsResponse>("/api/monitor/provider-sessions", {
    headers: { "Content-Type": "application/json" },
  });
  return ensureProviderOrphanContract(payload);
}

export async function cleanupMonitorProviderSession(
  providerId: string,
  sessionId: string,
): Promise<{
  accepted: boolean;
  message?: string | null;
  operation?: {
    operation_id?: string | null;
    status?: string | null;
    summary?: string | null;
  } | null;
}> {
  return fetchJsonOrThrow(`/api/monitor/provider-sessions/${encodeURIComponent(providerId)}/${encodeURIComponent(sessionId)}/cleanup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

export async function browseMonitorSandbox(leaseId: string, path: string): Promise<{
  current_path: string;
  parent_path: string | null;
  items: BrowseItem[];
}> {
  return fetchJsonOrThrow(`/api/monitor/sandbox/${leaseId}/browse?path=${encodeURIComponent(path)}`);
}

export async function readMonitorSandboxFile(
  leaseId: string,
  path: string,
): Promise<{ path: string; content: string; truncated: boolean }> {
  return fetchJsonOrThrow(`/api/monitor/sandbox/${leaseId}/read?path=${encodeURIComponent(path)}`);
}
