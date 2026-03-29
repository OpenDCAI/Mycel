import { ExternalLink, Play, Trash2, X } from "lucide-react";
import type { ScheduledTask, ScheduledTaskRun } from "@/store/types";

type ScheduledTaskDraft = Pick<
  ScheduledTask,
  "id" | "thread_id" | "name" | "instruction" | "cron_expression" | "enabled"
> & Partial<Pick<ScheduledTask, "last_triggered_at" | "next_trigger_at" | "created_at" | "updated_at">>;

interface ScheduledTaskEditorProps {
  open: boolean;
  mode: "create" | "edit";
  isMobile: boolean;
  draft: ScheduledTaskDraft;
  runs: ScheduledTaskRun[];
  onUpdate: (draft: ScheduledTaskDraft) => void;
  onSave: () => void;
  onClose: () => void;
  onDelete?: () => void;
  onTrigger?: () => void;
  saving?: boolean;
}

function formatTimestamp(value?: number): string {
  if (!value) return "--";
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function runTone(status: ScheduledTaskRun["status"]): string {
  if (status === "completed") return "bg-success/10 text-success";
  if (status === "failed") return "bg-destructive/10 text-destructive";
  if (status === "dispatched") return "bg-primary/10 text-primary";
  return "bg-muted text-muted-foreground";
}

export default function ScheduledTaskEditor({
  open,
  mode,
  isMobile,
  draft,
  runs,
  onUpdate,
  onSave,
  onClose,
  onDelete,
  onTrigger,
  saving = false,
}: ScheduledTaskEditorProps) {
  if (!open) return null;

  const isCreate = mode === "create";
  const canSave = draft.name.trim() && draft.thread_id.trim() && draft.instruction.trim() && draft.cron_expression.trim();

  const shellClassName = isCreate || isMobile
    ? "fixed inset-0 z-50 flex items-center justify-center"
    : "w-[420px] shrink-0 border-l border-border bg-background flex flex-col";

  const cardClassName = isCreate || isMobile
    ? "relative w-full max-w-xl mx-4 bg-background rounded-2xl shadow-2xl border border-border flex flex-col max-h-[88vh] overflow-hidden"
    : "flex flex-col h-full";

  const body = (
    <div className={cardClassName}>
      <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{isCreate ? "新建定时任务" : "编辑定时任务"}</h3>
          <p className="text-xs text-muted-foreground mt-1">直接调度长期存在的 thread，不再创建中间 task 记录。</p>
        </div>
        <div className="flex items-center gap-1.5">
          {!isCreate && onTrigger && (
            <button
              onClick={onTrigger}
              className="px-3 py-1.5 rounded-lg bg-primary/10 text-primary text-xs font-medium hover:bg-primary/15 transition-colors"
            >
              <span className="inline-flex items-center gap-1"><Play className="w-3.5 h-3.5" />立即触发</span>
            </button>
          )}
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        <div className="space-y-2">
          <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">名称</span>
          <input
            value={draft.name}
            onChange={(e) => onUpdate({ ...draft, name: e.target.value })}
            placeholder="例如：每日 thread 总结"
            className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm font-medium text-foreground outline-none focus:border-primary/40 transition-colors"
          />
        </div>

        <div className="space-y-2">
          <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">Thread ID</span>
          <div className="flex items-center gap-2">
            <input
              value={draft.thread_id}
              onChange={(e) => onUpdate({ ...draft, thread_id: e.target.value })}
              placeholder="thread-main"
              className="flex-1 px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm font-mono text-foreground outline-none focus:border-primary/40 transition-colors"
            />
            {draft.thread_id ? (
              <a
                href={`/chat/${draft.thread_id}`}
                className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-border text-xs text-primary hover:bg-primary/5 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                查看
              </a>
            ) : null}
          </div>
        </div>

        <div className="space-y-2">
          <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">Cron</span>
          <input
            value={draft.cron_expression}
            onChange={(e) => onUpdate({ ...draft, cron_expression: e.target.value })}
            placeholder="0 9 * * *"
            className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm font-mono text-foreground outline-none focus:border-primary/40 transition-colors"
          />
        </div>

        <div className="space-y-2">
          <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">指令</span>
          <textarea
            value={draft.instruction}
            onChange={(e) => onUpdate({ ...draft, instruction: e.target.value })}
            placeholder="例如：总结今天 thread 中最重要的决策和风险。"
            rows={5}
            className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors resize-none leading-relaxed"
          />
        </div>

        <div className="flex items-center justify-between rounded-xl border border-border bg-card/70 px-3.5 py-3">
          <div>
            <p className="text-sm font-medium text-foreground">启用调度</p>
            <p className="text-xs text-muted-foreground mt-1">关闭后不会自动触发，但仍可手动运行。</p>
          </div>
          <button
            onClick={() => onUpdate({ ...draft, enabled: draft.enabled ? 0 : 1 })}
            className={`relative w-11 h-6 rounded-full transition-colors ${draft.enabled ? "bg-primary" : "bg-muted"}`}
          >
            <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform ${draft.enabled ? "left-[22px]" : "left-0.5"}`} />
          </button>
        </div>

        {!isCreate && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-border bg-card/70 px-3.5 py-3">
                <div className="text-[11px] text-muted-foreground uppercase tracking-wider">上次触发</div>
                <div className="mt-2 text-sm font-medium text-foreground">{formatTimestamp(draft.last_triggered_at)}</div>
              </div>
              <div className="rounded-xl border border-border bg-card/70 px-3.5 py-3">
                <div className="text-[11px] text-muted-foreground uppercase tracking-wider">下次触发</div>
                <div className="mt-2 text-sm font-medium text-foreground">{formatTimestamp(draft.next_trigger_at)}</div>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">最近运行记录</span>
                <span className="text-[11px] text-muted-foreground">{runs.length} 条</span>
              </div>
              <div className="space-y-2">
                {runs.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border px-3.5 py-5 text-xs text-muted-foreground">
                    还没有运行记录。可以先点“立即触发”打一条真实 run。
                  </div>
                ) : runs.slice(0, 6).map((run) => (
                  <div key={run.id} className="rounded-xl border border-border bg-card/70 px-3.5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium ${runTone(run.status)}`}>
                        {run.status}
                      </span>
                      <span className="text-[11px] font-mono text-muted-foreground">{formatTimestamp(run.triggered_at)}</span>
                    </div>
                    <div className="mt-2 text-xs text-foreground break-all">
                      thread_run_id: {run.thread_run_id || "--"}
                    </div>
                    {run.error ? (
                      <div className="mt-2 text-xs text-destructive break-all">{run.error}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 px-5 py-4 border-t border-border shrink-0">
        <div>
          {!isCreate && onDelete ? (
            <button
              onClick={onDelete}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-xl text-xs text-destructive hover:bg-destructive/5 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              删除
            </button>
          ) : <span />}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            取消
          </button>
          <button
            onClick={onSave}
            disabled={!canSave || saving}
            className="px-5 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? (isCreate ? "创建中..." : "保存中...") : (isCreate ? "创建" : "保存")}
          </button>
        </div>
      </div>
    </div>
  );

  if (isCreate || isMobile) {
    return (
      <div className={shellClassName}>
        <div className="absolute inset-0 bg-black/50" onClick={onClose} />
        {body}
      </div>
    );
  }

  return <div className={shellClassName}>{body}</div>;
}
