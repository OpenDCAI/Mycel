import { useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { postRun } from "../api";
import CenteredInputBox from "../components/CenteredInputBox";
import WorkspaceSetupModal from "../components/WorkspaceSetupModal";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";
import { useWorkspaceSettings } from "../hooks/use-workspace-settings";
import { useAuthStore } from "../store/auth-store";
import { useAppStore } from "../store/app-store";
import MemberAvatar from "../components/MemberAvatar";
import FilesystemBrowser from "../components/FilesystemBrowser";
import { listMyLeases } from "../api/client";
import type { UserLeaseSummary } from "../api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { cn } from "../lib/utils";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  setSessionsOpen: (value: boolean) => void;
}

export default function NewChatPage({ mode = "member" }: { mode?: "member" | "new" }) {
  const navigate = useNavigate();
  const { memberId } = useParams<{ memberId: string }>();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread, handleGetMainThread } = tm;
  const { settings, loading, hasWorkspace, refreshSettings } = useWorkspaceSettings();
  const shouldResolveMain = mode === "member";
  const [error, setError] = useState<string | null>(null);
  const [resolveState, setResolveState] = useState<"resolving" | "ready" | "error">(
    shouldResolveMain ? "resolving" : "ready",
  );
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);
  const [createMode, setCreateMode] = useState<"new" | "existing">("new");
  const [leaseOptions, setLeaseOptions] = useState<UserLeaseSummary[]>([]);
  const [leaseError, setLeaseError] = useState<string | null>(null);
  const [leaseLoading, setLeaseLoading] = useState(false);
  const [selectedLeaseId, setSelectedLeaseId] = useState<string>("");
  const [workspaceMode, setWorkspaceMode] = useState<"browse" | "recent" | "manual">("browse");
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);

  const authAgent = useAuthStore(s => s.agent);
  const memberList = useAppStore(s => s.memberList);
  const libraryRecipes = useAppStore(s => s.libraryRecipes);
  const decodedMemberId = memberId ? decodeURIComponent(memberId) : null;
  const resolvedMember = decodedMemberId ? memberList.find(m => m.id === decodedMemberId) : undefined;
  const isOwnedAgent = decodedMemberId === authAgent?.id;
  const memberName = resolvedMember?.name ?? (isOwnedAgent ? (authAgent?.name || "Agent") : "Agent");
  const memberAvatarUrl = resolvedMember?.avatar_url;

  useEffect(() => {
    if (!shouldResolveMain) return;

    let cancelled = false;

    async function resolveMainThread() {
      if (!decodedMemberId) {
        setError("Missing member ID");
        setResolveState("error");
        return;
      }

      try {
        const thread = await handleGetMainThread(decodedMemberId);
        if (cancelled) return;
        if (thread) {
          navigate(`/threads/${encodeURIComponent(decodedMemberId)}/${thread.thread_id}`, { replace: true });
          return;
        }
        setResolveState("ready");
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "Failed to resolve main thread";
        console.error("[NewChatPage] resolve main thread failed:", err);
        setError(message);
        setResolveState("error");
      }
    }

    void resolveMainThread();
    return () => {
      cancelled = true;
    };
  }, [decodedMemberId, handleGetMainThread, navigate, shouldResolveMain]);

  useEffect(() => {
    let cancelled = false;

    async function loadLeases() {
      setLeaseLoading(true);
      setLeaseError(null);
      try {
        const leases = await listMyLeases();
        if (cancelled) return;
        setLeaseOptions(leases);
        setSelectedLeaseId((current) => current || leases[0]?.lease_id || "");
      } catch (err) {
        if (cancelled) return;
        setLeaseError(err instanceof Error ? err.message : "Failed to load leases");
      } finally {
        if (!cancelled) setLeaseLoading(false);
      }
    }

    void loadLeases();
    return () => {
      cancelled = true;
    };
  }, []);

  const recipeOptions = libraryRecipes
    .filter((item) => item.available !== false && item.provider_name)
    .map((item) => ({
      value: item.id,
      label: item.name,
      providerName: item.provider_name as string,
    }));
  const selectedLease = leaseOptions.find((lease) => lease.lease_id === selectedLeaseId) ?? null;

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    if (createMode === "new" && sandbox === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }
    if (!decodedMemberId) {
      throw new Error("Cannot create thread without member ID");
    }

    let threadId: string;
    if (createMode === "existing") {
      if (!selectedLease) {
        throw new Error("Choose an existing sandbox first");
      }
      threadId = await handleCreateThread(
        selectedLease.provider_name,
        undefined,
        decodedMemberId,
        model,
        selectedLease.lease_id,
      );
    } else {
      const recipe = recipeOptions.find((item) => item.value === sandbox);
      if (!recipe) {
        throw new Error("Recipe not found");
      }
      const cwd = workspace || settings?.default_workspace || undefined;
      threadId = await handleCreateThread(recipe.providerName, cwd, decodedMemberId, model, undefined, recipe.value);
    }
    postRun(threadId, message, undefined, model ? { model } : undefined).catch(err => {
      console.error("[NewChatPage] postRun failed:", err);
    });
    navigate(`/threads/${encodeURIComponent(decodedMemberId)}/${threadId}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  async function handleWorkspaceSet() {
    await refreshSettings();
    setShowWorkspaceSetup(false);
  }

  function summarizeEnvironment(sandboxValue: string, workspaceValue: string) {
    if (createMode === "existing") {
      if (!selectedLease) return "复用旧沙盒";
      return `${selectedLease.provider_name} · ${selectedLease.recipe_name}`;
    }
    const recipe = recipeOptions.find((item) => item.value === sandboxValue);
    if (!recipe) return "选择 recipe";
    if (recipe.providerName !== "local") return recipe.label;
    const activeWorkspace = workspaceValue || settings?.default_workspace || "";
    if (!activeWorkspace) return `${recipe.label} · 选择工作区`;
    const parts = activeWorkspace.split("/").filter(Boolean);
    return `${recipe.label} · ${parts.at(-1) ?? activeWorkspace}`;
  }

  if (loading || resolveState === "resolving") {
    return (
      <div className="flex-1 flex items-center justify-center relative">
        <div className="w-full max-w-[420px] px-6 text-center">
          <div className="flex justify-center mb-4">
            <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-xl font-medium text-foreground mb-2">
            正在检查 {memberName} 的主对话
          </h1>
          <p className="text-sm text-muted-foreground">
            如果没有主对话，这里会进入创建界面。
          </p>
        </div>
      </div>
    );
  }

  if (resolveState === "error") {
    return (
      <div className="flex-1 flex items-center justify-center relative">
        <div className="w-full max-w-[420px] px-6 text-center">
          <div className="flex justify-center mb-4">
            <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-xl font-medium text-foreground mb-2">
            无法检查 {memberName} 的主对话
          </h1>
          <p className="text-sm text-destructive">
            {error ?? "Unknown error"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex items-center justify-center relative">
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-[600px] px-4">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4">
            <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-2xl font-medium text-foreground mb-2">
            你好，我是 {memberName}
          </h1>
          <p className="text-sm text-muted-foreground mb-6">
            {mode === "new"
              ? `为 ${memberName} 创建一个新对话`
              : isOwnedAgent
                ? "你的通用数字成员，随时准备为你工作"
                : `${memberName} 准备为你工作`}
          </p>

          <div className="flex flex-wrap justify-center gap-2">
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              文件操作
            </div>
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              代码探索
            </div>
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              命令执行
            </div>
            <div className="px-3 py-1.5 bg-card border border-border rounded-lg text-xs text-muted-foreground">
              信息检索
            </div>
          </div>
        </div>

        <CenteredInputBox
          sandboxTypes={sandboxTypes}
          defaultSandbox={createMode === "new" ? (recipeOptions[0]?.value ?? selectedSandbox) : (selectedLease?.provider_name ?? selectedSandbox)}
          defaultWorkspace={settings?.default_workspace || undefined}
          workspaceSelectionEnabled={false}
          defaultModel={settings?.default_model || "leon:large"}
          recentWorkspaces={settings?.recent_workspaces || []}
          environmentControl={{
            renderSummary: ({ sandbox, workspace }) => summarizeEnvironment(sandbox, workspace),
            renderPanel: ({ sandbox, setSandbox, workspace, setWorkspace, customWorkspace, setCustomWorkspace, persistWorkspace }) => {
              const activeRecipe = recipeOptions.find((item) => item.value === sandbox) ?? recipeOptions[0] ?? null;
              const localWorkspace = workspace || settings?.default_workspace || "";

              return (
                <div className="space-y-4">
                  <div className="grid gap-2 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => setCreateMode("new")}
                      className={cn(
                        "rounded-2xl border px-4 py-3 text-left transition-colors",
                        createMode === "new"
                          ? "border-foreground/30 bg-accent/60"
                          : "border-border bg-card hover:bg-accent/30",
                      )}
                    >
                      <div className="text-sm font-medium text-foreground">New sandbox</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Start a fresh sandbox from the current recipe.
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => setCreateMode("existing")}
                      className={cn(
                        "rounded-2xl border px-4 py-3 text-left transition-colors",
                        createMode === "existing"
                          ? "border-foreground/30 bg-accent/60"
                          : "border-border bg-card hover:bg-accent/30",
                      )}
                    >
                      <div className="text-sm font-medium text-foreground">Existing sandbox</div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Reuse one of your current leases.
                      </div>
                    </button>
                  </div>

                  {createMode === "new" ? (
                    <div className="space-y-4">
                      {activeRecipe?.providerName === "local" ? (
                        <div className="rounded-2xl border border-border bg-background/70 p-3">
                          <div className="grid gap-3 md:grid-cols-[200px_minmax(0,1fr)_auto] md:items-end">
                            <div>
                              <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Recipe</div>
                              <Select value={sandbox} onValueChange={setSandbox}>
                                <SelectTrigger className="h-10 text-sm">
                                  <SelectValue placeholder="Choose a recipe" />
                                </SelectTrigger>
                                <SelectContent>
                                  {recipeOptions.map((item) => (
                                    <SelectItem key={item.value} value={item.value}>
                                      {item.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>

                            <div className="min-w-0">
                              <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Workspace</div>
                              <div
                                className="flex h-10 items-center rounded-xl border border-border bg-card px-3 text-sm text-foreground"
                                title={localWorkspace || "Choose a workspace before sending"}
                              >
                                <span className="truncate">
                                  {localWorkspace || "Choose a workspace before sending"}
                                </span>
                              </div>
                            </div>

                            <Popover open={workspacePickerOpen} onOpenChange={setWorkspacePickerOpen}>
                              <PopoverTrigger asChild>
                                <Button type="button" variant="outline" className="h-10 px-4">
                                  选择目录
                                </Button>
                              </PopoverTrigger>
                              <PopoverContent align="end" className="w-[520px] p-3">
                                <div className="mb-3 flex items-center gap-3">
                                  <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Source</div>
                                  <Select
                                    value={workspaceMode}
                                    onValueChange={(value) => setWorkspaceMode(value as "browse" | "recent" | "manual")}
                                  >
                                    <SelectTrigger className="h-9 w-[160px] text-sm">
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      <SelectItem value="browse">Browse</SelectItem>
                                      <SelectItem value="recent">Recent</SelectItem>
                                      <SelectItem value="manual">Manual</SelectItem>
                                    </SelectContent>
                                  </Select>
                                </div>

                                <div className="min-h-[280px]">
                                  {workspaceMode === "browse" && (
                                    <FilesystemBrowser
                                      onSelect={(path) => {
                                        setWorkspace(path);
                                        setCustomWorkspace("");
                                        setWorkspacePickerOpen(false);
                                        void persistWorkspace(path);
                                      }}
                                      initialPath={localWorkspace || "~"}
                                    />
                                  )}

                                  {workspaceMode === "recent" && (
                                    <div className="space-y-1">
                                      {(settings?.recent_workspaces || []).length > 0 ? (
                                        (settings?.recent_workspaces || []).map((path) => (
                                          <button
                                            key={path}
                                            type="button"
                                            onClick={() => {
                                              setWorkspace(path);
                                              setCustomWorkspace("");
                                              setWorkspacePickerOpen(false);
                                              void persistWorkspace(path);
                                            }}
                                            className="w-full rounded-xl border border-border bg-card px-3 py-2 text-left text-sm hover:bg-accent"
                                          >
                                            {path}
                                          </button>
                                        ))
                                      ) : (
                                        <div className="rounded-xl border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                                          暂无最近工作区
                                        </div>
                                      )}
                                    </div>
                                  )}

                                  {workspaceMode === "manual" && (
                                    <div className="flex gap-2">
                                      <Input
                                        value={customWorkspace}
                                        onChange={(e) => setCustomWorkspace(e.target.value)}
                                        placeholder="例如: ~/Projects"
                                        className="h-9"
                                      />
                                      <Button
                                        type="button"
                                        size="sm"
                                        disabled={!customWorkspace.trim()}
                                        onClick={() => {
                                          const path = customWorkspace.trim();
                                          if (!path) return;
                                          setWorkspace(path);
                                          setWorkspacePickerOpen(false);
                                          void persistWorkspace(path);
                                        }}
                                      >
                                        保存
                                      </Button>
                                    </div>
                                  )}
                                </div>
                              </PopoverContent>
                            </Popover>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Recipe</div>
                          <Select value={sandbox} onValueChange={setSandbox}>
                            <SelectTrigger className="h-10 text-sm">
                              <SelectValue placeholder="Choose a recipe" />
                            </SelectTrigger>
                            <SelectContent>
                              {recipeOptions.map((item) => (
                                <SelectItem key={item.value} value={item.value}>
                                  {item.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">My Leases</div>
                      <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
                        {leaseOptions.map((lease) => {
                          const isActive = selectedLeaseId === lease.lease_id;
                          return (
                            <button
                              key={lease.lease_id}
                              type="button"
                              onClick={() => setSelectedLeaseId(lease.lease_id)}
                              className={cn(
                                "w-full rounded-2xl border p-3 text-left transition-colors",
                                isActive ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:bg-accent/40",
                              )}
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="text-sm font-medium text-foreground">
                                    {lease.provider_name} · {lease.recipe_name}
                                  </div>
                                  <div className="mt-1 text-xs text-muted-foreground">
                                    {lease.cwd || "No working directory"}
                                  </div>
                                </div>
                                <div className="flex -space-x-2">
                                  {lease.agents.slice(0, 4).map((agent) => (
                                    <MemberAvatar
                                      key={agent.member_id}
                                      name={agent.member_name}
                                      avatarUrl={agent.avatar_url ?? undefined}
                                      type="mycel_agent"
                                      size="xs"
                                      className="ring-2 ring-background"
                                    />
                                  ))}
                                </div>
                              </div>
                            </button>
                          );
                        })}
                        {!leaseLoading && leaseOptions.length === 0 && (
                          <div className="rounded-2xl border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                            You do not have any reusable sandboxes yet.
                          </div>
                        )}
                      </div>
                      {leaseError && <p className="mt-2 text-xs text-destructive">{leaseError}</p>}
                    </div>
                  )}
                </div>
              );
            },
          }}
          onSend={handleSend}
        />
      </div>

      <WorkspaceSetupModal
        open={showWorkspaceSetup}
        onClose={() => setShowWorkspaceSetup(false)}
        onWorkspaceSet={() => {
          void handleWorkspaceSet();
        }}
      />
    </div>
  );
}
