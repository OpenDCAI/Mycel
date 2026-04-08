export type ProviderStatus = "active" | "ready" | "unavailable";

export type ProviderType = "local" | "cloud" | "container";

export interface ProviderCapabilities {
  filesystem: boolean;
  terminal: boolean;
  metrics: boolean;
  screenshot: boolean;
  web: boolean;
  process: boolean;
  hooks: boolean;
  mount: boolean;
}

export interface ProviderQuota {
  used: number;
  limit: number;
}

export type MetricSource = "api" | "sandbox_db" | "derived" | "plan" | "console" | "unknown";
export type MetricFreshness = "live" | "cached" | "stale";

export interface UsageMetric {
  used: number | null;
  limit: number | null;
  unit: string;
  source: MetricSource;
  freshness?: MetricFreshness;
  error?: string;
}

export interface ProviderTelemetry {
  running: UsageMetric;
  cpu: UsageMetric;
  memory: UsageMetric;
  disk: UsageMetric;
  quota?: UsageMetric;
}

export interface SessionMetrics {
  cpu: number | null;
  memory: number | null;
  memoryLimit: number | null;
  memoryNote?: string;
  disk: number | null;
  diskLimit: number | null;
  diskNote?: string;
  networkIn: number | null;
  networkOut: number | null;
  probeError?: string;
  webUrl?: string;
}

export interface ResourceSession {
  id: string;
  leaseId?: string;
  threadId: string;
  runtimeSessionId?: string | null;
  agentUserId?: string | null;
  agentName: string;
  avatarUrl?: string | null;
  status: "running" | "paused" | "stopped" | "destroying";
  startedAt: string;
  createdAt?: string;
  metrics?: SessionMetrics;
}

export interface ProviderInfo {
  id: string;
  name: string;
  description: string;
  vendor?: string;
  type: ProviderType;
  status: ProviderStatus;
  unavailableReason?: string;
  error?: {
    code: string;
    message: string;
  } | null;
  capabilities: ProviderCapabilities;
  quota?: ProviderQuota;
  telemetry: ProviderTelemetry;
  cardCpu: UsageMetric;
  consoleUrl?: string;
  latencyMs?: number;
  sessions: ResourceSession[];
}

export interface ResourceSummary {
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

export interface ResourceOverviewResponse {
  summary: ResourceSummary;
  providers: ProviderInfo[];
}

export interface BrowseItem {
  name: string;
  path: string;
  is_dir: boolean;
}
