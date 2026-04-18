import React, { useState, useEffect, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Box, Search, Store, Package, TrendingUp, Clock, RefreshCw, Zap, Users, Trash2, Plus, X } from "lucide-react";
import { useMarketplaceStore } from "@/store/marketplace-store";
import { useAppStore } from "@/store/app-store";
import { useIsMobile } from "@/hooks/use-mobile";
import MarketplaceCard from "@/components/marketplace/MarketplaceCard";
import UpdateDialog from "@/components/marketplace/UpdateDialog";
import SandboxTemplateEditor from "@/components/SandboxTemplateEditor";
import type { Agent, ResourceItem } from "@/store/types";
import type { UpdateAvailable } from "@/store/marketplace-store";
import { HUB_AGENT_USER_ITEM_TYPE } from "@/lib/marketplace-types";

type Tab = "explore" | "installed";
type InstalledSubTab = "agent-user" | "skill" | "agent" | "sandbox-template";
type TypeFilter = "all" | typeof HUB_AGENT_USER_ITEM_TYPE | "agent" | "skill" | "env";

function isTab(value: string | null): value is Tab {
  return value === "explore" || value === "installed";
}

function normalizeInstalledSubTab(value: string | null): InstalledSubTab | null {
  if (value === "subagent") return "agent";
  if (value === "skill-template") return "skill";
  if (value === "sandbox") return "sandbox-template";
  if (value === "agent-user" || value === "skill" || value === "agent" || value === "sandbox-template") return value;
  return null;
}

const typeFilters: { id: TypeFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: HUB_AGENT_USER_ITEM_TYPE, label: "Agent" },
  { id: "agent", label: "Subagent" },
  { id: "skill", label: "Skill" },
  { id: "env", label: "Env" },
];

const sortOptions = [
  { id: "downloads", label: "Popular", icon: TrendingUp },
  { id: "newest", label: "Newest", icon: Clock },
];

export default function MarketplacePage() {
  const isMobile = useIsMobile();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const rawTab = searchParams.get("tab");
  const rawInstalledSubTab = searchParams.get("sub");
  const tab = isTab(rawTab) ? rawTab : "explore";
  const installedSubTab = normalizeInstalledSubTab(rawInstalledSubTab) ?? "agent-user";

  const setTab = (t: Tab) => setSearchParams((p) => { p.set("tab", t); p.delete("sub"); return p; }, { replace: true });
  const setInstalledSubTab = (s: InstalledSubTab) => setSearchParams((p) => { p.set("sub", s); return p; }, { replace: true });

  // Explore state
  const items = useMarketplaceStore((s) => s.items);
  const total = useMarketplaceStore((s) => s.total);
  const loading = useMarketplaceStore((s) => s.loading);
  const filters = useMarketplaceStore((s) => s.filters);
  const setFilter = useMarketplaceStore((s) => s.setFilter);
  const fetchItems = useMarketplaceStore((s) => s.fetchItems);
  const error = useMarketplaceStore((s) => s.error);

  // Installed state
  const agentList = useAppStore((s) => s.agentList);
  const librarySkills = useAppStore((s) => s.librarySkills);
  const libraryAgents = useAppStore((s) => s.libraryAgents);
  const librarySandboxTemplates = useAppStore((s) => s.librarySandboxTemplates);
  const agentsLoaded = useAppStore((s) => s.agentsLoaded);
  const librariesLoaded = useAppStore((s) => s.librariesLoaded);
  const deleteResource = useAppStore((s) => s.deleteResource);
  const updates = useMarketplaceStore((s) => s.updates);
  const checkUpdates = useMarketplaceStore((s) => s.checkUpdates);

  // Search
  const [searchInput, setSearchInput] = useState("");
  const [installedSearch, setInstalledSearch] = useState("");

  // Update dialog
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [updateTarget, setUpdateTarget] = useState<{ agent: Agent; update: UpdateAvailable } | null>(null);
  const [recipeCreateOpen, setRecipeCreateOpen] = useState(false);


  // Fetch explore items when filters change
  useEffect(() => {
    if (tab !== "explore") return;
    const controller = new AbortController();
    void fetchItems(controller.signal);
    return () => {
      controller.abort();
    };
  }, [tab, filters, fetchItems]);

  // Debounced search
  useEffect(() => {
    const timer = setTimeout(() => {
      if (tab === "explore") setFilter("q", searchInput);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput, tab, setFilter]);

  const handleTypeFilter = (type: TypeFilter) => {
    setFilter("type", type === "all" ? null : type);
  };

  // Installed agent users with marketplace source info
  const installedAgentUsers: Agent[] = agentList.filter((agent) => !agent.builtin);
  const updateCheckableAgentUsers = installedAgentUsers.filter((agent) => agent.source?.marketplace_item_id);
  const filteredAgentUsers = installedAgentUsers.filter((agent) =>
    !installedSearch || agent.name.toLowerCase().includes(installedSearch.toLowerCase())
  );
  const filteredSkills = librarySkills.filter((s) =>
    !installedSearch || s.name.toLowerCase().includes(installedSearch.toLowerCase())
  );
  const filteredAgents = libraryAgents.filter((a) =>
    !installedSearch || a.name.toLowerCase().includes(installedSearch.toLowerCase())
  );
  const filteredSandboxTemplates = librarySandboxTemplates.filter((sandboxTemplate) =>
    !installedSearch || sandboxTemplate.name.toLowerCase().includes(installedSearch.toLowerCase())
  );
  const recipeProviderOptions = useMemo<ResourceItem[]>(() => {
    const seen = new Set<string>();
    return librarySandboxTemplates.filter((sandboxTemplate) => {
      const providerName = sandboxTemplate.provider_name;
      if (!providerName || seen.has(providerName)) return false;
      seen.add(providerName);
      return true;
    });
  }, [librarySandboxTemplates]);

  const installedSubTabs: { id: InstalledSubTab; label: string; icon: React.ElementType; count: number }[] = [
    { id: "agent-user", label: "Agent", icon: Package, count: installedAgentUsers.length },
    { id: "skill", label: "Skill", icon: Zap, count: librarySkills.length },
    { id: "agent", label: "Subagent", icon: Users, count: libraryAgents.length },
    { id: "sandbox-template", label: "Sandbox", icon: Box, count: librarySandboxTemplates.length },
  ];
  const installedSubTabLoaded = installedSubTab === "agent-user" ? agentsLoaded : librariesLoaded[installedSubTab];

  const handleCheckUpdates = async () => {
    if (updateCheckableAgentUsers.length === 0) return;
    // source is projected from agent_configs.meta; agent users without marketplace lineage cannot be checked.
    const payload = updateCheckableAgentUsers.flatMap((agent) => {
      const source = agent.source;
      if (!source?.marketplace_item_id) return [];
      return [{
        marketplace_item_id: source.marketplace_item_id,
        installed_version: source.installed_version || "0.0.0",
      }];
    });
    if (payload.length > 0) await checkUpdates(payload);
  };

  const tabItems = [
    { id: "explore" as Tab, label: "Explore", icon: Store },
    { id: "installed" as Tab, label: "Installed", icon: Package },
  ];

  return (
    <div className="flex h-full">
      {/* Sidebar tabs - desktop */}
      {!isMobile && (
        <div className="w-[200px] shrink-0 border-r border-border bg-card flex flex-col">
          <div className="h-14 flex items-center px-4 border-b border-border">
            <h2 className="text-sm font-semibold text-foreground">Marketplace</h2>
          </div>
          <div className="flex-1 p-2 space-y-0.5">
            {tabItems.map((t) => {
              const isActive = tab === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all duration-fast ${
                    isActive
                      ? "bg-primary/5 text-foreground border border-primary/15"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground border border-transparent"
                  }`}
                >
                  <t.icon className={`w-4 h-4 ${isActive ? "text-primary" : ""}`} />
                  <span>{t.label}</span>
                  {t.id === "installed" && updates.length > 0 && (
                    <span className="ml-auto text-2xs px-1.5 py-0.5 rounded-full bg-primary text-primary-foreground font-medium">
                      {updates.length}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 flex flex-col overflow-hidden bg-background">
        {/* Header */}
        <div className="h-14 flex items-center justify-between px-4 md:px-6 border-b border-border shrink-0">
          <div className="flex items-center gap-3">
            {isMobile && (
              <div className="flex gap-1">
                {tabItems.map((t) => {
                  const isActive = tab === t.id;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setTab(t.id)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs whitespace-nowrap shrink-0 transition-colors duration-fast ${
                        isActive ? "bg-primary/10 text-primary font-medium" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                      }`}
                    >
                      <t.icon className="w-3.5 h-3.5" />{t.label}
                    </button>
                  );
                })}
              </div>
            )}
            {!isMobile && (
              <h3 className="text-sm font-semibold text-foreground">
                {tab === "explore" ? "Explore" : "Installed"}
              </h3>
            )}
          </div>
          {tab === "installed" && installedSubTab === "agent-user" && (
            <button
              onClick={handleCheckUpdates}
              disabled={updateCheckableAgentUsers.length === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors duration-fast"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              检查更新
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto py-6 px-4 md:px-6">
            {tab === "explore" && (
              <>
                {/* Search */}
                <div className="relative mb-4">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="搜索 Marketplace..."
                    className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors duration-fast"
                  />
                </div>

                {/* Type filter + Sort */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex gap-1.5">
                    {typeFilters.map((f) => (
                      <button
                        key={f.id}
                        onClick={() => handleTypeFilter(f.id)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-fast ${
                          (f.id === "all" && !filters.type) || filters.type === f.id
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted"
                        }`}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1">
                    {sortOptions.map((s) => (
                      <button
                        key={s.id}
                        onClick={() => setFilter("sort", s.id)}
                        className={`p-1.5 rounded-md transition-colors duration-fast ${
                          filters.sort === s.id
                            ? "text-primary bg-primary/10"
                            : "text-muted-foreground hover:text-foreground hover:bg-muted"
                        }`}
                        title={s.label}
                      >
                        <s.icon className="w-3.5 h-3.5" />
                      </button>
                    ))}
                  </div>
                </div>

                {/* Error banner */}
                {error && (
                  <div className="flex items-center justify-between px-4 py-2.5 rounded-lg bg-destructive/10 text-destructive text-sm mb-4">
                    <span>{error}</span>
                    <button onClick={() => fetchItems()} className="text-xs underline">重试</button>
                  </div>
                )}

                {/* Results */}
                {loading ? (
                  <div className="flex items-center justify-center py-20">
                    <RefreshCw className="w-5 h-5 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <>
                    <div className={`grid ${isMobile ? "grid-cols-1" : "grid-cols-2"} gap-3`}>
                      {items.map((item) => (
                        <MarketplaceCard
                          key={item.id}
                          item={item}
                          onClick={() => navigate(`/marketplace/${item.id}`)}
                        />
                      ))}
                    </div>
                    {items.length === 0 && !loading && (
                      <div className="text-center py-12 text-sm text-muted-foreground">
                        {filters.q ? "未找到结果" : "Marketplace 暂无内容"}
                      </div>
                    )}
                    {/* Pagination */}
                    {total > 20 && (
                      <div className="flex items-center justify-center gap-2 mt-6">
                        <button
                          disabled={filters.page <= 1}
                          onClick={() => setFilter("page", filters.page - 1)}
                          className="px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50 transition-colors duration-fast"
                        >
                          上一页
                        </button>
                        <span className="text-xs text-muted-foreground">
                          Page {filters.page} of {Math.ceil(total / 20)}
                        </span>
                        <button
                          disabled={filters.page >= Math.ceil(total / 20)}
                          onClick={() => setFilter("page", filters.page + 1)}
                          className="px-3 py-1.5 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50 transition-colors duration-fast"
                        >
                          下一页
                        </button>
                      </div>
                    )}
                  </>
                )}
              </>
            )}

            {tab === "installed" && (
              <>
                {/* Search */}
                <div className="relative mb-4">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <input
                    value={installedSearch}
                    onChange={(e) => setInstalledSearch(e.target.value)}
                    placeholder="搜索已安装..."
                    className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40 transition-colors duration-fast"
                  />
                </div>

                {/* Sub-tabs */}
                <div className="flex gap-1 mb-4">
                  {installedSubTabs.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setInstalledSubTab(t.id)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-fast ${
                        installedSubTab === t.id
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted"
                      }`}
                    >
                      <t.icon className="w-3 h-3" />
                      {t.label}
                      {t.count > 0 && (
                        <span className={`px-1.5 py-0.5 rounded-full text-2xs font-medium ${
                          installedSubTab === t.id ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"
                        }`}>
                          {t.count}
                        </span>
                      )}
                    </button>
                  ))}
                </div>

                {installedSubTabLoaded && installedSubTab === "sandbox-template" && (
                  <div className="mb-4 flex items-center justify-between rounded-xl border border-border bg-card px-3 py-2">
                    <div>
                      <p className="text-sm font-medium text-foreground">Sandbox 模板</p>
                      <p className="text-xs text-muted-foreground">为当前账号创建可复用的 sandbox template。</p>
                    </div>
                    <button
                      type="button"
                      disabled={recipeProviderOptions.length === 0}
                      onClick={() => setRecipeCreateOpen(true)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background transition-colors hover:bg-foreground/90 disabled:opacity-50"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      新建 Sandbox
                    </button>
                  </div>
                )}

                {!installedSubTabLoaded && (
                  <div className="text-center py-12 text-sm text-muted-foreground">正在加载已安装内容...</div>
                )}

                {/* Agent user list */}
                {installedSubTabLoaded && installedSubTab === "agent-user" && (
                  <>
                    <div className={`grid ${isMobile ? "grid-cols-1" : "grid-cols-2"} gap-3`}>
                      {filteredAgentUsers.map((agent) => {
                        const update = updates.find((u) => u.marketplace_item_id === agent.id);
                        return (
                          <div key={agent.id} className="surface-interactive p-4 cursor-pointer group relative" onClick={() => navigate(`/contacts/agents/${agent.id}`)}>
                            <div className="flex items-start gap-3">
                              <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                                <Package className="w-4 h-4 text-primary" />
                              </div>
                              <div className="min-w-0 flex-1">
                                <h4 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors duration-fast">{agent.name}</h4>
                                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{agent.description}</p>
                                <p className="text-2xs text-muted-foreground mt-2 font-mono">v{agent.version}</p>
                              </div>
                            </div>
                            {update && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setUpdateTarget({ agent, update });
                                  setUpdateDialogOpen(true);
                                }}
                                className="absolute top-2 right-2 text-2xs px-2 py-0.5 rounded-full bg-primary/10 text-primary font-medium hover:bg-primary/20 transition-colors duration-fast"
                              >
                                更新到 v{update.latest_version}
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                    {filteredAgentUsers.length === 0 && (
                      <div className="text-center py-12 text-sm text-muted-foreground">暂无已安装的 Agent</div>
                    )}
                  </>
                )}

                {/* Skill list */}
                {installedSubTabLoaded && installedSubTab === "skill" && (
                  <>
                    <div className={`grid ${isMobile ? "grid-cols-1" : "grid-cols-2"} gap-3`}>
                      {filteredSkills.map((skill) => (
                        <div
                          key={skill.id}
                          onClick={() => navigate(`/library/skill/${skill.id}`)}
                          className="surface-interactive p-4 cursor-pointer group relative"
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-9 h-9 rounded-lg bg-warning/10 flex items-center justify-center shrink-0">
                              <Zap className="w-4 h-4 text-warning" />
                            </div>
                            <div className="min-w-0 flex-1 pr-8">
                              <h4 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors duration-fast">{skill.name}</h4>
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{skill.desc || "暂无描述"}</p>
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteResource("skill", skill.id); }}
                            className="absolute top-3 right-3 p-1 rounded hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all duration-fast"
                            title="删除"
                          >
                            <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive" />
                          </button>
                        </div>
                      ))}
                    </div>
                    {filteredSkills.length === 0 && (
                      <div className="text-center py-12 text-sm text-muted-foreground">暂无已安装的 Skill</div>
                    )}
                  </>
                )}

                {/* Subagent list */}
                {installedSubTabLoaded && installedSubTab === "agent" && (
                  <>
                    <div className={`grid ${isMobile ? "grid-cols-1" : "grid-cols-2"} gap-3`}>
                      {filteredAgents.map((agent) => (
                        <div
                          key={agent.id}
                          onClick={() => navigate(`/library/agent/${agent.id}`)}
                          className="surface-interactive p-4 cursor-pointer group relative"
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-9 h-9 rounded-lg bg-info/10 flex items-center justify-center shrink-0">
                              <Users className="w-4 h-4 text-info" />
                            </div>
                            <div className="min-w-0 flex-1 pr-8">
                              <h4 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors duration-fast">{agent.name}</h4>
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{agent.desc || "暂无描述"}</p>
                            </div>
                          </div>
                          <button
                            onClick={(e) => { e.stopPropagation(); deleteResource("agent", agent.id); }}
                            className="absolute top-3 right-3 p-1 rounded hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all duration-fast"
                            title="删除"
                          >
                            <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive" />
                          </button>
                        </div>
                      ))}
                    </div>
                    {filteredAgents.length === 0 && (
                      <div className="text-center py-12 text-sm text-muted-foreground">暂无已安装的 Subagent</div>
                    )}
                  </>
                )}

                {/* Sandbox template list */}
                {installedSubTabLoaded && installedSubTab === "sandbox-template" && (
                  <>
                    <div className={`grid ${isMobile ? "grid-cols-1" : "grid-cols-2"} gap-3`}>
                      {filteredSandboxTemplates.map((sandboxTemplate) => (
                        <div
                          key={sandboxTemplate.id}
                          onClick={() => navigate(`/library/sandbox-template/${sandboxTemplate.id}`)}
                          className="surface-interactive p-4 cursor-pointer group relative"
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                              <Box className="w-4 h-4 text-primary" />
                            </div>
                            <div className="min-w-0 flex-1 pr-8">
                              <h4 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors duration-fast">{sandboxTemplate.name}</h4>
                              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{sandboxTemplate.desc || "暂无描述"}</p>
                              <p className="text-2xs text-muted-foreground mt-2 font-mono truncate">
                                Sandbox · {sandboxTemplate.provider_name || sandboxTemplate.provider_type || "unknown"}
                              </p>
                            </div>
                          </div>
                          {!sandboxTemplate.builtin && (
                            <button
                              onClick={(e) => { e.stopPropagation(); deleteResource("sandbox-template", sandboxTemplate.id); }}
                              className="absolute top-3 right-3 p-1 rounded hover:bg-destructive/10 opacity-0 group-hover:opacity-100 transition-all duration-fast"
                              title="删除"
                            >
                              <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                    {filteredSandboxTemplates.length === 0 && (
                      <div className="text-center py-12 text-sm text-muted-foreground">暂无已安装的 Sandbox</div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* Update dialog */}
      {updateTarget && (
        <UpdateDialog
          open={updateDialogOpen}
          onOpenChange={setUpdateDialogOpen}
          agentId={updateTarget.agent.id}
          update={updateTarget.update}
          agentName={updateTarget.agent.name}
        />
      )}

      {recipeCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4" onClick={() => setRecipeCreateOpen(false)}>
          <div className="w-full max-w-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="mb-2 flex justify-end">
              <button
                type="button"
                aria-label="关闭"
                onClick={() => setRecipeCreateOpen(false)}
                className="rounded-full bg-card p-2 text-muted-foreground shadow-sm transition-colors hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <SandboxTemplateEditor
              item={null}
              providerOptions={recipeProviderOptions}
              onCreated={() => setRecipeCreateOpen(false)}
            />
          </div>
        </div>
      )}

    </div>
  );
}
