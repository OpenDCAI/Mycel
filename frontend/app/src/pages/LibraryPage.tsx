import { useState, useEffect } from "react";
import { Search, Plus, Zap, Plug, Bot, Edit, Trash2, AlertTriangle, RefreshCw, FlaskConical } from "lucide-react";
import LibraryEditor from "@/components/LibraryEditor";
import RecipeEditor from "@/components/RecipeEditor";
import { toast } from "sonner";
import { useIsMobile } from "@/hooks/use-mobile";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { useAppStore } from "@/store/app-store";
import type { ResourceItem } from "@/store/types";

type ResourceType = "skills" | "mcp" | "agents" | "recipes";

const typeMap: Record<ResourceType, string> = { skills: "skill", mcp: "mcp", agents: "agent", recipes: "recipe" };

const tabs: { id: ResourceType; label: string; icon: typeof Zap }[] = [
  { id: "skills", label: "Skill", icon: Zap },
  { id: "mcp", label: "MCP", icon: Plug },
  { id: "agents", label: "Agent", icon: Bot },
  { id: "recipes", label: "Recipe", icon: FlaskConical },
];

const RECIPE_PROVIDER_LABELS: Record<string, string> = {
  local: "Local",
  daytona: "Daytona",
  docker: "Docker",
  e2b: "E2B",
  agentbay: "AgentBay",
};

function providerLabel(name?: string): string {
  if (!name) return "Unknown";
  const hit = RECIPE_PROVIDER_LABELS[name];
  if (hit) return hit;
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function LibraryPage() {
  const isMobile = useIsMobile();
  const librarySkills = useAppStore((s) => s.librarySkills);
  const libraryMcps = useAppStore((s) => s.libraryMcps);
  const libraryAgents = useAppStore((s) => s.libraryAgents);
  const libraryRecipes = useAppStore((s) => s.libraryRecipes);
  const loadAll = useAppStore((s) => s.loadAll);
  const error = useAppStore((s) => s.error);
  const retry = useAppStore((s) => s.retry);
  const storeDeleteResource = useAppStore((s) => s.deleteResource);
  const getResourceUsedBy = useAppStore((s) => s.getResourceUsedBy);

  useEffect(() => { loadAll(); }, [loadAll]);

  const [tab, setTab] = useState<ResourceType>("skills");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ResourceItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [recipeDirty, setRecipeDirty] = useState(false);

  // Delete dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletingItem, setDeletingItem] = useState<ResourceItem | null>(null);

  const getList = () =>
    tab === "skills"
      ? librarySkills
      : tab === "mcp"
        ? libraryMcps
        : tab === "agents"
          ? libraryAgents
          : libraryRecipes;

  const items = getList();
  const filtered = items.filter((i) => i.name.toLowerCase().includes(search.toLowerCase()));
  const Icon = tab === "skills" ? Zap : tab === "mcp" ? Plug : tab === "agents" ? Bot : FlaskConical;
  const isRecipeTab = tab === "recipes";

  const handleCardClick = (item: ResourceItem) => {
    if (isRecipeTab && recipeDirty && selected?.id !== item.id) {
      const confirmed = window.confirm("当前 recipe 还有未保存的修改，确定要切换吗？");
      if (!confirmed) return;
    }
    setCreating(false);
    setSelected(item);
    setRecipeDirty(false);
  };

  const openCreate = () => {
    setSelected(null);
    setCreating(true);
  };

  const handleCreated = (item: ResourceItem) => {
    setCreating(false);
    setSelected(item);
  };

  const openDelete = (item: ResourceItem) => {
    setDeletingItem(item);
    setDeleteDialogOpen(true);
  };

  const handleDelete = async () => {
    if (!deletingItem) return;
    try {
      await storeDeleteResource(typeMap[tab], deletingItem.id);
      if (selected?.id === deletingItem.id) setSelected(null);
      toast.success(`${deletingItem.name} 已删除`);
      setDeleteDialogOpen(false);
    } catch (e: unknown) {
      toast.error("删除失败: " + (e instanceof Error ? e.message : String(e)));
    }
  };

  const resolvedSelected = selected ? items.find((item) => item.id === selected.id) ?? selected : null;
  const showDetail = resolvedSelected !== null || creating;

  return (
    <div className="flex h-full">
      {/* Sidebar tabs - desktop */}
      {!isMobile && (
        <div className="w-[200px] shrink-0 border-r border-border bg-card flex flex-col">
          <div className="h-14 flex items-center justify-between px-4 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Library</h2>
          </div>
          <div className="flex-1 p-2 space-y-0.5">
            {tabs.map((t) => {
              const count = (
                t.id === "skills" ? librarySkills :
                t.id === "mcp" ? libraryMcps :
                t.id === "agents" ? libraryAgents :
                libraryRecipes
              ).length;
              const isActive = tab === t.id;
              return (
                <button key={t.id} onClick={() => {
                  if (recipeDirty && isRecipeTab) {
                    const confirmed = window.confirm("当前 recipe 还有未保存的修改，确定要离开吗？");
                    if (!confirmed) return;
                  }
                  setTab(t.id); setSearch(""); setSelected(null); setCreating(false); setRecipeDirty(false);
                }} className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all ${
                  isActive ? "bg-primary/5 text-foreground border border-primary/15" : "text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent"
                }`}>
                  <div className="flex items-center gap-2.5"><t.icon className={`w-4 h-4 ${isActive ? "text-primary" : ""}`} /><span>{t.label}</span></div>
                  <span className={`text-xs font-mono ${isActive ? "text-primary" : ""}`}>{count}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 flex flex-col overflow-hidden bg-background">
        {/* Content header bar */}
        <div className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            {/* Mobile tabs */}
            {isMobile && (
              <div className="flex gap-1 overflow-x-auto">
                {tabs.map((t) => {
                  const isActive = tab === t.id;
                  return (
                    <button key={t.id} onClick={() => {
                      if (recipeDirty && isRecipeTab) {
                        const confirmed = window.confirm("当前 recipe 还有未保存的修改，确定要离开吗？");
                        if (!confirmed) return;
                      }
                      setTab(t.id); setSearch(""); setSelected(null); setCreating(false); setRecipeDirty(false);
                    }} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs whitespace-nowrap shrink-0 transition-colors ${
                      isActive ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                    }`}>
                      <t.icon className="w-3.5 h-3.5" />{t.label}
                    </button>
                  );
                })}
              </div>
            )}
            {!isMobile && (
              <>
                <h3 className="text-sm font-semibold text-foreground">
                  {tab === "skills" ? "Skill" : tab === "mcp" ? "MCP" : tab === "agents" ? "Agent" : "Recipe"}
                </h3>
                <span className="text-xs text-muted-foreground font-mono">{items.length}</span>
              </>
            )}
          </div>
          {!isRecipeTab && (
            <button onClick={openCreate} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity">
              <Plus className="w-4 h-4" />
              <span className="hidden md:inline">新建</span>
            </button>
          )}
        </div>

        <div className={`flex-1 overflow-y-auto`}>
          <div className={`${showDetail && !isMobile ? "max-w-xl" : "max-w-2xl"} mx-auto py-6 px-4 md:px-6`}>

          {/* Search */}
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索..." className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors" />
          </div>

          {isRecipeTab && (
            <div className="mb-4 rounded-2xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
              Recipes 是每种 provider 的默认环境模板。可以直接修改默认配置，也可以随时重置回系统默认值。
            </div>
          )}

          {/* Grid */}
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
          ) : (<>
          <div className={`grid ${isMobile ? "grid-cols-1" : "grid-cols-2"} gap-3`}>
            {filtered.map((item) => (
              <div
                key={item.id}
                onClick={() => { handleCardClick(item); }}
                className={`${isRecipeTab ? "rounded-2xl border border-border bg-card cursor-pointer hover:bg-accent/20" : "surface-interactive cursor-pointer"} p-4 group relative ${
                  isRecipeTab ? "" : ""
                } ${resolvedSelected?.id === item.id ? "border-primary/40 glow-sm" : ""}`}
              >
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-primary/8 flex items-center justify-center shrink-0">
                    <Icon className="w-4 h-4 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <h4 className={`text-sm font-medium text-foreground ${isRecipeTab ? "" : "group-hover:text-primary transition-colors"}`}>{item.name}</h4>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">{item.desc}</p>
                    <p className="text-[11px] text-muted-foreground mt-2">
                      {isRecipeTab
                        ? `${providerLabel(item.provider_name)} · 默认 recipe`
                        : (() => {
                            const n = getResourceUsedBy(typeMap[tab], item.name).length;
                            return n ? `被 ${n} 位成员使用` : "未被使用";
                          })()}
                    </p>
                  </div>
                </div>
                {!isRecipeTab && (
                  <div className="absolute top-2 right-2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={(e) => { e.stopPropagation(); handleCardClick(item); }} className="p-1 rounded hover:bg-muted transition-colors" title="编辑">
                      <Edit className="w-3 h-3 text-muted-foreground" />
                    </button>
                    <button onClick={(e) => { e.stopPropagation(); openDelete(item); }} className="p-1 rounded hover:bg-destructive/10 transition-colors" title="删除">
                      <Trash2 className="w-3 h-3 text-muted-foreground hover:text-destructive" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
          {filtered.length === 0 && (
            <div className="text-center py-12 text-sm text-muted-foreground">未找到相关内容</div>
          )}
          </>)}
        </div>
        </div>
      </div>

      {/* Editor panel */}
      {!isMobile && showDetail && !isRecipeTab && (
        <LibraryEditor item={resolvedSelected} type={typeMap[tab] as "skill" | "mcp" | "agent"} onClose={() => { setSelected(null); setCreating(false); }} onCreated={handleCreated} />
      )}
      {!isMobile && showDetail && isRecipeTab && resolvedSelected && (
        <RecipeEditor
          item={resolvedSelected}
          onDirtyChange={setRecipeDirty}
          onClose={() => {
            if (recipeDirty) {
              const confirmed = window.confirm("当前 recipe 还有未保存的修改，确定要关闭吗？");
              if (!confirmed) return;
            }
            setSelected(null);
            setCreating(false);
            setRecipeDirty(false);
          }}
        />
      )}
      {isMobile && showDetail && !isRecipeTab && (
        <div className="fixed inset-0 z-50 bg-background overflow-y-auto">
          <LibraryEditor item={resolvedSelected} type={typeMap[tab] as "skill" | "mcp" | "agent"} onClose={() => { setSelected(null); setCreating(false); }} onCreated={handleCreated} />
        </div>
      )}
      {isMobile && showDetail && isRecipeTab && resolvedSelected && (
        <div className="fixed inset-0 z-50 bg-background overflow-y-auto">
          <RecipeEditor
            item={resolvedSelected}
            onDirtyChange={setRecipeDirty}
            onClose={() => {
              if (recipeDirty) {
                const confirmed = window.confirm("当前 recipe 还有未保存的修改，确定要关闭吗？");
                if (!confirmed) return;
              }
              setSelected(null);
              setCreating(false);
              setRecipeDirty(false);
            }}
          />
        </div>
      )}

      {/* Delete confirmation */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>确定要删除 "{deletingItem?.name}" 吗？此操作不可撤销。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
