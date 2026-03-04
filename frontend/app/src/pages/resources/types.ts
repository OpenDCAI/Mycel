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
  snapshot: boolean;
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
}

export interface ProviderTelemetry {
  running: UsageMetric;
  cpu: UsageMetric;
  memory: UsageMetric;
  disk: UsageMetric;
  quota?: UsageMetric;
}

export interface SessionMetrics {
  cpu: number;
  memory: number;
  disk: number;
  networkIn: number;
  networkOut: number;
  webUrl?: string;
}

export interface ResourceSession {
  id: string;
  threadId: string;
  agentId: string;
  agentName: string;
  status: "running" | "paused" | "stopped";
  startedAt: string;
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
  consoleUrl?: string;
  latencyMs?: number;
  sessions: ResourceSession[];
}

/** An atomic resource allocated to an agent via a provider session */
export type ResourceType = keyof ProviderCapabilities;

export interface AllocatedResource {
  resourceType: ResourceType;
  providerId: string;
  providerName: string;
  threadId: string;
  agentId: string;
  agentName: string;
  sessionId: string;
  sessionStatus: ResourceSession["status"];
}
