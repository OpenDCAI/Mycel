import { useCallback, useEffect, useMemo, useState } from "react";
import { useIsMobile } from "@/hooks/use-mobile";
import type { ProviderInfo } from "./resources/types";
import { deriveAllocatedResources } from "./resources/allocation";
import { fetchResourceProviders, refreshResourceProviders } from "./resources/api";
import ProviderCard from "./resources/ProviderCard";
import ProviderDetail from "./resources/ProviderDetail";

export default function ResourcesPage() {
  const isMobile = useIsMobile();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [summary, setSummary] = useState<{
    active_providers: number;
    running_sessions: number;
    last_refreshed_at?: string;
    refresh_status?: "ok" | "error";
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const applyPayload = useCallback((payload: Awaited<ReturnType<typeof fetchResourceProviders>>) => {
    const nextProviders = payload.providers;
    setSummary({
      active_providers: payload.summary.active_providers,
      running_sessions: payload.summary.running_sessions,
      last_refreshed_at: payload.summary.last_refreshed_at ?? payload.summary.snapshot_at,
      refresh_status: payload.summary.refresh_status ?? "ok",
    });
    setProviders(nextProviders);
    setSelectedId((prev) => {
      if (nextProviders.some((p) => p.id === prev)) return prev;
      return nextProviders[0]?.id ?? "";
    });
  }, []);

  const loadSnapshot = useCallback(async () => {
    const payload = await fetchResourceProviders();
    applyPayload(payload);
  }, [applyPayload]);

  const refreshNow = useCallback(async () => {
    setRefreshing(true);
    try {
      const payload = await refreshResourceProviders();
      applyPayload(payload);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh resources");
    } finally {
      setRefreshing(false);
    }
  }, [applyPayload]);

  useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchResourceProviders();
        if (cancelled) return;
        applyPayload(payload);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load resources");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadInitial();
    return () => {
      cancelled = true;
    };
  }, [applyPayload]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadSnapshot().catch(() => {});
    }, 30000);
    return () => window.clearInterval(timer);
  }, [loadSnapshot]);

  const selected = providers.find((p) => p.id === selectedId) ?? null;
  const activeCount = summary?.active_providers ?? 0;
  const totalSessions = summary?.running_sessions ?? 0;
  const refreshedAt = summary?.last_refreshed_at
    ? new Date(summary.last_refreshed_at).toLocaleTimeString()
    : "--:--:--";
  const refreshDotClass = summary?.refresh_status === "error" ? "bg-warning" : "bg-success";
  const allocatedResources = useMemo(() => deriveAllocatedResources(providers), [providers]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">Loading resources...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center bg-background p-6">
        <div className="max-w-lg rounded-xl border border-border bg-card px-5 py-4">
          <h3 className="text-sm font-semibold text-foreground mb-2">Resource API error</h3>
          <p className="text-xs text-muted-foreground font-mono break-all">{error}</p>
        </div>
      </div>
    );
  }

  if (!selected) {
    return (
      <div className="h-full flex items-center justify-center bg-background">
        <p className="text-sm text-muted-foreground">No providers configured.</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border bg-card/80 backdrop-blur-sm shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">资源</h2>
          <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono">
            <span className="inline-flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-slow" />
              {activeCount} 活跃
            </span>
            <span>·</span>
            <span>{totalSessions} 会话</span>
            <span>·</span>
            <span className="inline-flex items-center gap-1">
              <span className={`w-1.5 h-1.5 rounded-full ${refreshDotClass}`} />
              刷新 {refreshedAt}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            void refreshNow();
          }}
          disabled={refreshing}
          className="h-8 px-3 rounded-md border border-border text-xs text-foreground hover:bg-muted disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {refreshing ? "刷新中..." : "刷新"}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6">
        {/* Provider cards */}
        <div className={`grid gap-3 ${isMobile ? "grid-cols-2" : "grid-cols-3 xl:grid-cols-6"}`}>
          {providers.map((p) => (
            <ProviderCard
              key={p.id}
              provider={p}
              selected={p.id === selectedId}
              onSelect={() => p.status !== "unavailable" && setSelectedId(p.id)}
            />
          ))}
        </div>

        {/* Provider detail */}
        <div key={selectedId} className="animate-fade-in">
          <ProviderDetail provider={selected} allocatedResources={allocatedResources} />
        </div>
      </div>
    </div>
  );
}
