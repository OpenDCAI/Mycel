import { memo, useState } from "react";
import { useParams } from "react-router-dom";
import type { ToolRendererProps } from "./types";
import { asRecord, recordString } from "@/lib/records";

function parseArgs(args: unknown): {
  description?: string;
  prompt?: string;
  subject?: string;
  taskId?: string;
  status?: string;
  subagent_type?: string;
} {
  const a = asRecord(args);
  if (!a) return {};
  return {
    description: recordString(a, "Description") ?? recordString(a, "description"),
    prompt: recordString(a, "Prompt") ?? recordString(a, "prompt"),
    subject: recordString(a, "subject") ?? recordString(a, "Subject"),
    taskId: recordString(a, "taskId") ?? recordString(a, "TaskId"),
    status: recordString(a, "status") ?? recordString(a, "Status"),
    subagent_type: recordString(a, "SubagentType") ?? recordString(a, "subagent_type"),
  };
}

function getTaskLabel(name: string, args: ReturnType<typeof parseArgs>): string {
  switch (name) {
    case "TaskCreate":
      return args.subject || args.description?.slice(0, 50) || "创建任务";
    case "TaskUpdate":
      return args.status ? `更新任务 #${args.taskId ?? "?"} → ${args.status}` : `更新任务 #${args.taskId ?? "?"}`;
    case "TaskList":
      return "查看任务列表";
    case "TaskGet":
      return `查看任务 #${args.taskId ?? "?"}`;
    case "Task":
      return args.description?.slice(0, 50) || args.prompt?.slice(0, 50) || "子任务";
    default:
      return args.description?.slice(0, 60) || args.prompt?.slice(0, 60) || "执行子任务";
  }
}

function taskOutputText(value: unknown): string {
  const data = asRecord(value);
  if (!data) return JSON.stringify(value, null, 2);
  const result = data.result;
  if (typeof result === "string") return result;
  if (result !== undefined && result !== null) return JSON.stringify(result, null, 2);
  return recordString(data, "text") ?? JSON.stringify(value, null, 2);
}

export default memo(function TaskRenderer({ step, expanded }: ToolRendererProps) {
  const { threadId } = useParams<{ threadId?: string }>();
  const args = parseArgs(step.args);
  const label = getTaskLabel(step.name, args);
  const stream = step.subagent_stream;
  const [taskOutput, setTaskOutput] = useState<string | null>(null);
  const [loadingOutput, setLoadingOutput] = useState(false);

  const handleViewDetails = async () => {
    if (!threadId || !stream?.task_id) return;
    setLoadingOutput(true);
    try {
      const res = await fetch(`/api/threads/${threadId}/tasks/${stream.task_id}`);
      setTaskOutput(taskOutputText(await res.json()));
    } catch {
      setTaskOutput("加载失败");
    } finally {
      setLoadingOutput(false);
    }
  };

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="truncate max-w-[320px]">{label}</span>
        {step.status === "calling" && stream?.status === "running" && (
          <span className="text-muted-foreground/70">streaming...</span>
        )}
        {step.status === "calling" && !stream && <span className="text-muted-foreground/70">...</span>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {args.prompt && (
        <div className="p-3 rounded-lg text-xs bg-muted border border-border text-foreground-secondary whitespace-pre-wrap">
          {args.prompt}
        </div>
      )}

      {/* Real-time streaming output */}
      {stream && (
        <div className="p-3 rounded-lg text-xs bg-info/10 border border-info/20 space-y-2">
          <div className="flex items-center gap-2 text-info font-medium">
            <span>{stream.description || args.description || "子任务"}</span>
            {stream.status === "running" && (
              <span className="inline-block w-2 h-2 bg-info rounded-full animate-pulse" />
            )}
            {stream.status === "completed" && <span className="text-success">✓</span>}
            {stream.status === "error" && <span className="text-destructive">✗</span>}
          </div>

          {stream.text && (
            <div className="text-foreground-secondary whitespace-pre-wrap">{stream.text}</div>
          )}

          {stream.tool_calls.length > 0 && (
            <div className="space-y-1">
              {stream.tool_calls.map((tc, idx) => (
                <div key={idx} className="text-muted-foreground text-xs font-mono">
                  → {tc.name}
                </div>
              ))}
            </div>
          )}

          {stream.error && (
            <div className="text-destructive text-xs">{stream.error}</div>
          )}
        </div>
      )}

      {step.result && (
        <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[200px] overflow-y-auto font-mono bg-muted border border-border text-foreground-secondary">
          {step.result}
        </pre>
      )}

      {/* 查看详情：拉取 Task Output REST API */}
      {stream?.task_id && threadId && step.status === "done" && (
        <div className="mt-1">
          {taskOutput === null ? (
            <button
              onClick={handleViewDetails}
              disabled={loadingOutput}
              className="text-xs text-info hover:underline disabled:opacity-50"
            >
              {loadingOutput ? "加载中..." : "查看详情"}
            </button>
          ) : (
            <div className="mt-1.5 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">任务输出</span>
                <button onClick={() => setTaskOutput(null)} className="text-xs text-muted-foreground/70 hover:text-muted-foreground">
                  收起
                </button>
              </div>
              <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[300px] overflow-y-auto font-mono bg-info/5 border border-info/20 text-info">
                {taskOutput}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
