import type { BrowseItem, ResourceOverviewResponse } from "./types";

function ensureProviderCardContract(payload: ResourceOverviewResponse): ResourceOverviewResponse {
  if (!payload || !payload.summary || !Array.isArray(payload.providers)) {
    throw new Error("Unexpected /api/monitor/resources response shape");
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

export async function fetchMonitorResources(): Promise<ResourceOverviewResponse> {
  const payload = await readJsonOrThrow<ResourceOverviewResponse>(
    await fetch("/api/monitor/resources", { headers: { "Content-Type": "application/json" } }),
  );
  return ensureProviderCardContract(payload);
}

export async function refreshMonitorResources(): Promise<ResourceOverviewResponse> {
  const payload = await readJsonOrThrow<ResourceOverviewResponse>(
    await fetch("/api/monitor/resources/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    }),
  );
  return ensureProviderCardContract(payload);
}

export async function browseMonitorSandbox(leaseId: string, path: string): Promise<{
  current_path: string;
  parent_path: string | null;
  items: BrowseItem[];
}> {
  return readJsonOrThrow(
    await fetch(`/api/monitor/sandbox/${leaseId}/browse?path=${encodeURIComponent(path)}`),
  );
}

export async function readMonitorSandboxFile(
  leaseId: string,
  path: string,
): Promise<{ path: string; content: string; truncated: boolean }> {
  return readJsonOrThrow(
    await fetch(`/api/monitor/sandbox/${leaseId}/read?path=${encodeURIComponent(path)}`),
  );
}
