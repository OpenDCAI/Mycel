import { useState, useEffect } from "react";
import {
  Search, CheckCircle2, Circle, Clock, AlertCircle,
  ListTodo, ArrowUpDown, ChevronDown, ChevronUp, LayoutGrid, List,
  Plus, X, Calendar, User, AlertTriangle, RefreshCw, ExternalLink,
  Play, Trash2, Timer,
} from "lucide-react";
import { useIsMobile } from "@/hooks/use-mobile";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAppStore } from "@/store/app-store";
import type { Task, TaskStatus, Priority, CronJob } from "@/store/types";

const statusConfig: Record<TaskStatus, { label: string; icon: typeof Circle; color: string }> = {
  pending: { label: "等待中", icon: Circle, color: "text-muted-foreground" },
  running: { label: "执行中", icon: Clock, color: "text-primary" },
  completed: { label: "已完成", icon: CheckCircle2, color: "text-success" },
  failed: { label: "失败", icon: AlertCircle, color: "text-destructive" },
};

const priorityConfig: Record<Priority, { label: string; className: string }> = {
  high: { label: "高", className: "bg-destructive/10 text-destructive" },
  medium: { label: "中", className: "bg-warning/10 text-warning" },
  low: { label: "低", className: "bg-muted text-muted-foreground" },
};
const sourceLabel: Record<string, string> = {
  manual: "手动",
  cron: "定时",
  agent: "Agent",
  queue: "队列",
};
type SortField = "title" | "priority" | "created_at" | null;
type SortDir = "asc" | "desc";
type ViewMode = "table" | "board";
type ActiveTab = "tasks" | "cron";

function cronToHuman(expr: string): string {
  const parts = expr.split(" ");
  if (parts.length !== 5) return expr;
  const [min, hour, dom, mon, dow] = parts;
  if (min === "0" && hour !== "*" && dom === "*" && mon === "*" && dow === "*")
    return `每天 ${hour}:00`;
  if (min !== "*" && hour !== "*" && dom === "*" && mon === "*" && dow === "*")
    return `每天 ${hour}:${min.padStart(2, "0")}`;
  if (dom === "*" && mon === "*" && dow !== "*")
    return `每周${["日","一","二","三","四","五","六"][parseInt(dow)] || dow} ${hour}:${min.padStart(2, "0")}`;
  return expr;
}

export default function Tasks() {
  const isMobile = useIsMobile();
  const tasks = useAppStore((s) => s.taskList);
  const memberList = useAppStore((s) => s.memberList);
  const loadAll = useAppStore((s) => s.loadAll);
  const error = useAppStore((s) => s.error);
  const retry = useAppStore((s) => s.retry);
  const storeAddTask = useAppStore((s) => s.addTask);
  const storeUpdateTask = useAppStore((s) => s.updateTask);
  const storeDeleteTask = useAppStore((s) => s.deleteTask);
  const storeBulkUpdate = useAppStore((s) => s.bulkUpdateTaskStatus);
  const cronJobs = useAppStore((s) => s.cronJobs);
  const storeAddCronJob = useAppStore((s) => s.addCronJob);
  const storeUpdateCronJob = useAppStore((s) => s.updateCronJob);
  const storeDeleteCronJob = useAppStore((s) => s.deleteCronJob);
  const storeTriggerCronJob = useAppStore((s) => s.triggerCronJob);

  const fetchTasks = useAppStore((s) => s.fetchTasks);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchTasks();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all");
  const [priorityFilter, setPriorityFilter] = useState<Priority | "all">("all");
  const [sortField, setSortField] = useState<SortField>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>(isMobile ? "table" : "table");
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("tasks");

  // Editing state for the panel
  const [editForm, setEditForm] = useState<Task | null>(null);

  // Cron editing state
  const [editingCron, setEditingCron] = useState<CronJob | null>(null);
  const [cronForm, setCronForm] = useState<CronJob | null>(null);
  const [deleteCronConfirmId, setDeleteCronConfirmId] = useState<string | null>(null);

  // Helper: resolve assignee name/avatar from memberList
  const getAssigneeInfo = (assigneeId: string) => {
    const member = memberList.find((s) => s.id === assigneeId);
    const name = member?.name || "";
    const avatar = name.split(" ").map((w) => w[0]).join("").slice(0, 2);
    return { name, avatar };
  };

  const openEdit = (task: Task) => {
    setEditingTask(task);
    setEditForm({ ...task });
  };

  const closeEdit = () => {
    setEditingTask(null);
    setEditForm(null);
  };

  const saveEdit = async () => {
    if (!editForm) return;
    try {
      await storeUpdateTask(editForm.id, editForm);
      setEditingTask(editForm);
      toast.success("任务已保存");
    } catch (e: unknown) {
      toast.error("保存失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const confirmDelete = (id: string) => setDeleteConfirmId(id);
  const executeDelete = async () => {
    if (!deleteConfirmId) return;
    try {
      await storeDeleteTask(deleteConfirmId);
      if (editingTask?.id === deleteConfirmId) closeEdit();
      toast.success("任务已删除");
      setDeleteConfirmId(null);
    } catch (e: unknown) {
      toast.error("删除失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const createTask = async () => {
    try {
      const newTask = await storeAddTask();
      openEdit(newTask);
    } catch (e: unknown) {
      toast.error("创建失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };
  // Cron helpers
  const openCronEdit = (cron: CronJob) => {
    setEditingCron(cron);
    setCronForm({ ...cron });
  };

  const closeCronEdit = () => {
    setEditingCron(null);
    setCronForm(null);
  };

  const saveCronEdit = async () => {
    if (!cronForm) return;
    try {
      await storeUpdateCronJob(cronForm.id, cronForm);
      setEditingCron(cronForm);
      toast.success("定时任务已保存");
    } catch (e: unknown) {
      toast.error("保存失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const createCronJob = async () => {
    try {
      const newCron = await storeAddCronJob({ name: "新定时任务", cron_expression: "0 9 * * *" });
      openCronEdit(newCron);
    } catch (e: unknown) {
      toast.error("创建失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const executeCronDelete = async () => {
    if (!deleteCronConfirmId) return;
    try {
      await storeDeleteCronJob(deleteCronConfirmId);
      if (editingCron?.id === deleteCronConfirmId) closeCronEdit();
      toast.success("定时任务已删除");
      setDeleteCronConfirmId(null);
    } catch (e: unknown) {
      toast.error("删除失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleTriggerCron = async (id: string) => {
    try {
      await storeTriggerCronJob(id);
      toast.success("已触发执行");
    } catch (e: unknown) {
      toast.error("触发失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  let filtered = tasks.filter((t) => {
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
    if (search) {
      const { name } = getAssigneeInfo(t.assignee_id);
      if (!t.title.toLowerCase().includes(search.toLowerCase()) && !name.toLowerCase().includes(search.toLowerCase())) return false;
    }
    return true;
  });

  if (sortField) {
    filtered = [...filtered].sort((a, b) => {
      let cmp = 0;
      if (sortField === "title") cmp = a.title.localeCompare(b.title);
      else if (sortField === "priority") {
        const order = { high: 0, medium: 1, low: 2 };
        cmp = order[a.priority] - order[b.priority];
      } else if (sortField === "created_at") cmp = a.created_at - b.created_at;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }

  const stats = {
    running: tasks.filter((t) => t.status === "running").length,
    pending: tasks.filter((t) => t.status === "pending").length,
    completed: tasks.filter((t) => t.status === "completed").length,
    failed: tasks.filter((t) => t.status === "failed").length,
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortField(field); setSortDir("asc"); }
  };

  const toggleSelectAll = () => {
    if (selectedRows.size === filtered.length) setSelectedRows(new Set());
    else setSelectedRows(new Set(filtered.map((t) => t.id)));
  };

  const toggleSelectRow = (id: string) => {
    setSelectedRows((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 ml-1 opacity-40" />;
    return sortDir === "asc" ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />;
  };

  const handleDragStart = (e: React.DragEvent, taskId: string) => {
    e.dataTransfer.setData("taskId", taskId);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent, status: TaskStatus) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverColumn(status);
  };

  const handleDragLeave = () => setDragOverColumn(null);

  const handleDrop = async (e: React.DragEvent, newStatus: TaskStatus) => {
    e.preventDefault();
    const taskId = e.dataTransfer.getData("taskId");
    try {
      await storeUpdateTask(taskId, { status: newStatus, progress: newStatus === "completed" ? 100 : newStatus === "pending" ? 0 : undefined });
    } catch (err: unknown) {
      toast.error("更新失败: " + (err instanceof Error ? err.message : String(err)));
    }
    setDragOverColumn(null);
  };

  const kanbanColumns: TaskStatus[] = ["pending", "running", "completed", "failed"];
  // Stats bar
  const statsBar = (
    <div className="flex items-center gap-3 px-4 md:px-6 py-2 border-b border-border shrink-0">
      {([
        { key: "running" as const, label: "执行中", color: "text-primary" },
        { key: "pending" as const, label: "等待", color: "text-muted-foreground" },
        { key: "completed" as const, label: "完成", color: "text-success" },
        { key: "failed" as const, label: "失败", color: "text-destructive" },
      ]).map((s) => (
        <div key={s.key} className="flex items-center gap-1.5 text-xs">
          <span className={`font-mono font-semibold ${s.color}`}>{stats[s.key]}</span>
          <span className="text-muted-foreground">{s.label}</span>
        </div>
      ))}
    </div>
  );

  // Edit panel
  const editPanel = editForm && (
    <div className={`${isMobile ? "fixed inset-0 z-50 flex" : "w-[360px] shrink-0 border-l border-border"} bg-background flex flex-col`}>
      {isMobile && <div className="fixed inset-0 bg-black/50 -z-10" onClick={closeEdit} />}
      <div className="h-14 flex items-center justify-between px-4 border-b border-border shrink-0">
        <h3 className="text-sm font-semibold text-foreground">编辑任务</h3>
        <div className="flex items-center gap-1">
          <button onClick={saveEdit} className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
            保存
          </button>
          <button onClick={closeEdit} className="p-1.5 rounded-md hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Title */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">标题</label>
          <input
            value={editForm.title}
            onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors"
          />
        </div>
        {/* Description */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">描述</label>
          <textarea
            value={editForm.description}
            onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors resize-none"
          />
        </div>
        {/* Status */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">状态</label>
          <div className="flex flex-wrap gap-1.5">
            {(["pending", "running", "completed", "failed"] as const).map((s) => {
              const config = statusConfig[s];
              const StatusIcon = config.icon;
              return (
                <button
                  key={s}
                  onClick={() => setEditForm({ ...editForm, status: s, progress: s === "completed" ? 100 : s === "pending" ? 0 : editForm.progress })}
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs transition-colors ${
                    editForm.status === s ? "bg-primary/10 text-primary font-medium border border-primary/20" : "bg-card border border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <StatusIcon className="w-3 h-3" />
                  {config.label}
                </button>
              );
            })}
          </div>
        </div>
        {/* Priority */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">优先级</label>
          <div className="flex gap-1.5">
            {(["high", "medium", "low"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setEditForm({ ...editForm, priority: p })}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  editForm.priority === p ? priorityConfig[p].className + " ring-1 ring-current/20" : "bg-card border border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {priorityConfig[p].label}
              </button>
            ))}
          </div>
        </div>
        {/* Assignee */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">
            <User className="w-3 h-3 inline mr-1" />执行者
          </label>
          <select
            value={editForm.assignee_id}
            onChange={(e) => {
              setEditForm({ ...editForm, assignee_id: e.target.value });
            }}
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors"
          >
            <option value="">未分配</option>
            {memberList.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
        {/* Deadline */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">
            <Calendar className="w-3 h-3 inline mr-1" />截止日期
          </label>
          <input
            type="date"
            value={editForm.deadline}
            onChange={(e) => setEditForm({ ...editForm, deadline: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors"
          />
        </div>
        {/* Progress (only for running) */}
        {editForm.status === "running" && (
          <div>
            <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">进度</label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0}
                max={100}
                value={editForm.progress}
                onChange={(e) => setEditForm({ ...editForm, progress: Number(e.target.value) })}
                className="flex-1 accent-primary"
              />
              <span className="text-xs font-mono text-primary w-10 text-right">{editForm.progress}%</span>
            </div>
          </div>
        )}

        {/* Result preview */}
        {editForm.result && (
          <div>
            <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">执行结果</label>
            <p className="text-sm p-2 bg-muted rounded whitespace-pre-wrap">{editForm.result}</p>
          </div>
        )}

        {/* Danger zone */}
        <div className="pt-4 border-t border-border">
          <button
            onClick={() => confirmDelete(editForm.id)}
            className="w-full px-3 py-2 rounded-lg border border-destructive/20 text-destructive text-xs font-medium hover:bg-destructive/5 transition-colors"
          >
            删除任务
          </button>
        </div>
      </div>
    </div>
  );

  // Cron edit panel
  const cronEditPanel = cronForm && (
    <div className={`${isMobile ? "fixed inset-0 z-50 flex" : "w-[360px] shrink-0 border-l border-border"} bg-background flex flex-col`}>
      {isMobile && <div className="fixed inset-0 bg-black/50 -z-10" onClick={closeCronEdit} />}
      <div className="h-14 flex items-center justify-between px-4 border-b border-border shrink-0">
        <h3 className="text-sm font-semibold text-foreground">编辑定时任务</h3>
        <div className="flex items-center gap-1">
          <button onClick={saveCronEdit} className="px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
            保存
          </button>
          <button onClick={closeCronEdit} className="p-1.5 rounded-md hover:bg-muted transition-colors">
            <X className="w-4 h-4 text-muted-foreground" />
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Name */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">名称</label>
          <input
            value={cronForm.name}
            onChange={(e) => setCronForm({ ...cronForm, name: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors"
          />
        </div>
        {/* Description */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">描述</label>
          <textarea
            value={cronForm.description}
            onChange={(e) => setCronForm({ ...cronForm, description: e.target.value })}
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground outline-none focus:border-primary/40 transition-colors resize-none"
          />
        </div>
        {/* Cron expression */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">
            <Timer className="w-3 h-3 inline mr-1" />Cron 表达式
          </label>
          <input
            value={cronForm.cron_expression}
            onChange={(e) => setCronForm({ ...cronForm, cron_expression: e.target.value })}
            placeholder="0 9 * * *"
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground font-mono outline-none focus:border-primary/40 transition-colors"
          />
          {cronForm.cron_expression && (
            <p className="text-[11px] text-muted-foreground mt-1">{cronToHuman(cronForm.cron_expression)}</p>
          )}
        </div>
        {/* Task template */}
        <div>
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mb-1.5 block">任务模板 (JSON)</label>
          <textarea
            value={cronForm.task_template}
            onChange={(e) => setCronForm({ ...cronForm, task_template: e.target.value })}
            rows={5}
            placeholder='{"title": "日报", "priority": "medium"}'
            className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground font-mono outline-none focus:border-primary/40 transition-colors resize-none"
          />
        </div>
        {/* Enabled toggle */}
        <div className="flex items-center justify-between">
          <label className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium">启用</label>
          <button
            onClick={() => setCronForm({ ...cronForm, enabled: cronForm.enabled ? 0 : 1 })}
            className={`relative w-9 h-5 rounded-full transition-colors ${cronForm.enabled ? "bg-primary" : "bg-muted"}`}
          >
            <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${cronForm.enabled ? "left-[18px]" : "left-0.5"}`} />
          </button>
        </div>
        {/* Danger zone */}
        <div className="pt-4 border-t border-border">
          <button
            onClick={() => setDeleteCronConfirmId(cronForm.id)}
            className="w-full px-3 py-2 rounded-lg border border-destructive/20 text-destructive text-xs font-medium hover:bg-destructive/5 transition-colors"
          >
            删除定时任务
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full">
      {/* Main content */}
      <div className="flex-1 flex flex-col bg-background overflow-hidden">
        {/* Top bar */}
        <div className={`h-14 flex items-center justify-between ${isMobile ? "px-3" : "px-6"} border-b border-border shrink-0`}>
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-foreground">任务</h2>
            <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
              <button
                className={`px-3 py-1 rounded text-sm ${activeTab === "tasks" ? "bg-background shadow-sm" : "text-muted-foreground"}`}
                onClick={() => setActiveTab("tasks")}
              >
                任务看板
              </button>
              <button
                className={`px-3 py-1 rounded text-sm ${activeTab === "cron" ? "bg-background shadow-sm" : "text-muted-foreground"}`}
                onClick={() => setActiveTab("cron")}
              >
                定时任务
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {activeTab === "tasks" ? (
              <>
                <div className="flex items-center border border-border rounded-md overflow-hidden">
                  <button
                    onClick={() => setViewMode("table")}
                    className={`p-1.5 transition-colors ${viewMode === "table" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
                    title="表格视图"
                  >
                    <List className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => setViewMode("board")}
                    className={`p-1.5 transition-colors ${viewMode === "board" ? "bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}
                    title="看板视图"
                  >
                    <LayoutGrid className="w-3.5 h-3.5" />
                  </button>
                </div>
                <button onClick={createTask} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
                  <Plus className="w-4 h-4" />
                  <span className="hidden md:inline">新建任务</span>
                </button>
              </>
            ) : (
              <button onClick={createCronJob} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
                <Plus className="w-4 h-4" />
                <span className="hidden md:inline">新建定时任务</span>
              </button>
            )}
          </div>
        </div>
        {/* Filters (tasks tab only) */}
        {activeTab === "tasks" && (<>
        {/* Filters */}
        <div className={`flex items-center gap-2 px-4 md:px-6 py-2.5 border-b border-border overflow-x-auto shrink-0`}>
          <div className="flex items-center gap-1">
            {(["all", "running", "pending", "completed", "failed"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-2 py-1 rounded-md text-xs transition-colors whitespace-nowrap shrink-0 ${
                  statusFilter === s ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                {s === "all" ? "全部" : statusConfig[s].label}
                <span className="ml-1 font-mono">{s === "all" ? tasks.length : stats[s as TaskStatus]}</span>
              </button>
            ))}
          </div>

          {!isMobile && (
            <>
              <div className="w-px h-5 bg-border" />
              {(["all", "high", "medium", "low"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPriorityFilter(p)}
                  className={`px-2 py-1 rounded-md text-xs transition-colors whitespace-nowrap shrink-0 ${
                    priorityFilter === p ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  }`}
                >
                  {p === "all" ? "优先级" : priorityConfig[p].label}
                </button>
              ))}
              <div className="flex-1" />
              <div className="relative w-52">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索任务..."
                  className="w-full pl-8 pr-3 py-1.5 rounded-md bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors"
                />
              </div>
            </>
          )}
        </div>

        {/* Stats */}
        {statsBar}

        {/* Bulk actions bar */}
        {selectedRows.size > 0 && (
          <div className="flex items-center gap-3 px-6 py-2 bg-primary/5 border-b border-primary/15 text-xs shrink-0">
            <span className="text-primary font-medium">已选择 {selectedRows.size} 项</span>
            <button onClick={async () => { try { await storeBulkUpdate([...selectedRows], "pending"); setSelectedRows(new Set()); } catch (e: unknown) { toast.error("操作失败: " + (e instanceof Error ? e.message : String(e))); } }} className="px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors">批量取消</button>
            <button onClick={async () => { try { await storeBulkUpdate([...selectedRows], "running"); setSelectedRows(new Set()); } catch (e: unknown) { toast.error("操作失败: " + (e instanceof Error ? e.message : String(e))); } }} className="px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors">批量重试</button>
            <button onClick={() => setSelectedRows(new Set())} className="ml-auto text-muted-foreground hover:text-foreground transition-colors">清除选择</button>
          </div>
        )}
        {/* Content area */}
        <div className="flex-1 overflow-y-auto">
          {error ? (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
                <AlertTriangle className="w-6 h-6 text-destructive" />
              </div>
              <p className="text-sm font-medium text-foreground mb-1">加载失败</p>
              <p className="text-xs text-muted-foreground mb-4 max-w-xs text-center">{error}</p>
              <button onClick={retry} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
                <RefreshCw className="w-3.5 h-3.5" />重试
              </button>
            </div>
          ) : viewMode === "board" ? (
            <div className={`${isMobile ? "flex flex-col gap-4 p-3" : "flex gap-4 p-4 h-full overflow-x-auto"}`}>
              {kanbanColumns.map((status) => {
                const columnTasks = filtered.filter((t) => t.status === status);
                const config = statusConfig[status];
                const StatusIcon = config.icon;
                return (
                  <div
                    key={status}
                    className={`${isMobile ? "w-full" : "w-[280px] shrink-0"} flex flex-col rounded-lg border transition-colors ${
                      dragOverColumn === status ? "border-primary/40 bg-primary/5" : "border-border bg-card/50"
                    }`}
                    onDragOver={(e) => handleDragOver(e, status)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, status)}
                  >
                    <div className="flex items-center justify-between px-3 py-2.5 border-b border-border">
                      <div className="flex items-center gap-2">
                        <StatusIcon className={`w-3.5 h-3.5 ${config.color}`} />
                        <span className="text-xs font-medium text-foreground">{config.label}</span>
                      </div>
                      <span className="text-[11px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">{columnTasks.length}</span>
                    </div>
                    <div className={`flex-1 p-2 space-y-2 ${isMobile ? "" : "overflow-y-auto min-h-[200px]"}`}>
                      {columnTasks.length === 0 && (
                        <div className="text-center py-8 text-xs text-muted-foreground">拖拽任务到此列</div>
                      )}
                      {columnTasks.map((task) => {
                        const priority = priorityConfig[task.priority];
                        return (
                          <div
                            key={task.id}
                            draggable
                            onDragStart={(e) => handleDragStart(e, task.id)}
                            onClick={() => openEdit(task)}
                            className={`p-3 rounded-lg border bg-background cursor-pointer active:cursor-grabbing transition-all hover:shadow-sm ${
                              editingTask?.id === task.id ? "border-primary/40 shadow-sm" : "border-border hover:border-primary/30"
                            }`}
                          >
                            <div className="flex items-center gap-1 mb-2">
                              <p className="text-sm font-medium text-foreground leading-snug">{task.title}</p>
                              {task.source && task.source !== "manual" && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0">
                                  {sourceLabel[task.source] || task.source}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center justify-between">
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${priority.className}`}>
                                {priority.label}
                              </span>
                              <div className="flex items-center gap-1.5">
                                {task.assignee_id && (() => { const { name, avatar } = getAssigneeInfo(task.assignee_id); return name ? (
                                  <>
                                    <div className="w-5 h-5 rounded bg-primary/10 flex items-center justify-center">
                                      <span className="text-[8px] font-mono text-primary font-bold">{avatar}</span>
                                    </div>
                                    <span className="text-[10px] text-muted-foreground">{name}</span>
                                  </>
                                ) : null; })()}
                              </div>
                            </div>
                            {task.status === "running" && (
                              <div className="flex items-center gap-1.5 mt-2">
                                <div className="flex-1 h-1 rounded-full bg-muted overflow-hidden">
                                  <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${task.progress}%` }} />
                                </div>
                                <span className="text-[10px] font-mono text-primary">{task.progress}%</span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : isMobile ? (
            <div className="p-3 space-y-2">
              {filtered.length === 0 ? (
                <div className="flex items-center justify-center py-20">
                  <div className="text-center">
                    <ListTodo className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                    <p className="text-sm font-medium text-foreground mb-1">暂无任务</p>
                    <p className="text-xs text-muted-foreground mb-3">创建一个新任务开始工作</p>
                    <button onClick={createTask} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
                      <Plus className="w-3.5 h-3.5" />新建任务
                    </button>
                  </div>
                </div>
              ) : (
                filtered.map((task) => {
                  const status = statusConfig[task.status];
                  const priority = priorityConfig[task.priority];
                  const StatusIcon = status.icon;
                  return (
                    <div
                      key={task.id}
                      onClick={() => openEdit(task)}
                      className={`p-3 rounded-lg border bg-card cursor-pointer transition-colors ${
                        editingTask?.id === task.id ? "border-primary/40" : "border-border"
                      } ${task.status === "failed" ? "border-l-2 border-l-destructive bg-destructive/[0.03]" : ""}`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <StatusIcon className={`w-4 h-4 ${status.color} shrink-0`} />
                          <p className="text-sm font-medium text-foreground">{task.title}</p>
                        </div>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${priority.className}`}>{priority.label}</span>
                      </div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          {task.assignee_id && (() => { const { name, avatar } = getAssigneeInfo(task.assignee_id); return name ? (
                            <>
                              <div className="w-4 h-4 rounded bg-primary/10 flex items-center justify-center">
                                <span className="text-[7px] font-mono text-primary font-bold">{avatar}</span>
                              </div>
                              <span>{name}</span>
                            </>
                          ) : null; })()}
                        </div>
                        {task.status === "running" && (
                          <span className="font-mono text-primary">{task.progress}%</span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-[32px_32px_1fr_80px_160px_80px_60px] gap-2 px-6 py-2 border-b border-border text-[11px] text-muted-foreground uppercase tracking-wider font-medium sticky top-0 bg-background z-10">
                <span className="flex items-center">
                  <input type="checkbox" aria-label="全选任务" checked={selectedRows.size === filtered.length && filtered.length > 0} onChange={toggleSelectAll} className="w-3.5 h-3.5 accent-primary rounded" />
                </span>
                <span />
                <button onClick={() => handleSort("title")} className="flex items-center hover:text-foreground transition-colors text-left">任务 <SortIcon field="title" /></button>
                <button onClick={() => handleSort("priority")} className="flex items-center hover:text-foreground transition-colors">优先级 <SortIcon field="priority" /></button>
                <span>执行者</span>
                <span>进度</span>
                <button onClick={() => handleSort("created_at")} className="flex items-center hover:text-foreground transition-colors">时间 <SortIcon field="created_at" /></button>
              </div>

              {filtered.length === 0 ? (
                <div className="flex items-center justify-center py-20">
                  <div className="text-center">
                    <ListTodo className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                    <p className="text-sm font-medium text-foreground mb-1">暂无任务</p>
                    <p className="text-xs text-muted-foreground mb-3">创建一个新任务开始工作</p>
                    <button onClick={createTask} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
                      <Plus className="w-3.5 h-3.5" />新建任务
                    </button>
                  </div>
                </div>
              ) : (
                filtered.map((task) => {
                  const status = statusConfig[task.status];
                  const priority = priorityConfig[task.priority];
                  const StatusIcon = status.icon;
                  return (
                    <div
                      key={task.id}
                      onClick={() => openEdit(task)}
                      className={`grid grid-cols-[32px_32px_1fr_80px_160px_80px_60px] gap-2 px-6 py-3 border-b border-border hover:bg-muted/30 transition-colors cursor-pointer items-center ${
                        editingTask?.id === task.id ? "bg-primary/[0.03]" : ""
                      } ${task.status === "failed" ? "bg-destructive/[0.03] border-l-2 border-l-destructive" : ""}`}
                    >
                      <span className="flex items-center" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label={`选择任务: ${task.title}`} checked={selectedRows.has(task.id)} onChange={() => toggleSelectRow(task.id)} className="w-3.5 h-3.5 accent-primary rounded" />
                      </span>
                      <StatusIcon className={`w-4 h-4 ${status.color}`} />
                      <span className="text-sm font-medium text-foreground truncate flex items-center gap-1">
                        {task.title}
                        {task.source && task.source !== "manual" && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary ml-1 shrink-0">
                            {sourceLabel[task.source] || task.source}
                          </span>
                        )}
                        {task.thread_id && (
                          <a href={`/chat/${task.thread_id}`}
                             className="text-muted-foreground hover:text-primary ml-1 shrink-0"
                             onClick={(e) => e.stopPropagation()}>
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </span>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium w-fit ${priority.className}`}>{priority.label}</span>
                      <div className="flex items-center gap-2">
                        {task.assignee_id ? (() => { const { name, avatar } = getAssigneeInfo(task.assignee_id); return name ? (
                          <>
                            <div className="w-5 h-5 rounded bg-primary/10 flex items-center justify-center shrink-0">
                              <span className="text-[8px] font-mono text-primary font-bold">{avatar}</span>
                            </div>
                            <span className="text-xs text-muted-foreground truncate">{name}</span>
                          </>
                        ) : <span className="text-xs text-muted-foreground">未分配</span>; })() : (
                          <span className="text-xs text-muted-foreground">未分配</span>
                        )}
                      </div>
                      <div>
                        {task.status === "running" ? (
                          <div className="flex items-center gap-1.5">
                            <div className="w-12 h-1.5 rounded-full bg-muted overflow-hidden">
                              <div className="h-full bg-primary rounded-full" style={{ width: `${task.progress}%` }} />
                            </div>
                            <span className="text-[10px] font-mono text-primary">{task.progress}%</span>
                          </div>
                        ) : task.status === "completed" ? (
                          <span className="text-[10px] font-mono text-success">100%</span>
                        ) : (
                          <span className="text-[10px] text-muted-foreground">—</span>
                        )}
                      </div>
                      <span className="text-[11px] text-muted-foreground font-mono">{task.created_at ? new Date(task.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) : "--"}</span>
                    </div>
                  );
                })
              )}
            </>
          )}
        </div>
        </>)}

        {/* Cron tab content */}
        {activeTab === "cron" && (
          <div className="flex-1 overflow-y-auto">
            {cronJobs.length === 0 ? (
              <div className="flex items-center justify-center py-20">
                <div className="text-center">
                  <Timer className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                  <p className="text-sm font-medium text-foreground mb-1">暂无定时任务</p>
                  <p className="text-xs text-muted-foreground mb-3">创建定时任务自动执行工作</p>
                  <button onClick={createCronJob} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
                    <Plus className="w-3.5 h-3.5" />新建定时任务
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* Cron table header */}
                <div className="grid grid-cols-[1fr_140px_64px_120px_80px] gap-2 px-6 py-2 border-b border-border text-[11px] text-muted-foreground uppercase tracking-wider font-medium sticky top-0 bg-background z-10">
                  <span>名称</span>
                  <span>Cron 表达式</span>
                  <span>状态</span>
                  <span>上次触发</span>
                  <span>操作</span>
                </div>
                {cronJobs.map((cron) => (
                  <div
                    key={cron.id}
                    onClick={() => openCronEdit(cron)}
                    className={`grid grid-cols-[1fr_140px_64px_120px_80px] gap-2 px-6 py-3 border-b border-border hover:bg-muted/30 transition-colors cursor-pointer items-center ${
                      editingCron?.id === cron.id ? "bg-primary/[0.03]" : ""
                    }`}
                  >
                    <div className="flex flex-col gap-0.5">
                      <span className="text-sm font-medium text-foreground truncate">{cron.name}</span>
                      {cron.description && (
                        <span className="text-[11px] text-muted-foreground truncate">{cron.description}</span>
                      )}
                    </div>
                    <div className="flex flex-col gap-0.5">
                      <span className="text-xs font-mono text-foreground">{cron.cron_expression}</span>
                      <span className="text-[11px] text-muted-foreground">{cronToHuman(cron.cron_expression)}</span>
                    </div>
                    <span>
                      <span className={`inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium ${
                        cron.enabled ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"
                      }`}>
                        {cron.enabled ? "启用" : "停用"}
                      </span>
                    </span>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {cron.last_run_at ? new Date(cron.last_run_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "--"}
                    </span>
                    <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => handleTriggerCron(cron.id)}
                        className="p-1.5 rounded-md hover:bg-primary/10 text-muted-foreground hover:text-primary transition-colors"
                        title="立即触发"
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteCronConfirmId(cron.id)}
                        className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {/* Edit panel (tasks) */}
      {activeTab === "tasks" && editingTask && editPanel}

      {/* Edit panel (cron) */}
      {activeTab === "cron" && editingCron && cronEditPanel}

      {/* Delete confirmation dialog (Q19) */}
      <AlertDialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除任务</AlertDialogTitle>
            <AlertDialogDescription>
              此操作不可撤销。删除后该任务的所有数据将永久丢失。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={executeDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Cron delete confirmation dialog */}
      <AlertDialog open={!!deleteCronConfirmId} onOpenChange={(open) => !open && setDeleteCronConfirmId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除定时任务</AlertDialogTitle>
            <AlertDialogDescription>
              此操作不可撤销。删除后该定时任务将永久丢失。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={executeCronDelete} className="bg-destructive text-destructive-foreground hover:bg-destructive/90">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}









