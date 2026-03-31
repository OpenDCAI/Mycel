import { useState, useEffect, useMemo } from "react";
import { X, ChevronDown, Tag } from "lucide-react";
import type { CronJob, Priority } from "@/store/types";

// ── Types ──────────────────────────────────────────────────

type Frequency = "interval" | "daily" | "weekdays" | "weekly" | "monthly";

interface ScheduleState {
  frequency: Frequency;
  hour: number;
  minute: number;
  weekdays: number[];   // 0=Sun ... 6=Sat
  monthDay: number;     // 1-31
  intervalValue: number; // for "every N hours"
}

interface TaskTemplate {
  title: string;
  description: string;
  priority: Priority;
  category: string;
}

// ── Constants ──────────────────────────────────────────────

const WEEK_LABELS = ["日", "一", "二", "三", "四", "五", "六"];

const INTERVAL_OPTIONS = [1, 2, 3, 4, 6, 8, 12];

const CATEGORIES = [
  { id: "code-review", label: "代码审查", color: "bg-blue-500" },
  { id: "report", label: "日报周报", color: "bg-emerald-500" },
  { id: "backup", label: "数据备份", color: "bg-amber-500" },
  { id: "security", label: "安全检查", color: "bg-red-500" },
  { id: "cleanup", label: "清理维护", color: "bg-violet-500" },
  { id: "monitoring", label: "监控巡检", color: "bg-cyan-500" },
  { id: "other", label: "其他", color: "bg-gray-400" },
];

const PRIORITY_OPTIONS: { value: Priority; label: string; className: string }[] = [
  { value: "high", label: "高", className: "bg-destructive/10 text-destructive border-destructive/20" },
  { value: "medium", label: "中", className: "bg-warning/10 text-warning border-warning/20" },
  { value: "low", label: "低", className: "bg-muted text-muted-foreground border-border" },
];

const FREQ_OPTIONS: { value: Frequency; label: string }[] = [
  { value: "interval", label: "每隔" },
  { value: "daily", label: "每天" },
  { value: "weekdays", label: "工作日" },
  { value: "weekly", label: "每周" },
  { value: "monthly", label: "每月" },
];

// ── Helpers ────────────────────────────────────────────────

function parseSchedule(expr: string): ScheduleState {
  const parts = expr.split(" ");
  const defaults: ScheduleState = { frequency: "daily", hour: 9, minute: 0, weekdays: [1], monthDay: 1, intervalValue: 2 };
  if (parts.length !== 5) return defaults;

  const [min, hour, dom, , dow] = parts;

  // interval: 0 */2 * * *
  if (hour.startsWith("*/") && dom === "*" && dow === "*") {
    return { ...defaults, frequency: "interval", intervalValue: parseInt(hour.slice(2)) || 2, minute: parseInt(min) || 0 };
  }

  const h = parseInt(hour) || 9;
  const m = parseInt(min) || 0;

  // weekdays: 0 9 * * 1-5
  if (dom === "*" && dow === "1-5") return { ...defaults, frequency: "weekdays", hour: h, minute: m };
  // weekly: 0 9 * * 1,3,5
  if (dom === "*" && dow !== "*") {
    const days = dow.split(",").map(Number).filter((n) => !isNaN(n));
    return { ...defaults, frequency: "weekly", hour: h, minute: m, weekdays: days.length ? days : [1] };
  }
  // monthly: 0 9 1 * *
  if (dom !== "*" && dow === "*") return { ...defaults, frequency: "monthly", hour: h, minute: m, monthDay: parseInt(dom) || 1 };
  // daily: 0 9 * * *  (or any other * * pattern)
  return { ...defaults, frequency: "daily", hour: h, minute: m };
}

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

function parseTaskTemplate(json: string): TaskTemplate {
  try {
    const obj = JSON.parse(json);
    return {
      title: obj.title || "",
      description: obj.description || "",
      priority: obj.priority || "medium",
      category: obj.category || "other",
    };
  } catch {
    return { title: "", description: "", priority: "medium", category: "other" };
  }
}

function buildTaskTemplate(t: TaskTemplate): string {
  return JSON.stringify({ title: t.title, description: t.description, priority: t.priority, category: t.category });
}

// ── Component ──────────────────────────────────────────────

interface CronEditorProps {
  cronForm: CronJob;
  isMobile: boolean;
  onUpdate: (form: CronJob) => void;
  onSave: () => void;
  onClose: () => void;
  onDelete: () => void;
}

export default function CronEditor({ cronForm, isMobile, onUpdate, onSave, onClose, onDelete }: CronEditorProps) {
  const [schedule, setSchedule] = useState<ScheduleState>(() => parseSchedule(cronForm.cron_expression));
  const [template, setTemplate] = useState<TaskTemplate>(() => parseTaskTemplate(cronForm.task_template));
  const [freqOpen, setFreqOpen] = useState(false);

  // Sync schedule/template changes back to cronForm
  useEffect(() => {
    const expr = buildCron(schedule);
    const tmpl = buildTaskTemplate(template);
    if (expr !== cronForm.cron_expression || tmpl !== cronForm.task_template) {
      onUpdate({ ...cronForm, cron_expression: expr, task_template: tmpl });
    }
  }, [schedule, template]);

  // Reset when cronForm.id changes (switching between cron jobs)
  useEffect(() => {
    setSchedule(parseSchedule(cronForm.cron_expression));
    setTemplate(parseTaskTemplate(cronForm.task_template));
  }, [cronForm.id]);

  const humanSchedule = useMemo(() => scheduleToHuman(schedule), [schedule]);

  const updateSchedule = (patch: Partial<ScheduleState>) => setSchedule((s) => ({ ...s, ...patch }));
  const updateTemplate = (patch: Partial<TaskTemplate>) => setTemplate((t) => ({ ...t, ...patch }));

  const toggleWeekday = (day: number) => {
    setSchedule((s) => {
      const has = s.weekdays.includes(day);
      const next = has ? s.weekdays.filter((d) => d !== day) : [...s.weekdays, day];
      return { ...s, weekdays: next.length ? next : [day] };
    });
  };

  const needsTimePicker = schedule.frequency !== "interval";

  // ── Render ─────────────────────────────────────────────

  return (
    <div className={`${isMobile ? "fixed inset-0 z-50 flex" : "w-[380px] shrink-0 border-l border-border"} bg-background flex flex-col`}>
      {isMobile && <div className="fixed inset-0 bg-black/50 -z-10" onClick={onClose} />}

      {/* Header */}
      <div className="h-14 flex items-center justify-between px-5 border-b border-border shrink-0">
        <h3 className="text-sm font-semibold text-foreground">编辑定时任务</h3>
        <div className="flex items-center gap-1.5">
          <button onClick={onSave} className="px-3.5 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity duration-fast">
            保存
          </button>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors duration-fast">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* ── Section 1: Identity ── */}
        <div className="px-5 pt-5 pb-4 space-y-3">
          <input
            value={cronForm.name}
            onChange={(e) => onUpdate({ ...cronForm, name: e.target.value })}
            placeholder="任务名称"
            className="w-full text-lg font-semibold text-foreground bg-transparent outline-none placeholder:text-muted-foreground/50"
          />
          <textarea
            value={cronForm.description}
            onChange={(e) => onUpdate({ ...cronForm, description: e.target.value })}
            placeholder="添加描述..."
            rows={2}
            className="w-full text-sm text-muted-foreground bg-transparent outline-none placeholder:text-muted-foreground/40 resize-none leading-relaxed"
          />
        </div>

        <div className="mx-5 border-t border-border" />

        {/* ── Section 2: Schedule ── */}
        <div className="px-5 py-4 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">调度</span>
            <span className="text-xs text-primary font-medium">{humanSchedule}</span>
          </div>

          {/* Sentence builder */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Frequency dropdown */}
            <div className="relative">
              <button
                onClick={() => setFreqOpen(!freqOpen)}
                className="flex items-center gap-1 px-3 py-2 rounded-xl bg-primary/8 border border-primary/15 text-sm font-medium text-primary hover:bg-primary/12 transition-colors duration-fast"
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
                      className={`w-full text-left px-3 py-1.5 text-sm transition-colors duration-fast ${
                        schedule.frequency === f.value ? "text-primary font-medium bg-primary/5" : "text-foreground hover:bg-muted"
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Interval: "每隔 [N] 小时 执行" */}
            {schedule.frequency === "interval" && (
              <>
                <select
                  value={schedule.intervalValue}
                  onChange={(e) => updateSchedule({ intervalValue: parseInt(e.target.value) })}
                  className="appearance-none px-2.5 py-2 rounded-xl bg-muted/60 border border-border text-sm font-medium text-foreground outline-none focus:border-primary/40 transition-colors duration-fast cursor-pointer"
                >
                  {INTERVAL_OPTIONS.map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
                <span className="text-sm text-muted-foreground">小时执行</span>
              </>
            )}

            {/* Fixed time: "的 HH:MM 执行" */}
            {needsTimePicker && (
              <>
                <span className="text-sm text-muted-foreground">的</span>
                <div className="flex items-center gap-1">
                  <select
                    value={schedule.hour}
                    onChange={(e) => updateSchedule({ hour: parseInt(e.target.value) })}
                    className="appearance-none px-2.5 py-2 rounded-xl bg-muted/60 border border-border text-sm font-mono text-foreground outline-none focus:border-primary/40 transition-colors duration-fast cursor-pointer"
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{String(i).padStart(2, "0")}</option>
                    ))}
                  </select>
                  <span className="text-sm font-medium text-muted-foreground">:</span>
                  <select
                    value={schedule.minute}
                    onChange={(e) => updateSchedule({ minute: parseInt(e.target.value) })}
                    className="appearance-none px-2.5 py-2 rounded-xl bg-muted/60 border border-border text-sm font-mono text-foreground outline-none focus:border-primary/40 transition-colors duration-fast cursor-pointer"
                  >
                    {Array.from({ length: 12 }, (_, i) => i * 5).map((m) => (
                      <option key={m} value={m}>{String(m).padStart(2, "0")}</option>
                    ))}
                  </select>
                </div>
                <span className="text-sm text-muted-foreground">执行</span>
              </>
            )}
          </div>

          {/* Weekly: day pills */}
          {schedule.frequency === "weekly" && (
            <div className="flex items-center gap-1.5">
              {WEEK_LABELS.map((label, i) => (
                <button
                  key={i}
                  onClick={() => toggleWeekday(i)}
                  className={`w-9 h-9 rounded-full text-xs font-medium transition-all duration-fast ${
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

          {/* Monthly: day picker */}
          {schedule.frequency === "monthly" && (
            <div className="space-y-2">
              <span className="text-xs text-muted-foreground">选择日期</span>
              <div className="grid grid-cols-7 gap-1">
                {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                  <button
                    key={d}
                    onClick={() => updateSchedule({ monthDay: d })}
                    className={`h-8 rounded-lg text-xs font-medium transition-all duration-fast ${
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

        <div className="mx-5 border-t border-border" />

        {/* ── Section 3: Task preview ── */}
        <div className="px-5 py-4 space-y-4">
          <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">到时候创建的任务</span>

          <input
            value={template.title}
            onChange={(e) => updateTemplate({ title: e.target.value })}
            placeholder="任务标题"
            className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm font-medium text-foreground outline-none focus:border-primary/40 transition-colors duration-fast placeholder:text-muted-foreground/50"
          />

          <textarea
            value={template.description}
            onChange={(e) => updateTemplate({ description: e.target.value })}
            placeholder="任务描述（可选）"
            rows={2}
            className="w-full px-3.5 py-2.5 rounded-xl bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors duration-fast resize-none placeholder:text-muted-foreground/50 leading-relaxed"
          />

          {/* Category tags */}
          <div className="space-y-2">
            <span className="text-xs text-muted-foreground font-medium flex items-center gap-1">
              <Tag className="w-3 h-3" />分类
            </span>
            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.id}
                  onClick={() => updateTemplate({ category: cat.id })}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-fast ${
                    template.category === cat.id
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
            <span className="text-xs text-muted-foreground font-medium">优先级</span>
            <div className="flex gap-2">
              {PRIORITY_OPTIONS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => updateTemplate({ priority: p.value })}
                  className={`flex-1 py-2 rounded-xl text-xs font-medium border transition-all duration-fast ${
                    template.priority === p.value
                      ? p.className + " shadow-sm"
                      : "bg-transparent border-border text-muted-foreground hover:bg-muted/40"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mx-5 border-t border-border" />

        {/* ── Section 4: Toggle + Danger ── */}
        <div className="px-5 py-4 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-foreground font-medium">启用调度</span>
            <button
              onClick={() => onUpdate({ ...cronForm, enabled: cronForm.enabled ? 0 : 1 })}
              className={`relative w-11 h-6 rounded-full transition-colors duration-fast ${cronForm.enabled ? "bg-primary" : "bg-muted"}`}
            >
              <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-background shadow-sm transition-transform duration-fast ${cronForm.enabled ? "left-[22px]" : "left-0.5"}`} />
            </button>
          </div>

          <button
            onClick={onDelete}
            className="w-full px-3 py-2.5 rounded-xl text-destructive text-xs font-medium hover:bg-destructive/5 transition-colors duration-fast"
          >
            删除定时任务
          </button>
        </div>
      </div>
    </div>
  );
}
