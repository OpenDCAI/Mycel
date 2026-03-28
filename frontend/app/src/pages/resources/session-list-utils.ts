import { useMemo } from "react";
import type { ResourceSession, SessionMetrics } from "./types";

export interface LeaseGroup {
  leaseId: string;
  status: ResourceSession["status"];
  sessions: ResourceSession[];
  startedAt: string;
  metrics: SessionMetrics | null;
}

const STATUS_ORDER: Record<ResourceSession["status"], number> = {
  running: 0,
  destroying: 1,
  paused: 2,
  stopped: 3,
};

export function useSessionCounts(sessions: ResourceSession[]) {
  return useMemo(
    () => ({
      running: sessions.filter((s) => s.status === "running").length,
      paused: sessions.filter((s) => s.status === "paused").length,
      stopped: sessions.filter((s) => s.status === "stopped").length,
    }),
    [sessions],
  );
}

export function groupByLease(sessions: ResourceSession[]): LeaseGroup[] {
  const map = new Map<string, ResourceSession[]>();
  for (const s of sessions) {
    // Group by leaseId; local sessions with no lease each get their own group
    const key = s.leaseId || s.id;
    const arr = map.get(key) ?? [];
    arr.push(s);
    map.set(key, arr);
  }

  return Array.from(map.values())
    .map((group) => {
      const sorted = [...group].sort(
        (a, b) => (STATUS_ORDER[a.status] ?? 4) - (STATUS_ORDER[b.status] ?? 4),
      );
      const best = sorted[0];
      const earliest = group.reduce(
        (min, s) => (s.startedAt < min ? s.startedAt : min),
        group[0].startedAt,
      );
      return {
        leaseId: group[0].leaseId ?? "",
        status: best.status,
        sessions: sorted,
        startedAt: earliest,
        metrics: best.metrics ?? null,
      } satisfies LeaseGroup;
    })
    .sort((a, b) => (STATUS_ORDER[a.status] ?? 4) - (STATUS_ORDER[b.status] ?? 4));
}
