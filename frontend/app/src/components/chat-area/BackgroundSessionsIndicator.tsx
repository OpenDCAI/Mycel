import { useState } from "react";
import { Loader2, CheckCircle2, XCircle, Terminal, Bot, X } from "lucide-react";
import type { BackgroundTask } from "../../hooks/use-background-tasks";

interface BackgroundSessionsIndicatorProps {
  tasks: BackgroundTask[];
  onCancelTask?: (taskId: string) => void;
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <Loader2 className="w-3 h-3 text-info animate-spin flex-shrink-0" />;
    case "completed":
      return <CheckCircle2 className="w-3 h-3 text-success flex-shrink-0" />;
    case "error":
      return <XCircle className="w-3 h-3 text-destructive flex-shrink-0" />;
    default:
      return <Loader2 className="w-3 h-3 text-muted-foreground flex-shrink-0" />;
  }
}

export function BackgroundSessionsIndicator({ tasks, onCancelTask }: BackgroundSessionsIndicatorProps) {
  const [isHovered, setIsHovered] = useState(false);

  const runningTasks = tasks.filter((t) => t.status === "running");
  const runningCount = runningTasks.length;

  if (runningCount === 0) return null;

  const agents = runningTasks.filter((t) => t.task_type === "agent");
  const terminals = runningTasks.filter((t) => t.task_type === "bash");

  return (
    <div
      className="absolute top-2 left-2 z-10"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* 入口：小圆点 + 数字 */}
      <div className="flex items-center gap-1 text-xs text-info font-medium cursor-default px-1.5 py-0.5 bg-info/10 backdrop-blur-sm rounded border border-info/20 hover:bg-info/10 transition-colors duration-fast select-none">
        <span className="w-1.5 h-1.5 rounded-full bg-info animate-pulse" />
        {runningCount}
      </div>

      {/* 悬浮面板 */}
      {isHovered && (
        <div className="absolute top-full left-0 pt-1">
          {/* 透明桥接区域，填充间隙 */}
          <div className="h-1" />
          <div className="bg-card rounded-lg shadow-lg border border-border p-3 min-w-[260px] max-w-[380px] animate-in fade-in slide-in-from-top-1 duration-fast">
            {agents.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 text-2xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                <Bot className="w-3 h-3" />
                Agent ({agents.length})
              </div>
              <div className="space-y-1 mb-2.5">
                {agents.map((task) => (
                  <div key={task.task_id} className="flex items-center gap-1.5 text-xs text-foreground-secondary group">
                    <StatusIcon status={task.status} />
                    <span className="truncate flex-1">{task.description || task.task_id}</span>
                    {task.status === "running" && onCancelTask && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onCancelTask(task.task_id);
                        }}
                        className="p-0.5 hover:bg-destructive/10 rounded transition-colors duration-fast flex-shrink-0"
                        title="取消任务"
                      >
                        <X className="w-3 h-3 text-destructive" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {terminals.length > 0 && (
            <div>
              {agents.length > 0 && <div className="border-t border-border mb-2.5" />}
              <div className="flex items-center gap-1.5 text-2xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">
                <Terminal className="w-3 h-3" />
                终端 ({terminals.length})
              </div>
              <div className="space-y-1">
                {terminals.map((task) => (
                  <div key={task.task_id} className="flex items-center gap-1.5 text-xs text-foreground-secondary group">
                    <StatusIcon status={task.status} />
                    <span className="font-mono truncate flex-1">{task.description || task.command_line || task.task_id}</span>
                    {task.status === "running" && onCancelTask && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onCancelTask(task.task_id);
                        }}
                        className="p-0.5 hover:bg-destructive/10 rounded transition-colors duration-fast flex-shrink-0"
                        title="取消任务"
                      >
                        <X className="w-3 h-3 text-destructive" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          </div>
        </div>
      )}
    </div>
  );
}
