import { Pause, Play } from "lucide-react";
import { pauseThreadSandbox, resumeThreadSandbox, type LeaseStatus } from "../../api";

interface PanelHeaderProps {
  threadId: string | null;
  isRemote: boolean;
  lease: LeaseStatus | null;
  onClose: () => void;
  onRefreshStatus: () => Promise<unknown>;
}

export function PanelHeader({ threadId, isRemote, lease, onClose, onRefreshStatus }: PanelHeaderProps) {
  const instanceState = lease?.instance?.state;

  return (
    <div className="h-12 flex items-center justify-between px-4 flex-shrink-0 border-b border-border">
      <div>
        <h3 className="text-sm font-semibold text-foreground">另一台小电脑</h3>
        <p className="text-xs font-mono text-muted-foreground/70">
          {threadId ? threadId.slice(0, 20) : "无对话"}
        </p>
      </div>
      <div className="flex items-center gap-1">
        {isRemote && instanceState === "running" && (
          <button
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground/70 hover:bg-muted hover:text-foreground"
            onClick={() => void (threadId && pauseThreadSandbox(threadId).then(() => onRefreshStatus()))}
          >
            <Pause className="w-4 h-4" />
          </button>
        )}
        {isRemote && instanceState === "paused" && (
          <button
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground/70 hover:bg-muted hover:text-success"
            onClick={() => void (threadId && resumeThreadSandbox(threadId).then(() => onRefreshStatus()))}
          >
            <Play className="w-4 h-4" />
          </button>
        )}
        <button
          className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground/70 hover:bg-muted hover:text-foreground"
          onClick={onClose}
          title="收起视窗"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5">
            <polyline points="3,10 7,10 7,14" />
            <polyline points="13,6 9,6 9,2" />
          </svg>
        </button>
      </div>
    </div>
  );
}
