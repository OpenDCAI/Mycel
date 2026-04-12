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
  triage?: {
    summary?: {
      active_drift?: number;
      detached_residue?: number;
      orphan_cleanup?: number;
    };
  };
}

export interface ProviderOrphanSession {
  session_id: string;
  provider: string;
  status: string;
  source: "provider_orphan";
}

export interface ProviderOrphanSessionsResponse {
  count: number;
  sessions: ProviderOrphanSession[];
}

export interface BrowseItem {
  name: string;
  path: string;
  is_dir: boolean;
}
