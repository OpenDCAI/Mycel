import { useState, useEffect } from "react";
import { Search, Plus, Zap, Users, Wrench, Plug, SearchX, ArrowUpDown, AlertTriangle, RefreshCw, MessageSquare, Copy, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import CreateMemberDialog from "@/components/CreateMemberDialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAppStore } from "@/store/app-store";
import { toast } from "sonner";

const statusConfig = {
  active: { label: "在线", dot: "bg-success", shape: "rounded-full" },
  draft: { label: "草稿", dot: "bg-warning", shape: "rounded-sm" },
  inactive: { label: "离线", dot: "bg-muted-foreground", shape: "rounded-full opacity-50" },
};

const avatarColors = [
  "bg-primary/15 text-primary",
  "bg-success/15 text-success",
  "bg-warning/15 text-warning",
  "bg-destructive/15 text-destructive",
  "bg-chart-1/15 text-chart-1",
  "bg-accent text-accent-foreground",
];

type SortKey = "name" | "skills" | "status" | null;

export default function MembersPage() {
  const isMobile = useIsMobile();
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "draft" | "inactive">("all");
  const [sortBy, setSortBy] = useState<SortKey>(null);
  const navigate = useNavigate();
  const memberList = useAppStore(s => s.memberList);
  const loadAll = useAppStore(s => s.loadAll);
  const error = useAppStore(s => s.error);
  const retry = useAppStore(s => s.retry);
  const deleteMember = useAppStore(s => s.deleteMember);
  const addMember = useAppStore(s => s.addMember);
  const updateMemberConfig = useAppStore(s => s.updateMemberConfig);

  useEffect(() => { loadAll(); }, [loadAll]);

  let filtered = memberList.filter((s) => {
    if (statusFilter !== "all" && s.status !== statusFilter) return false;
    if (search && !s.name.toLowerCase().includes(search.toLowerCase()) && !s.description.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (sortBy === "name") filtered = [...filtered].sort((a, b) => a.name.localeCompare(b.name));
  else if (sortBy === "skills") filtered = [...filtered].sort((a, b) => b.config.skills.length - a.config.skills.length);
  else if (sortBy === "status") {
    const order = { active: 0, draft: 1, inactive: 2 };
    filtered = [...filtered].sort((a, b) => order[a.status] - order[b.status]);
  }

  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">成员</h2>
          <span className="text-xs text-muted-foreground font-mono">{memberList.length}</span>
        </div>
        <button onClick={() => setCreateOpen(true)} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
          <Plus className="w-4 h-4" />
          <span className="hidden md:inline">创建成员</span>
        </button>
      </div>

      {/* Filters */}
      <div className={`px-4 md:px-6 py-3 border-b border-border flex items-center gap-3 ${isMobile ? "overflow-x-auto" : "gap-4"}`}>
        <div className={`relative ${isMobile ? "min-w-[150px] flex-1" : "max-w-md flex-1"}`}>
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索成员..." className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors" />
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {(["all", "active", "draft", "inactive"] as const).map((s) => {
            const count = s === "all" ? memberList.length : memberList.filter((st) => st.status === s).length;
            return (
              <button key={s} onClick={() => setStatusFilter(s)} className={`px-2 py-1 rounded-md text-xs transition-colors whitespace-nowrap ${
                statusFilter === s ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}>
                {s === "all" ? "全部" : statusConfig[s].label}
                {!isMobile && <span className="ml-1 font-mono">{count}</span>}
              </button>
            );
          })}
        </div>

        {!isMobile && (
          <button
            onClick={() => setSortBy(sortBy === "name" ? "skills" : sortBy === "skills" ? "status" : sortBy === "status" ? null : "name")}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0"
          >
            <ArrowUpDown className="w-3 h-3" />
            {sortBy ? `排序: ${sortBy === "name" ? "名称" : sortBy === "skills" ? "技能数" : "状态"}` : "排序"}
          </button>
        )}
      </div>

      {/* Card Grid */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6">
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
        ) : filtered.length === 0 ? (
          memberList.length === 0 ? (
            /* Truly empty — no members at all */
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
                <Bot className="w-7 h-7 text-primary" />
              </div>
              <p className="text-sm font-semibold text-foreground mb-1">还没有 AI 成员</p>
              <p className="text-xs text-muted-foreground mb-5 max-w-[220px] text-center leading-relaxed">
                创建你的第一个 AI 成员，赋予它专属技能与工具
              </p>
              <button
                onClick={() => setCreateOpen(true)}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity"
              >
                <Plus className="w-3.5 h-3.5" />创建成员
              </button>
            </div>
          ) : (
            /* Filter / search returned nothing */
            <div className="flex flex-col items-center justify-center py-24">
              <div className="w-12 h-12 rounded-xl bg-muted flex items-center justify-center mb-4">
                <SearchX className="w-6 h-6 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium text-foreground mb-1">未找到匹配成员</p>
              <p className="text-xs text-muted-foreground">尝试调整搜索词或筛选条件</p>
            </div>
          )
        ) : (
          <div className={`grid gap-4 ${isMobile ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"}`}>
            {filtered.map((member, index) => {
              const status = statusConfig[member.status];
              const colorClass = avatarColors[index % avatarColors.length];
              const initials = member.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
              const isBuiltin = (member as any).builtin === true;
              const handleCardClick = () => {
                navigate(`/members/${member.id}`);
              };
              const handleStartChat = (e: React.MouseEvent) => {
                e.stopPropagation();
                navigate("/chat", { state: { startWith: member.id, memberName: member.name } });
              };
              const handleCopy = async (e: React.MouseEvent) => {
                e.stopPropagation();
                try {
                  const newMember = await addMember(`${member.name} (副本)`, member.description);
                  await updateMemberConfig(newMember.id, {
                    prompt: member.config.prompt,
                    tools: member.config.tools,
                    mcps: member.config.mcps,
                    skills: member.config.skills,
                    subAgents: member.config.subAgents,
                    rules: member.config.rules,
                  });
                  toast.success("已复制");
                } catch { toast.error("复制失败"); }
              };
              const handleDelete = async (e: React.MouseEvent) => {
                e.stopPropagation();
                if (isBuiltin) return;
                try {
                  await deleteMember(member.id);
                  toast.success("已删除");
                } catch { toast.error("删除失败"); }
              };
              return (
                <div key={member.id} onClick={handleCardClick} className="surface-interactive p-4 cursor-pointer group hover:-translate-y-0.5 hover:shadow-md" role="button" aria-label={isBuiltin ? `与 ${member.name} 对话` : `查看成员 ${member.name}`} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && handleCardClick()}>
                  <div className="flex items-start justify-between mb-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xs font-bold font-mono ${colorClass}`}>{initials}</div>
                    <div className="flex items-center gap-1.5">
                      {isBuiltin && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">内置</span>}
                      <div className={`w-1.5 h-1.5 ${status.shape} ${status.dot}`} />
                      <span className="text-[11px] text-muted-foreground">{status.label}</span>
                    </div>
                  </div>
                  <h3 className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors mb-0.5">{member.name}</h3>
                  <p className="text-xs text-muted-foreground mb-3 line-clamp-2">{member.description}</p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                      <Tooltip><TooltipTrigger asChild><span className="flex items-center gap-1 cursor-default"><Zap className="w-3 h-3" /> {member.config.skills.length}</span></TooltipTrigger><TooltipContent side="bottom"><p>Skills</p></TooltipContent></Tooltip>
                      <Tooltip><TooltipTrigger asChild><span className="flex items-center gap-1 cursor-default"><Wrench className="w-3 h-3" /> {member.config.tools.length}</span></TooltipTrigger><TooltipContent side="bottom"><p>Tools</p></TooltipContent></Tooltip>
                      <Tooltip><TooltipTrigger asChild><span className="flex items-center gap-1 cursor-default"><Plug className="w-3 h-3" /> {member.config.mcps.length}</span></TooltipTrigger><TooltipContent side="bottom"><p>MCP</p></TooltipContent></Tooltip>
                      <Tooltip><TooltipTrigger asChild><span className="flex items-center gap-1 cursor-default"><Users className="w-3 h-3" /> {member.config.subAgents.length}</span></TooltipTrigger><TooltipContent side="bottom"><p>Agents</p></TooltipContent></Tooltip>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button onClick={handleStartChat} className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors opacity-0 group-hover:opacity-100">
                            <MessageSquare className="w-3.5 h-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom"><p>发起会话</p></TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button onClick={handleCopy} className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors opacity-0 group-hover:opacity-100">
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="bottom"><p>复制</p></TooltipContent>
                      </Tooltip>
                      {!isBuiltin && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button onClick={handleDelete} className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors opacity-0 group-hover:opacity-100">
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="bottom"><p>删除</p></TooltipContent>
                        </Tooltip>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <CreateMemberDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
