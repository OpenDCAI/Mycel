import { useState, useMemo } from "react";
import { X, Calendar, User, Tag, ChevronDown } from "lucide-react";
import type { Priority, CronJob, Task } from "@/store/types";

// ── Shared constants ──────────────────────────────────────

type TabType = "task" | "cron";

const CATEGORIES = [
  { id: "code-review", label: "代码审查", color: "bg-blue-500" },
  { id: "report", label: "日报周报", color: "bg-emerald-500" },
  { id: "backup", label: "数据备份", color: "bg-amber-500" },
  { id: "security", label: "安全检查", color: "bg-red-500" },
  { id: "cleanup", label: "清理维护", color: "bg-violet-500" },
  { id: "monitoring", label: "监控巡检", color: "bg-cyan-500" },
  { id: "other", label: "其他", color: "bg-gray-400" },
];

const PRIORITY_OPTIONS: { value: Priority; label: string; active: string }[] = [
  { value: "high", label: "高", active: "bg-destructive/10 text-destructive border-destructive/20" },
  { value: "medium", label: "中", active: "bg-warning/10 text-warning border-warning/20" },
  { value: "low", label: "低", active: "bg-muted text-muted-foreground border-border" },
];

// ── Cron schedule types ───────────────────────────────────

type Frequency = "interval" | "daily" | "weekdays" | "weekly" | "monthly";

interface ScheduleState {
  frequency: Frequency;
  hour: number;
  minute: number;
  weekdays: number[];
  monthDay: number;
  intervalValue: number;
}

const FREQ_OPTIONS: { value: Frequency; label: string }[] = [
  { value: "interval", label: "每隔" },
  { value: "daily", label: "每天" },
  { value: "weekdays", label: "工作日" },
  { value: "weekly", label: "每周" },
  { value: "monthly", label: "每月" },
];

const WEEK_LABELS = ["日", "一", "二", "三", "四", "五", "六"];
const INTERVAL_OPTIONS = [1, 2, 3, 4, 6, 8, 12];

function buildCron(s: ScheduleState): string {
  switch (s.frequency) {
    case "interval": return `${s.minute} */${s.intervalValue} * * *`;
    case "daily": return `${s.minute} ${s.hour} * * *`;
    case "weekdays": return `${s.minute} ${s.hour} * * 1-5`;
    case "weekly": return `${s.minute} ${s.hour} * * ${[...s.weekdays].sort().join(",")}`;
    case "monthly": return `${s.minute} ${s.hour} ${s.monthDay} * *`;
  }
}

function scheduleToHuman(s: ScheduleState): string {
  const t = `${String(s.hour).padStart(2, "0")}:${String(s.minute).padStart(2, "0")}`;
  switch (s.frequency) {
    case "interval": return `每 ${s.intervalValue} 小时`;
    case "daily": return `每天 ${t}`;
    case "weekdays": return `工作日 ${t}`;
    case "weekly": return `每周${s.weekdays.map((d) => WEEK_LABELS[d]).join("、")} ${t}`;
    case "monthly": return `每月 ${s.monthDay} 日 ${t}`;
  }
}

// ── Props ─────────────────────────────────────────────────

interface Member {
  id: string;
  name: string;
}

interface CreateTaskModalProps {
  open: boolean;
  defaultTab?: TabType;
  members: Member[];
  onClose: () => void;
  onCreateTask: (fields: Partial<Task>) => Promise<void>;
  onCreateCronJob: (fields: Partial<CronJob>) => Promise<void>;
}

// ── Component ─────────────────────────────────────────────

export default function CreateTaskModal({ open, defaultTab = "task", members, onClose, onCreateTask, onCreateCronJob }: CreateTaskModalProps) {
  const [tab, setTab] = useState<TabType>(defaultTab);
  const [saving, setSaving] = useState(false);

  // ── Task form state ──
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [assigneeId, setAssigneeId] = useState("");
  const [deadline, setDeadline] = useState("");
  const [category, setCategory] = useState("other");

  // ── Cron form state ──
  const [cronName, setCronName] = useState("");
  const [cronDescription, setCronDescription] = useState("");
  const [schedule, setSchedule] = useState<ScheduleState>({
    frequency: "daily", hour: 9, minute: 0, weekdays: [1], monthDay: 1, intervalValue: 2,
  });
  const [cronTaskTitle, setCronTaskTitle] = useState("");
  const [cronTaskDescription, setCronTaskDescription] = useState("");
  const [cronTaskPriority, setCronTaskPriority] = useState<Priority>("medium");
  const [cronCategory, setCronCategory] = useState("other");
  const [freqOpen, setFreqOpen] = useState(false);

  const humanSchedule = useMemo(() => scheduleToHuman(schedule), [schedule]);

  const resetForm = () => {
    setTitle(""); setDescription(""); setPriority("medium"); setAssigneeId(""); setDeadline(""); setCategory("other");
    setCronName(""); setCronDescription(""); setCronTaskTitle(""); setCronTaskDescription(""); setCronTaskPriority("medium"); setCronCategory("other");
    setSchedule({ frequency: "daily", hour: 9, minute: 0, weekdays: [1], monthDay: 1, intervalValue: 2 });
    setFreqOpen(false);
  };

  const handleClose = () => { resetForm(); onClose(); };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (tab === "task") {
        if (!title.trim()) return;
        await onCreateTask({ title: title.trim(), description, priority, assignee_id: assigneeId, deadline, source: "manual" });
      } else {
        if (!cronName.trim()) return;
        const cronExpr = buildCron(schedule);
        const taskTemplate = JSON.stringify({ title: cronTaskTitle, description: cronTaskDescription, priority: cronTaskPriority, category: cronCategory });
        await onCreateCronJob({ name: cronName.trim(), description: cronDescription, cron_expression: cronExpr, task_template: taskTemplate, enabled: 1 });
      }
      handleClose();
    } finally {
      setSaving(false);
    }
  };

  const canSave = tab === "task" ? title.trim().length > 0 : cronName.trim().length > 0;

  const updateSchedule = (patch: Partial<ScheduleState>) => setSchedule((s) => ({ ...s, ...patch }));

  const toggleWeekday = (day: number) => {
    setSchedule((s) => {
      const has = s.weekdays.includes(day);
      const next = has ? s.weekdays.filter((d) => d !== day) : [...s.weekdays, day];
      return { ...s, weekdays: next.length ? next : [day] };
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-background rounded-2xl shadow-2xl border border-border flex flex-col max-h-[85vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3">
          <h2 className="text-base font-semibold text-foreground">新建任务</h2>
          <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>

        {/* Tab switcher */}
        <div className="px-6 pb-3">
          <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
            <button
              onClick={() => setTab("task")}
              className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                tab === "task" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              普通任务
            </button>
            <button
              onClick={() => setTab("cron")}
              className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                tab === "cron" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              定时任务
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto px-6 pb-2">
          {tab === "task" ? (
            <div className="space-y-4">
              {/* Title */}
              <div>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="任务标题 *"
                  autoFocus
                  className="w-full text-lg font-semibold text-foreground bg-transparent outline-none placeholder:text-muted-foreground/50"
                />
              </div>

              {/* Description */}
              <div>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="描述这个任务..."
                  rows={3}
                  className="w-full text-sm text-foreground bg-transparent outline-none placeholder:text-muted-foreground/40 resize-none leading-relaxed"
                />
              </div>

              <div className="border-t border-border" />

              {/* Category */}
              <div className="space-y-2">
                <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1">
                  <Tag className="w-3 h-3" />分类
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {CATEGORIES.map((cat) => (
                    <button
                      key={cat.id}
                      onClick={() => setCategory(cat.id)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                        category === cat.id
                          ? "bg-foreground text-background shadow-sm"
                          : "bg-muted/60 text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full ${cat.color}`} />
                      {cat.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Priority */}
              <div className="space-y-2">
                <span className="text-[11px] text-muted-foreground font-medium">优先级</span>
                <div className="flex gap-2">
                  {PRIORITY_OPTIONS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => setPriority(p.value)}
                      className={`flex-1 py-2 rounded-xl text-xs font-medium border transition-all ${
                        priority === p.value ? p.active + " shadow-sm" : "bg-transparent border-border text-muted-foreground hover:bg-muted/40"
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Assignee */}
              <div className="space-y-2">
                <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1">
                  <User className="w-3 h-3" />执行者
                </span>
                <select
                  value={assigneeId}
                  onChange={(e) => setAssigneeId(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors"
                >
                  <option value="">未分配</option>
                  {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              </div>

              {/* Deadline */}
              <div className="space-y-2">
                <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1">
                  <Calendar className="w-3 h-3" />截止日期
                </span>
                <input
                  type="date"
                  value={deadline}
                  onChange={(e) => setDeadline(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors"
                />
              </div>
            </div>
          ) : (
            /* ── Cron Tab ── */
            <div className="space-y-4">
              {/* Name */}
              <div>
                <input
                  value={cronName}
                  onChange={(e) => setCronName(e.target.value)}
                  placeholder="定时任务名称 *"
                  autoFocus
                  className="w-full text-lg font-semibold text-foreground bg-transparent outline-none placeholder:text-muted-foreground/50"
                />
              </div>

              {/* Description */}
              <div>
                <textarea
                  value={cronDescription}
                  onChange={(e) => setCronDescription(e.target.value)}
                  placeholder="描述这个定时任务..."
                  rows={2}
                  className="w-full text-sm text-foreground bg-transparent outline-none placeholder:text-muted-foreground/40 resize-none leading-relaxed"
                />
              </div>

              <div className="border-t border-border" />

              {/* Schedule */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">调度频率</span>
                  <span className="text-xs text-primary font-medium">{humanSchedule}</span>
                </div>

                {/* Sentence builder */}
                <div className="flex items-center gap-2 flex-wrap">
                  {/* Frequency dropdown */}
                  <div className="relative">
                    <button
                      onClick={() => setFreqOpen(!freqOpen)}
                      className="flex items-center gap-1 px-3 py-2 rounded-xl bg-primary/8 border border-primary/15 text-sm font-medium text-primary hover:bg-primary/12 transition-colors"
                    >
                      {FREQ_OPTIONS.find((f) => f.value === schedule.frequency)?.label}
                      <ChevronDown className="w-3.5 h-3.5" />
                    </button>
                    {freqOpen && (
                      <div className="absolute top-full left-0 mt-1 py-1 bg-background border border-border rounded-xl shadow-lg z-20 min-w-[120px]">
                        {FREQ_OPTIONS.map((f) => (
                          <button
                            key={f.value}
                            onClick={() => { updateSchedule({ frequency: f.value }); setFreqOpen(false); }}
                            className={`w-full text-left px-3 py-1.5 text-sm transition-colors ${
                              schedule.frequency === f.value ? "text-primary font-medium bg-primary/5" : "text-foreground hover:bg-muted"
                            }`}
                          >
                            {f.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Interval */}
                  {schedule.frequency === "interval" && (
                    <>
                      <select
                        value={schedule.intervalValue}
                        onChange={(e) => updateSchedule({ intervalValue: parseInt(e.target.value) })}
                        className="appearance-none px-2.5 py-2 rounded-xl bg-muted/60 border border-border text-sm font-medium text-foreground outline-none focus:border-primary/40 transition-colors cursor-pointer"
                      >
                        {INTERVAL_OPTIONS.map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                      <span className="text-sm text-muted-foreground">小时执行</span>
                    </>
                  )}

                  {/* Time picker */}
                  {schedule.frequency !== "interval" && (
                    <>
                      <span className="text-sm text-muted-foreground">的</span>
                      <div className="flex items-center gap-1">
                        <select
                          value={schedule.hour}
                          onChange={(e) => updateSchedule({ hour: parseInt(e.target.value) })}
                          className="appearance-none px-2.5 py-2 rounded-xl bg-muted/60 border border-border text-sm font-mono text-foreground outline-none focus:border-primary/40 transition-colors cursor-pointer"
                        >
                          {Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{String(i).padStart(2, "0")}</option>)}
                        </select>
                        <span className="text-sm font-medium text-muted-foreground">:</span>
                        <select
                          value={schedule.minute}
                          onChange={(e) => updateSchedule({ minute: parseInt(e.target.value) })}
                          className="appearance-none px-2.5 py-2 rounded-xl bg-muted/60 border border-border text-sm font-mono text-foreground outline-none focus:border-primary/40 transition-colors cursor-pointer"
                        >
                          {Array.from({ length: 12 }, (_, i) => i * 5).map((m) => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}
                        </select>
                      </div>
                      <span className="text-sm text-muted-foreground">执行</span>
                    </>
                  )}
                </div>

                {/* Weekly pills */}
                {schedule.frequency === "weekly" && (
                  <div className="flex items-center gap-1.5">
                    {WEEK_LABELS.map((label, i) => (
                      <button
                        key={i}
                        onClick={() => toggleWeekday(i)}
                        className={`w-9 h-9 rounded-full text-xs font-medium transition-all ${
                          schedule.weekdays.includes(i)
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "bg-muted/60 text-muted-foreground hover:bg-muted"
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Monthly grid */}
                {schedule.frequency === "monthly" && (
                  <div className="space-y-2">
                    <span className="text-xs text-muted-foreground">选择日期</span>
                    <div className="grid grid-cols-7 gap-1">
                      {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                        <button
                          key={d}
                          onClick={() => updateSchedule({ monthDay: d })}
                          className={`h-8 rounded-lg text-xs font-medium transition-all ${
                            schedule.monthDay === d
                              ? "bg-primary text-primary-foreground shadow-sm"
                              : "bg-muted/40 text-muted-foreground hover:bg-muted"
                          }`}
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="border-t border-border" />

              {/* Task template */}
              <div className="space-y-3">
                <span className="text-[11px] text-muted-foreground font-medium uppercase tracking-wider">触发时创建的任务</span>

                <input
                  value={cronTaskTitle}
                  onChange={(e) => setCronTaskTitle(e.target.value)}
                  placeholder="任务标题"
                  className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm font-medium text-foreground outline-none focus:border-primary/40 transition-colors placeholder:text-muted-foreground/50"
                />

                <textarea
                  value={cronTaskDescription}
                  onChange={(e) => setCronTaskDescription(e.target.value)}
                  placeholder="任务描述（可选）"
                  rows={2}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors resize-none placeholder:text-muted-foreground/50 leading-relaxed"
                />

                {/* Category */}
                <div className="space-y-2">
                  <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1">
                    <Tag className="w-3 h-3" />分类
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {CATEGORIES.map((cat) => (
                      <button
                        key={cat.id}
                        onClick={() => setCronCategory(cat.id)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                          cronCategory === cat.id
                            ? "bg-foreground text-background shadow-sm"
                            : "bg-muted/60 text-muted-foreground hover:bg-muted"
                        }`}
                      >
                        <span className={`w-2 h-2 rounded-full ${cat.color}`} />
                        {cat.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Priority */}
                <div className="space-y-2">
                  <span className="text-[11px] text-muted-foreground font-medium">优先级</span>
                  <div className="flex gap-2">
                    {PRIORITY_OPTIONS.map((p) => (
                      <button
                        key={p.value}
                        onClick={() => setCronTaskPriority(p.value)}
                        className={`flex-1 py-2 rounded-xl text-xs font-medium border transition-all ${
                          cronTaskPriority === p.value ? p.active + " shadow-sm" : "bg-transparent border-border text-muted-foreground hover:bg-muted/40"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-border">
          <button
            onClick={handleClose}
            className="px-4 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            disabled={!canSave || saving}
            className="px-5 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? "创建中..." : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
