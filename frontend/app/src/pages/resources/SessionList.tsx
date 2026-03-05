import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, File, Folder, Home, X } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ResourceSession, SessionMetrics } from "./types";
import { getAgentColor, getAgentInitials } from "./utils/avatar";
import { calculateDuration, formatDuration } from "./utils/duration";
import { formatMetric } from "./utils/format";
import { useDirectoryBrowser } from "@/hooks/use-directory-browser";

// ---------------------------------------------------------------------------
// Grouping
// ---------------------------------------------------------------------------

interface LeaseGroup {
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

function groupByLease(sessions: ResourceSession[]): LeaseGroup[] {
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
        (a, b) => (STATUS_ORDER[a.status] ?? 4) - (STATUS_ORDER[b.status] ?? 4)
      );
      const best = sorted[0];
      const earliest = group.reduce(
        (min, s) => (s.startedAt < min ? s.startedAt : min),
        group[0].startedAt
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

// ---------------------------------------------------------------------------
// Public component
// ---------------------------------------------------------------------------

interface SessionListProps {
  sessions: ResourceSession[];
  providerType: string;
}

export default function SessionList({ sessions, providerType }: SessionListProps) {
  if (sessions.length === 0) {
    return <p className="text-xs text-muted-foreground">暂无会话</p>;
  }

  const groups = groupByLease(sessions);

  return (
    <div className="space-y-2">
      {groups.map((group) => (
        <LeaseItem key={group.leaseId || group.sessions[0].id} group={group} providerType={providerType} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LeaseItem
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<ResourceSession["status"], string> = {
  running: "运行中",
  paused: "已暂停",
  stopped: "已结束",
  destroying: "销毁中",
};

function LeaseItem({ group, providerType }: { group: LeaseGroup; providerType: string }) {
  const [expanded, setExpanded] = useState(false);
  const duration = group.startedAt ? calculateDuration(group.startedAt) : null;
  const isStopped = group.status === "stopped";
  const canBrowse = group.status !== "stopped" && group.status !== "destroying";

  const hasMetrics =
    group.metrics != null &&
    (group.metrics.cpu != null || group.metrics.memory != null || group.metrics.disk != null);

  return (
    <div className={`rounded-md border border-border/50 bg-card/60 overflow-hidden ${isStopped ? "opacity-50" : ""}`}>
      {/* Row */}
      <button
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/20 transition-colors text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <StatusDot status={group.status} />
        {expanded ? (
          <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />
        )}

        {/* Crew avatars */}
        <div className="flex -space-x-1 shrink-0">
          {group.sessions.slice(0, 4).map((s) => (
            <Avatar key={s.id || s.leaseId} className="w-5 h-5 border border-background">
              <AvatarFallback className={`${getAgentColor(s.agentId)} text-[8px]`}>
                {getAgentInitials(s.agentName)}
              </AvatarFallback>
            </Avatar>
          ))}
          {group.sessions.length > 4 && (
            <div className="w-5 h-5 rounded-full bg-muted border border-background flex items-center justify-center text-[8px] text-muted-foreground">
              +{group.sessions.length - 4}
            </div>
          )}
        </div>

        {/* Names */}
        <span className="text-xs text-foreground flex-1 truncate">
          {group.sessions.map((s) => s.agentName || "未绑定").join(", ")}
        </span>

        {/* Lease ID */}
        {group.leaseId && (
          <span className="text-[10px] text-muted-foreground font-mono shrink-0">
            {shortId(group.leaseId)}
          </span>
        )}

        {/* Duration + status */}
        <div className="flex items-center gap-2 shrink-0">
          {duration != null && (
            <span className="text-[10px] text-muted-foreground">{formatDuration(duration)}</span>
          )}
          <span className="text-[10px] text-muted-foreground">{STATUS_LABEL[group.status]}</span>
        </div>
      </button>

      {/* Expanded panel */}
      {expanded && (
        <div className="border-t border-border/30">
          {/* Metrics bar */}
          {hasMetrics && (
            <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[10px] font-mono bg-muted/10 border-b border-border/20">
              <MetricCell label="CPU" value={group.metrics?.cpu} unit="%" />
              <MetricCell label="RAM" value={group.metrics?.memory} unit="GB" />
              <MetricCell label="磁盘" value={group.metrics?.disk} unit="GB" />
            </div>
          )}
          {/* File browser */}
          <div className="px-3 py-2">
            {canBrowse ? (
              <SandboxBrowser leaseId={group.leaseId} providerType={providerType} />
            ) : (
              <p className="text-[11px] text-muted-foreground text-center py-2">沙盒已停止，无法浏览文件</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sandbox file browser — uses shared useDirectoryBrowser hook
// ---------------------------------------------------------------------------

function SandboxBrowser({ leaseId, providerType }: { leaseId: string; providerType: string }) {
  const isLocal = providerType === "local" || !leaseId;
  const defaultPath = isLocal ? "~" : "/";

  const buildBrowseUrl = (path: string) =>
    isLocal
      ? `/api/settings/browse?path=${encodeURIComponent(path)}&include_files=true`
      : `/api/monitor/sandbox/${leaseId}/browse?path=${encodeURIComponent(path)}`;

  const buildReadUrl = (path: string) =>
    isLocal
      ? `/api/settings/read?path=${encodeURIComponent(path)}`
      : `/api/monitor/sandbox/${leaseId}/read?path=${encodeURIComponent(path)}`;

  const { currentPath, parentPath, items, loading, error, loadPath } =
    useDirectoryBrowser(buildBrowseUrl, defaultPath);

  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  useEffect(() => {
    void loadPath(defaultPath);
    setSelectedFile(null);
    setFileContent(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaseId]);

  async function openFile(path: string) {
    if (selectedFile === path) {
      setSelectedFile(null);
      setFileContent(null);
      return;
    }
    setSelectedFile(path);
    setFileContent(null);
    setFileError(null);
    setFileLoading(true);
    try {
      const resp = await fetch(buildReadUrl(path));
      if (!resp.ok) throw new Error(`${resp.status}`);
      const data = await resp.json() as { content: string; truncated: boolean };
      setFileContent(data.content);
      if (data.truncated) setFileError("(内容已截断至 100 KB)");
    } catch (e) {
      setFileError(e instanceof Error ? e.message : "读取失败");
    } finally {
      setFileLoading(false);
    }
  }

  return (
    <div className="text-xs">
      {/* Path bar */}
      <div className="flex items-center gap-1.5 mb-1.5">
        <button
          onClick={() => { void loadPath(defaultPath); setSelectedFile(null); setFileContent(null); }}
          className="text-muted-foreground hover:text-foreground transition-colors"
          title="返回根目录"
        >
          <Home className="w-3 h-3" />
        </button>
        <span className="font-mono text-muted-foreground truncate flex-1 text-[10px]">{currentPath}</span>
      </div>

      <ScrollArea className="h-[180px] border rounded border-border/30">
        <div className="p-1 space-y-0.5">
          {parentPath && (
            <button
              onClick={() => loadPath(parentPath)}
              className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 rounded text-muted-foreground"
            >
              <Folder className="w-3 h-3 shrink-0" />
              <span>..</span>
            </button>
          )}

          {loading && (
            <div className="text-center py-6 text-muted-foreground">加载中...</div>
          )}
          {error && (
            <div className="text-center py-6 text-destructive text-[11px]">{error}</div>
          )}

          {!loading && !error && items.length === 0 && (
            <div className="text-center py-6 text-muted-foreground">此目录为空</div>
          )}

          {!loading && !error && items.map((item) =>
            item.is_dir ? (
              <button
                key={item.path}
                onClick={() => loadPath(item.path)}
                className="w-full flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 rounded"
              >
                <Folder className="w-3 h-3 text-muted-foreground shrink-0" />
                <span className="flex-1 text-left truncate">{item.name}</span>
              </button>
            ) : (
              <button
                key={item.path}
                onClick={() => { void openFile(item.path); }}
                className={`w-full flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 rounded text-left ${
                  selectedFile === item.path ? "bg-muted/40 text-foreground" : "text-muted-foreground"
                }`}
              >
                <File className="w-3 h-3 shrink-0" />
                <span className="truncate">{item.name}</span>
              </button>
            )
          )}
        </div>
      </ScrollArea>

      {/* File content panel */}
      {selectedFile && (
        <div className="mt-1.5 border rounded border-border/30 bg-muted/5">
          <div className="flex items-center justify-between px-2 py-1 border-b border-border/20">
            <span className="text-[10px] font-mono text-muted-foreground truncate flex-1">
              {selectedFile.split("/").pop()}
            </span>
            <button
              onClick={() => { setSelectedFile(null); setFileContent(null); setFileError(null); }}
              className="ml-2 text-muted-foreground hover:text-foreground shrink-0"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
          <ScrollArea className="h-[200px]">
            <div className="p-2">
              {fileLoading && (
                <div className="text-center py-6 text-muted-foreground text-[11px]">加载中...</div>
              )}
              {!fileLoading && fileError && !fileContent && (
                <div className="text-center py-6 text-destructive text-[11px]">{fileError}</div>
              )}
              {fileContent != null && (
                <>
                  <pre className="text-[10px] font-mono text-foreground whitespace-pre-wrap break-all leading-relaxed">
                    {fileContent}
                  </pre>
                  {fileError && (
                    <p className="text-[10px] text-muted-foreground mt-1 italic">{fileError}</p>
                  )}
                </>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function StatusDot({ status }: { status: ResourceSession["status"] }) {
  const cls = {
    running: "bg-success animate-pulse",
    paused: "bg-warning/80",
    stopped: "bg-muted-foreground/40",
    destroying: "bg-destructive animate-pulse",
  }[status];
  return <span className={`h-2 w-2 rounded-full shrink-0 ${cls}`} />;
}

function MetricCell({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null | undefined;
  unit: string;
}) {
  return (
    <div className="rounded border border-border/40 bg-muted/20 px-2 py-1">
      <p className="text-muted-foreground">{label}</p>
      <p className="text-foreground font-semibold">{formatMetric(value, unit)}</p>
    </div>
  );
}

function shortId(raw: string): string {
  if (!raw) return "--";
  return raw.length <= 12 ? raw : `${raw.slice(0, 8)}…`;
}
