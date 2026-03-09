import type { ProviderInfo } from "./types";

interface ResourceSummary {
  snapshot_at: string;
  last_refreshed_at?: string;
  refresh_duration_ms?: number;
  refresh_status?: "ok" | "error";
  refresh_error?: string | null;
  total_providers: number;
  active_providers: number;
  unavailable_providers: number;
  running_sessions: number;
}

interface ResourceOverviewResponse {
  summary: ResourceSummary;
  providers: ProviderInfo[];
}

function ensureProviderCardContract(providers: ProviderInfo[]): void {
  for (const provider of providers) {
    if (!provider.cardCpu) {
      throw new Error(`Provider cardCpu missing: ${provider.id}`);
    }
  }
}

async function ensureResponseShape(response: Response): Promise<ResourceOverviewResponse> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API ${response.status}: ${body || response.statusText}`);
  }

  const payload = (await response.json()) as ResourceOverviewResponse;
  if (!payload || !payload.summary || !Array.isArray(payload.providers)) {
    throw new Error("Unexpected /api/monitor/resources response shape");
  }
  ensureProviderCardContract(payload.providers);
  return payload;
}

export async function fetchResourceProviders(): Promise<ResourceOverviewResponse> {
  const response = await fetch("/api/monitor/resources", {
    headers: { "Content-Type": "application/json" },
  });
  return ensureResponseShape(response);
}

export async function refreshResourceProviders(): Promise<ResourceOverviewResponse> {
  const response = await fetch("/api/monitor/resources/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return ensureResponseShape(response);
}
