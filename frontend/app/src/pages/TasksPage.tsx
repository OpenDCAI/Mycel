import { useState, useEffect, useMemo, useCallback } from "react";
import {
  Search, CheckCircle2, Circle, Clock, AlertCircle,
  ListTodo, ArrowUpDown, ChevronDown, ChevronUp, ChevronRight, LayoutGrid, List,
  Plus, AlertTriangle, RefreshCw, ExternalLink,
  Play, Trash2, Timer, Loader2,
} from "lucide-react";
import { useIsMobile } from "@/hooks/use-mobile";
import { toast } from "sonner";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAppStore } from "@/store/app-store";
import { authFetch } from "@/store/auth-store";
import type { Task, TaskStatus, CronJob, Priority } from "@/store/types";
import CronEditor from "@/components/cron-editor";
import TaskModal from "@/components/task-modal";

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
  const [min, hour, dom, , dow] = parts;
  if (dow === "1-5" && dom === "*") return `工作日 ${hour}:${min.padStart(2, "0")}`;
  if (min === "0" && hour !== "*" && dom === "*" && dow === "*") return `每天 ${hour}:00`;
  if (hour !== "*" && dom === "*" && dow === "*") return `每天 ${hour}:${min.padStart(2, "0")}`;
  if (dom === "*" && dow !== "*") {
    const labels = ["日","一","二","三","四","五","六"];
    const days = dow.split(",").map((d: string) => labels[parseInt(d)] || d).join("、");
    return `每周${days} ${hour}:${min.padStart(2, "0")}`;
  }
  if (dom !== "*" && dow === "*") return `每月 ${dom} 日 ${hour}:${min.padStart(2, "0")}`;
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
  const storeBulkDelete = useAppStore((s) => s.bulkDeleteTasks);
  const cronJobs = useAppStore((s) => s.cronJobs);
  const storeAddCronJob = useAppStore((s) => s.addCronJob);
  const storeUpdateCronJob = useAppStore((s) => s.updateCronJob);
  const storeDeleteCronJob = useAppStore((s) => s.deleteCronJob);
  const storeTriggerCronJob = useAppStore((s) => s.triggerCronJob);

  const fetchTasks = useAppStore((s) => s.fetchTasks);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchTasks().catch(() => {/* background poll failure — store handles error state */});
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all");
  const [priorityFilter, setPriorityFilter] = useState<Priority | "all">("all");
  const [sortField, setSortField] = useState<SortField>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("tasks");
  const [tagFilter, setTagFilter] = useState<string | null>(null);

  // Unified task modal state (create + edit)
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskModalTab, setTaskModalTab] = useState<"task" | "cron">("task");
  const [editingTask, setEditingTask] = useState<Task | undefined>(undefined);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Expandable task row state
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [threadCache, setThreadCache] = useState<Record<string, { text: string | null; loading: boolean; error: string | null }>>({});

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

  const openEdit = (task: Task) => { setEditingTask(task); setTaskModalOpen(true); };
  const closeTaskModal = () => { setTaskModalOpen(false); setEditingTask(undefined); };

  const openCreateModal = (tab: "task" | "cron" = "task") => {
    setEditingTask(undefined);
    setTaskModalTab(tab);
    setTaskModalOpen(true);
  };

  const handleCreateTask = async (fields: Partial<Task>) => {
    try {
      await storeAddTask(fields);
      toast.success("任务已创建");
    } catch (e: unknown) {
      toast.error("创建失败: " + (e instanceof Error ? e.message : String(e)));
      throw e;
    }
  };

  const handleSaveTask = async (id: string, fields: Partial<Task>) => {
    try {
      await storeUpdateTask(id, fields);
      toast.success("任务已保存");
    } catch (e: unknown) {
      toast.error("保存失败: " + (e instanceof Error ? e.message : String(e)));
      throw e;
    }
  };

  const executeDelete = async () => {
    if (!deleteConfirmId) return;
    try {
      await storeDeleteTask(deleteConfirmId);
      toast.success("任务已删除");
      setDeleteConfirmId(null);
    } catch (e: unknown) {
      toast.error("删除失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const handleCreateCronJob = async (fields: Partial<CronJob>) => {
    try {
      await storeAddCronJob(fields);
      toast.success("定时任务已创建");
    } catch (e: unknown) {
      toast.error("创建失败: " + (e instanceof Error ? e.message : String(e)));
      throw e;
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

  const THREAD_CACHE_MAX = 50;

  const fetchThreadDetail = useCallback(async (threadId: string) => {
    setThreadCache((prev) => {
      if (prev[threadId]?.loading || (prev[threadId] && !prev[threadId].loading && (prev[threadId].text !== null || prev[threadId].error !== null))) return prev;
      const next = { ...prev, [threadId]: { text: null, loading: true, error: null } };
      // Evict oldest entries when over limit
      const keys = Object.keys(next);
      if (keys.length > THREAD_CACHE_MAX) {
        delete next[keys[0]];
      }
      return next;
    });
    try {
      const res = await authFetch(`/api/threads/${threadId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const messages: Array<{ role: string; content: string | Array<{ type: string; text?: string }> }> = data.messages || [];
      let lastText: string | null = null;
      for (let i = messages.length - 1; i >= 0; i--) {
        const msg = messages[i];
        if (msg.role === "assistant") {
          const content = msg.content;
          if (typeof content === "string") {
            lastText = content;
          } else if (Array.isArray(content)) {
            const textBlock = content.find((c) => c.type === "text" && c.text);
            if (textBlock?.text) lastText = textBlock.text;
          }
          if (lastText) break;
        }
      }
      if (lastText && lastText.length > 300) lastText = lastText.slice(0, 300) + "…";
      setThreadCache((prev) => ({ ...prev, [threadId]: { text: lastText, loading: false, error: null } }));
    } catch (e: unknown) {
      setThreadCache((prev) => ({ ...prev, [threadId]: { text: null, loading: false, error: e instanceof Error ? e.message : "加载失败" } }));
    }
  }, []);

  const toggleExpand = (e: React.MouseEvent, task: Task) => {
    e.stopPropagation();
    if (!task.thread_id) return;
    const isExpanding = expandedTaskId !== task.id;
    setExpandedTaskId(isExpanding ? task.id : null);
    if (isExpanding) fetchThreadDetail(task.thread_id);
  };

  const allTags = useMemo(() => {
    const set = new Set<string>();
    tasks.forEach((t) => (t.tags || []).forEach((tag) => set.add(tag)));
    return [...set].sort();
  }, [tasks]);

  let filtered = tasks.filter((t) => {
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
    if (tagFilter && !(t.tags || []).includes(tagFilter)) return false;
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

  // Cron edit panel (Apple-style)
  const cronEditPanel = cronForm && (
    <CronEditor
      cronForm={cronForm}
      isMobile={isMobile}
      onUpdate={(updated) => setCronForm(updated)}
      onSave={saveCronEdit}
      onClose={closeCronEdit}
      onDelete={() => setDeleteCronConfirmId(cronForm.id)}
    />
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
                <button onClick={() => openCreateModal("task")} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
                  <Plus className="w-4 h-4" />
                  <span className="hidden md:inline">新建任务</span>
                </button>
              </>
            ) : (
              <button onClick={() => openCreateModal("cron")} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
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

        {/* Active tag filter */}
        {tagFilter && (
          <div className="flex items-center gap-2 px-4 md:px-6 py-1.5 border-b border-border bg-primary/[0.03] shrink-0">
            <span className="text-xs text-muted-foreground">标签过滤：</span>
            <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-medium">
              {tagFilter}
              <button onClick={() => setTagFilter(null)} className="hover:text-primary/60 leading-none text-sm">×</button>
            </span>
          </div>
        )}

        {/* Bulk actions bar */}
        {selectedRows.size > 0 && (
          <div className="flex items-center gap-3 px-6 py-2 bg-primary/5 border-b border-primary/15 text-xs shrink-0">
            <span className="text-primary font-medium">已选择 {selectedRows.size} 项</span>
            <button onClick={async () => { try { await storeBulkUpdate([...selectedRows], "pending"); setSelectedRows(new Set()); } catch (e: unknown) { toast.error("操作失败: " + (e instanceof Error ? e.message : String(e))); } }} className="px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors">批量取消</button>
            <button onClick={async () => { try { await storeBulkUpdate([...selectedRows], "running"); setSelectedRows(new Set()); } catch (e: unknown) { toast.error("操作失败: " + (e instanceof Error ? e.message : String(e))); } }} className="px-2 py-1 rounded bg-muted hover:bg-muted/80 text-foreground transition-colors">批量重试</button>
            <button onClick={async () => { try { await storeBulkDelete([...selectedRows]); setSelectedRows(new Set()); toast.success(`已删除 ${selectedRows.size} 个任务`); } catch (e: unknown) { toast.error("删除失败: " + (e instanceof Error ? e.message : String(e))); } }} className="ml-auto text-destructive hover:text-destructive/80 transition-colors">批量删除</button>
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
                            <div className="flex flex-col gap-1 mb-2">
                              <div className="flex items-center gap-1">
                                <p className="text-sm font-medium text-foreground leading-snug">{task.title}</p>
                                {task.source && task.source !== "manual" && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary shrink-0">
                                    {sourceLabel[task.source] || task.source}
                                  </span>
                                )}
                              </div>
                              {(task.tags || []).length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  {(task.tags || []).map((tag) => (
                                    <button
                                      key={tag}
                                      onClick={(e) => { e.stopPropagation(); setTagFilter(tagFilter === tag ? null : tag); }}
                                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium transition-colors ${
                                        tagFilter === tag ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                                      }`}
                                    >
                                      {tag}
                                    </button>
                                  ))}
                                </div>
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
                    <button onClick={() => openCreateModal("task")} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
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
              <div className="grid grid-cols-[32px_32px_1fr_80px_160px_80px_60px_28px] gap-2 px-6 py-2 border-b border-border text-[11px] text-muted-foreground uppercase tracking-wider font-medium sticky top-0 bg-background z-10">
                <span className="flex items-center">
                  <input type="checkbox" aria-label="全选任务" checked={selectedRows.size === filtered.length && filtered.length > 0} onChange={toggleSelectAll} className="w-3.5 h-3.5 accent-primary rounded" />
                </span>
                <span />
                <button onClick={() => handleSort("title")} className="flex items-center hover:text-foreground transition-colors text-left">任务 <SortIcon field="title" /></button>
                <button onClick={() => handleSort("priority")} className="flex items-center hover:text-foreground transition-colors">优先级 <SortIcon field="priority" /></button>
                <span>执行者</span>
                <span>进度</span>
                <button onClick={() => handleSort("created_at")} className="flex items-center hover:text-foreground transition-colors">时间 <SortIcon field="created_at" /></button>
                <span />
              </div>

              {filtered.length === 0 ? (
                <div className="flex items-center justify-center py-20">
                  <div className="text-center">
                    <ListTodo className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
                    <p className="text-sm font-medium text-foreground mb-1">暂无任务</p>
                    <p className="text-xs text-muted-foreground mb-3">创建一个新任务开始工作</p>
                    <button onClick={() => openCreateModal("task")} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
                      <Plus className="w-3.5 h-3.5" />新建任务
                    </button>
                  </div>
                </div>
              ) : (
                filtered.map((task) => {
                  const status = statusConfig[task.status];
                  const priority = priorityConfig[task.priority];
                  const StatusIcon = status.icon;
                  const isExpanded = expandedTaskId === task.id;
                  const cache = task.thread_id ? threadCache[task.thread_id] : null;
                  return (
                    <div key={task.id}>
                      <div
                        onClick={() => openEdit(task)}
                        className={`grid grid-cols-[32px_32px_1fr_80px_160px_80px_60px_28px] gap-2 px-6 py-3 border-b border-border hover:bg-muted/30 transition-colors cursor-pointer items-center ${
                          editingTask?.id === task.id ? "bg-primary/[0.03]" : ""
                        } ${task.status === "failed" ? "bg-destructive/[0.03] border-l-2 border-l-destructive" : ""} ${isExpanded ? "bg-muted/20" : ""}`}
                      >
                        <span className="flex items-center" onClick={(e) => e.stopPropagation()}>
                          <input type="checkbox" aria-label={`选择任务: ${task.title}`} checked={selectedRows.has(task.id)} onChange={() => toggleSelectRow(task.id)} className="w-3.5 h-3.5 accent-primary rounded" />
                        </span>
                        <StatusIcon className={`w-4 h-4 ${status.color}`} />
                        <span className="text-sm font-medium text-foreground truncate flex items-center gap-1 flex-wrap">
                          {task.title}
                          {task.source && task.source !== "manual" && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary ml-1 shrink-0">
                              {sourceLabel[task.source] || task.source}
                            </span>
                          )}
                          {(task.tags || []).map((tag) => (
                            <button
                              key={tag}
                              onClick={(e) => { e.stopPropagation(); setTagFilter(tagFilter === tag ? null : tag); }}
                              className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0 transition-colors ${
                                tagFilter === tag ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-primary/10 hover:text-primary"
                              }`}
                            >
                              {tag}
                            </button>
                          ))}
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
                        <span className="flex items-center justify-center">
                          {task.thread_id && (
                            <button
                              onClick={(e) => toggleExpand(e, task)}
                              className="w-5 h-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                              title={isExpanded ? "收起执行详情" : "展开执行详情"}
                            >
                              {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                            </button>
                          )}
                        </span>
                      </div>
                      {isExpanded && task.thread_id && (
                        <div className="border-b border-border bg-muted/10 px-6 py-3">
                          <div className="flex items-start gap-3">
                            <div className="shrink-0 mt-0.5">
                              <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-[11px] text-muted-foreground font-mono">
                                  Thread: {task.thread_id.slice(0, 8)}…
                                </span>
                                <a
                                  href={`/chat/${task.thread_id}`}
                                  className="inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <ExternalLink className="w-3 h-3" />
                                  查看对话
                                </a>
                              </div>
                              {cache?.loading ? (
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  加载中…
                                </div>
                              ) : cache?.error ? (
                                <p className="text-xs text-destructive">{cache.error}</p>
                              ) : cache?.text ? (
                                <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap border border-border rounded-md px-3 py-2 bg-background">
                                  {cache.text}
                                </p>
                              ) : (
                                <p className="text-xs text-muted-foreground italic">暂无 AI 回复记录</p>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
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
                  <button onClick={() => openCreateModal("cron")} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity">
                    <Plus className="w-3.5 h-3.5" />新建定时任务
                  </button>
                </div>
              </div>
            ) : (
              <>
                {/* Cron table header */}
                <div className="grid grid-cols-[1fr_160px_64px_120px_80px] gap-2 px-6 py-2 border-b border-border text-[11px] text-muted-foreground uppercase tracking-wider font-medium sticky top-0 bg-background z-10">
                  <span>名称</span>
                  <span>执行频率</span>
                  <span>状态</span>
                  <span>上次触发</span>
                  <span>操作</span>
                </div>
                {cronJobs.map((cron) => (
                  <div
                    key={cron.id}
                    onClick={() => openCronEdit(cron)}
                    className={`grid grid-cols-[1fr_160px_64px_120px_80px] gap-2 px-6 py-3 border-b border-border hover:bg-muted/30 transition-colors cursor-pointer items-center ${
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
                      <span className="text-sm text-foreground">{cronToHuman(cron.cron_expression)}</span>
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

      {/* Edit panel (cron) */}
      {activeTab === "cron" && editingCron && cronEditPanel}

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

      {/* Task delete confirmation dialog */}
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

      {/* Unified Task Modal (create + edit) */}
      <TaskModal
        open={taskModalOpen}
        editTask={editingTask}
        defaultTab={taskModalTab}
        members={memberList}
        existingTags={allTags}
        onClose={closeTaskModal}
        onCreateTask={handleCreateTask}
        onSaveTask={handleSaveTask}
        onDeleteTask={(id) => setDeleteConfirmId(id)}
        onCreateCronJob={handleCreateCronJob}
      />
    </div>
  );
}









