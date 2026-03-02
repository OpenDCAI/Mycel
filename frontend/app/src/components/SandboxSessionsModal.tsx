import { Loader2, Pause, Play, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  destroySandboxSession,
  listSandboxSessions,
  pauseSandboxSession,
  resumeSandboxSession,
  type SandboxSession,
} from "../api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

interface SandboxSessionsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSessionMutated?: (threadId: string) => void;
}

export default function SandboxSessionsModal({ isOpen, onClose, onSessionMutated }: SandboxSessionsModalProps) {
  const [sessions, setSessions] = useState<SandboxSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh(opts?: { silent?: boolean }) {
    const silent = opts?.silent ?? false;
    const showInitialLoading = !hasLoaded && !silent;
    if (showInitialLoading) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    try {
      const rows = await listSandboxSessions();
      setSessions(rows);
      setHasLoaded(true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    if (!isOpen) return;
    void refresh();
    const timer = window.setInterval(() => {
      void refresh({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [isOpen]);

  async function withBusy(row: SandboxSession, fn: () => Promise<void>) {
    setBusy(row.session_id);
    try {
      await fn();
      if (!row.thread_id.startsWith("(")) {
        onSessionMutated?.(row.thread_id);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  function statusBadge(status: string) {
    if (status === "running") {
      return (
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-50 text-green-700 border border-green-200">
          运行中
        </span>
      );
    }
    if (status === "paused") {
      return (
        <span className="px-2 py-0.5 rounded text-xs font-medium bg-yellow-50 text-yellow-700 border border-yellow-200">
          已暂停
        </span>
      );
    }
    return (
      <span className="px-2 py-0.5 rounded text-xs font-medium bg-secondary text-muted-foreground border border-border">
        {status}
      </span>
    );
  }

  return (
    <Dialog open={isOpen} onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="sm:max-w-[860px] p-0 gap-0" showCloseButton>
        <DialogHeader className="h-12 px-5 flex-row items-center justify-between border-b border-border">
          <div className="flex items-center gap-3">
            <DialogTitle className="text-sm">运行环境会话</DialogTitle>
            {refreshing && (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground" />
            )}
          </div>
          <button
            className="px-3 py-1.5 rounded-lg text-xs border border-border text-foreground/70 hover:bg-accent hover:text-foreground"
            onClick={() => void refresh()}
          >
            刷新
          </button>
        </DialogHeader>

        <div className="p-5 overflow-auto max-h-[calc(85vh-48px)] custom-scrollbar">
          {loading && sessions.length === 0 && (
            <div className="flex items-center gap-2 py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
              <span className="text-sm text-muted-foreground">加载中...</span>
            </div>
          )}
          {error && sessions.length === 0 && <p className="text-sm py-8 text-center text-destructive">{error}</p>}
          {error && sessions.length > 0 && <p className="text-xs mb-3 text-destructive">刷新失败: {error}</p>}
          {!loading && sessions.length === 0 && !error && (
            <p className="text-sm py-8 text-center text-muted-foreground">暂无活跃会话</p>
          )}
          {sessions.length > 0 && (
            <div className="space-y-2">
              {sessions.map((row) => (
                <div
                  key={row.session_id}
                  className="flex items-center gap-4 p-3 rounded-lg bg-accent/50 border border-border"
                >
                  <div className="flex-1 min-w-0 grid grid-cols-4 gap-3 items-center">
                    <div>
                      <div className="text-[10px] uppercase tracking-wider mb-0.5 text-muted-foreground">对话</div>
                      <div className="text-sm font-mono truncate">{row.thread_id.slice(0, 16)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider mb-0.5 text-muted-foreground">会话</div>
                      <div className="text-sm font-mono truncate">{row.session_id.slice(0, 16)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider mb-0.5 text-muted-foreground">环境</div>
                      <div className="text-sm">{row.provider}</div>
                    </div>
                    <div>
                      <div className="text-[10px] uppercase tracking-wider mb-0.5 text-muted-foreground">状态</div>
                      {statusBadge(row.status)}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {row.status === "running" && (
                      <button
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
                        disabled={busy === row.session_id}
                        onClick={() => void withBusy(row, () => pauseSandboxSession(row.session_id, row.provider))}
                        title="暂停"
                      >
                        <Pause className="w-4 h-4" />
                      </button>
                    )}
                    {row.status === "paused" && (
                      <button
                        className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-accent hover:text-green-600 disabled:opacity-30"
                        disabled={busy === row.session_id}
                        onClick={() => void withBusy(row, () => resumeSandboxSession(row.session_id, row.provider))}
                        title="恢复"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-30"
                      disabled={busy === row.session_id}
                      onClick={() => void withBusy(row, () => destroySandboxSession(row.session_id, row.provider))}
                      title="销毁"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
