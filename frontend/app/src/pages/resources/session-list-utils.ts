import type { ResourceSession, SessionMetrics } from "./types";

export interface LeaseGroup {
  leaseId: string;
  status: ResourceSession["status"];
  sessions: ResourceSession[];
  startedAt: string;
  metrics: SessionMetrics | null;
}
