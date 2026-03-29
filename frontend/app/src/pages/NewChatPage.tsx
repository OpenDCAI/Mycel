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
import { cn } from "../lib/utils";
import { ArrowLeft } from "lucide-react";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  setSessionsOpen: (value: boolean) => void;
}

const PROVIDER_TYPE_LABELS: Record<string, string> = {
  local: "Local",
  daytona: "Daytona",
  docker: "Docker",
  e2b: "E2B",
  agentbay: "AgentBay",
};

function providerTypeFromName(name: string): string {
  if (name.startsWith("daytona")) return "daytona";
  if (name.startsWith("docker")) return "docker";
  if (name.startsWith("e2b")) return "e2b";
  if (name.startsWith("agentbay")) return "agentbay";
  return "local";
}

function defaultRecipeIdForProvider(providerName: string): string {
  return `${providerName}:default`;
}

function larkCliRecipeIdForProvider(providerName: string): string {
  return `${providerName}:lark-cli`;
}

function baseRecipeId(recipeId: string): string {
  return recipeId.endsWith(":lark-cli") ? recipeId.replace(/:lark-cli$/, ":default") : recipeId;
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
  const [draftCreateMode, setDraftCreateMode] = useState<"new" | "existing">("new");
  const [leaseOptions, setLeaseOptions] = useState<UserLeaseSummary[]>([]);
  const [leaseError, setLeaseError] = useState<string | null>(null);
  const [leaseLoading, setLeaseLoading] = useState(false);
  const [selectedLeaseId, setSelectedLeaseId] = useState<string>("");
  const [draftSelectedLeaseId, setDraftSelectedLeaseId] = useState<string>("");
  const [selectedRecipeId, setSelectedRecipeId] = useState<string>("");
  const [draftRecipeId, setDraftRecipeId] = useState<string>("");
  const [draftProviderType, setDraftProviderType] = useState<string>("");
  const [draftLarkCliEnabled, setDraftLarkCliEnabled] = useState(false);
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("");
  const [draftWorkspace, setDraftWorkspace] = useState<string>("");
  const [draftCustomWorkspace, setDraftCustomWorkspace] = useState<string>("");
  const [workspaceMode, setWorkspaceMode] = useState<"browse" | "recent" | "manual">("browse");
  const [configStep, setConfigStep] = useState<1 | 2>(1);

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
      providerType: providerTypeFromName(item.provider_name as string),
      configurableFeatures: (item as { configurable_features?: Record<string, boolean> }).configurable_features ?? {},
    }));
  const selectedLease = leaseOptions.find((lease) => lease.lease_id === selectedLeaseId) ?? null;
  const providerTypeOptions = Array.from(new Set(recipeOptions.map((item) => item.providerType)))
    .map((value) => ({
      value,
      label: PROVIDER_TYPE_LABELS[value] ?? value,
    }));
  useEffect(() => {
    if (!selectedRecipeId && recipeOptions[0]?.value) {
      setSelectedRecipeId(recipeOptions[0].value);
    }
  }, [recipeOptions, selectedRecipeId]);

  useEffect(() => {
    if (!selectedLeaseId && leaseOptions[0]?.lease_id) {
      setSelectedLeaseId(leaseOptions[0].lease_id);
    }
  }, [leaseOptions, selectedLeaseId]);

  useEffect(() => {
    if (!selectedWorkspace && settings?.default_workspace) {
      setSelectedWorkspace(settings.default_workspace);
    }
  }, [selectedWorkspace, settings?.default_workspace]);

  async function handleSend(message: string, sandbox: string, model: string, workspace?: string) {
    const activeRecipe = recipeOptions.find((item) => item.value === baseRecipeId(sandbox));
    if (createMode === "new" && activeRecipe?.providerName === "local" && !workspace && !hasWorkspace) {
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
      const recipe = recipeOptions.find((item) => item.value === baseRecipeId(sandbox));
      if (!recipe) {
        throw new Error("Recipe not found");
      }
      const cwd = workspace || settings?.default_workspace || undefined;
      threadId = await handleCreateThread(recipe.providerName, cwd, decodedMemberId, model, undefined, sandbox);
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
    const activeRecipeId = baseRecipeId(selectedRecipeId || sandboxValue);
    const recipe = recipeOptions.find((item) => item.value === activeRecipeId);
    if (!recipe) return "选择 recipe";
    const larkSuffix = (selectedRecipeId || sandboxValue).endsWith(":lark-cli") ? " · Lark CLI" : "";
    if (recipe.providerName !== "local") return `${recipe.label}${larkSuffix}`;
    const activeWorkspace = selectedWorkspace || workspaceValue || settings?.default_workspace || "";
    if (!activeWorkspace) return `${recipe.label}${larkSuffix} · 选择工作区`;
    const parts = activeWorkspace.split("/").filter(Boolean);
    return `${recipe.label}${larkSuffix} · ${parts.at(-1) ?? activeWorkspace}`;
  }

  function openDraftConfig() {
    const activeRecipe = recipeOptions.find((item) => item.value === baseRecipeId(selectedRecipeId)) ?? recipeOptions[0];
    setDraftCreateMode(createMode);
    setDraftSelectedLeaseId(selectedLeaseId || leaseOptions[0]?.lease_id || "");
    setDraftRecipeId(activeRecipe?.value || "");
    setDraftProviderType(
      activeRecipe?.providerType || "",
    );
    setDraftLarkCliEnabled(selectedRecipeId.endsWith(":lark-cli"));
    setDraftWorkspace(selectedWorkspace || settings?.default_workspace || "");
    setDraftCustomWorkspace("");
    setWorkspaceMode("browse");
    setConfigStep(1);
  }

  function cancelDraftConfig() {
    const activeRecipe = recipeOptions.find((item) => item.value === baseRecipeId(selectedRecipeId)) ?? recipeOptions[0];
    setDraftCreateMode(createMode);
    setDraftSelectedLeaseId(selectedLeaseId || leaseOptions[0]?.lease_id || "");
    setDraftRecipeId(activeRecipe?.value || "");
    setDraftProviderType(
      activeRecipe?.providerType || "",
    );
    setDraftLarkCliEnabled(selectedRecipeId.endsWith(":lark-cli"));
    setDraftWorkspace(selectedWorkspace || settings?.default_workspace || "");
    setDraftCustomWorkspace("");
    setWorkspaceMode("browse");
    setConfigStep(1);
  }

  async function applyDraftConfig() {
    if (configStep === 1) {
      setConfigStep(2);
      return false;
    }

    setCreateMode(draftCreateMode);
    setSelectedLeaseId(draftSelectedLeaseId);
    const activeRecipe = recipeOptions.find((item) => item.value === draftRecipeId) ?? recipeOptions[0] ?? null;
    if (activeRecipe) {
      setSelectedRecipeId(
        draftLarkCliEnabled
          ? larkCliRecipeIdForProvider(activeRecipe.providerName)
          : defaultRecipeIdForProvider(activeRecipe.providerName),
      );
    }
    const nextWorkspace = draftWorkspace || settings?.default_workspace || "";
    setSelectedWorkspace(nextWorkspace);
    setConfigStep(1);
    if (draftCreateMode === "new" && draftRecipeId.startsWith("local:") && nextWorkspace) {
      await fetch("/api/settings/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: nextWorkspace }),
      });
    }
    return true;
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
          defaultSandbox={createMode === "new" ? (selectedRecipeId || (recipeOptions[0]?.value ?? selectedSandbox)) : (selectedLease?.provider_name ?? selectedSandbox)}
          defaultWorkspace={selectedWorkspace || settings?.default_workspace || undefined}
          workspaceSelectionEnabled={false}
          defaultModel={settings?.default_model || "leon:large"}
          recentWorkspaces={settings?.recent_workspaces || []}
          environmentControl={{
            isDetailView: configStep === 2,
            panelClassName:
              configStep === 2 && draftCreateMode === "new" && (recipeOptions.find((item) => item.value === draftRecipeId)?.providerType === "local")
                ? "h-[560px] max-h-[calc(100vh-4rem)]"
                : "max-h-[calc(100vh-4rem)]",
            applyLabel: configStep === 1 ? "下一步" : "确认",
            renderSummary: ({ sandbox, workspace }) => summarizeEnvironment(sandbox, workspace),
            onOpen: openDraftConfig,
            onCancel: cancelDraftConfig,
            onApply: applyDraftConfig,
            renderPanel: () => {
              const activeRecipe = recipeOptions.find((item) => item.value === draftRecipeId) ?? recipeOptions[0] ?? null;
              const filteredRecipeOptions = draftProviderType
                ? recipeOptions.filter((item) => item.providerType === draftProviderType)
                : recipeOptions;
              const filteredLeaseOptions = draftProviderType
                ? leaseOptions.filter((lease) => providerTypeFromName(lease.provider_name) === draftProviderType)
                : leaseOptions;
              const localWorkspace = draftWorkspace || settings?.default_workspace || "";
              const showWorkspaceStep = configStep === 2 && draftCreateMode === "new" && activeRecipe?.providerType === "local";
              const showExistingStep = configStep === 2 && draftCreateMode === "existing";
              const showRecipeDetailsStep = configStep === 2 && draftCreateMode === "new";
              const canToggleLarkCli = Boolean(activeRecipe?.configurableFeatures.lark_cli);

              return (
                <div className="space-y-4">
                  {showWorkspaceStep ? (
                    <div className="flex min-h-0 flex-1 flex-col">
                      <div className="mb-4 flex items-center justify-between">
                        <button
                          type="button"
                          onClick={() => setConfigStep(1)}
                          className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
                        >
                          <ArrowLeft className="h-4 w-4" />
                          返回上一步
                        </button>
                        {canToggleLarkCli && (
                          <label className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 text-sm">
                            <input
                              type="checkbox"
                              checked={draftLarkCliEnabled}
                              onChange={(event) => setDraftLarkCliEnabled(event.target.checked)}
                            />
                            启用 Lark CLI
                          </label>
                        )}
                      </div>

                      <div className="mb-4 grid gap-3 md:grid-cols-[minmax(0,1fr)_160px]">
                        <div className="rounded-2xl border border-border bg-card px-3 py-3">
                          <div className="mb-1 text-xs uppercase tracking-[0.18em] text-muted-foreground">Workspace</div>
                          <div className="truncate text-sm text-foreground">{localWorkspace || "Choose a workspace"}</div>
                        </div>
                        <Select
                          value={workspaceMode}
                          onValueChange={(value) => setWorkspaceMode(value as "browse" | "recent" | "manual")}
                        >
                          <SelectTrigger className="h-11 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="browse">Browse</SelectItem>
                            <SelectItem value="recent">Recent</SelectItem>
                            <SelectItem value="manual">Manual</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-border bg-background/70 p-3">
                        {workspaceMode === "browse" && (
                          <FilesystemBrowser
                            onSelect={(path) => {
                              setDraftWorkspace(path);
                              setDraftCustomWorkspace("");
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
                                    setDraftWorkspace(path);
                                    setDraftCustomWorkspace("");
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
                              value={draftCustomWorkspace}
                              onChange={(e) => setDraftCustomWorkspace(e.target.value)}
                              placeholder="例如: ~/Projects"
                              className="h-9"
                            />
                            <Button
                              type="button"
                              size="sm"
                              disabled={!draftCustomWorkspace.trim()}
                              onClick={() => {
                                const path = draftCustomWorkspace.trim();
                                if (!path) return;
                                setDraftWorkspace(path);
                              }}
                            >
                              保存
                            </Button>
                          </div>
                        )}
                      </div>
                    </div>
                  ) : showExistingStep ? (
                    <div className="space-y-4">
                      <button
                        type="button"
                        onClick={() => setConfigStep(1)}
                        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
                      >
                        <ArrowLeft className="h-4 w-4" />
                        返回上一步
                      </button>
                      <div className="space-y-2">
                        <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">My Leases</div>
                        <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
                          {filteredLeaseOptions.map((lease) => {
                            const isActive = draftSelectedLeaseId === lease.lease_id;
                            return (
                              <button
                                key={lease.lease_id}
                                type="button"
                                onClick={() => setDraftSelectedLeaseId(lease.lease_id)}
                                className={cn(
                                  "w-full rounded-2xl border p-3 text-left transition-colors",
                                  isActive ? "border-primary/40 bg-primary/5" : "border-border bg-card hover:bg-accent/40",
                                )}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <div className="text-sm font-medium text-foreground">
                                      {PROVIDER_TYPE_LABELS[providerTypeFromName(lease.provider_name)] ?? lease.provider_name} · {lease.recipe_name}
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
                          {!leaseLoading && filteredLeaseOptions.length === 0 && (
                            <div className="rounded-2xl border border-dashed border-border px-3 py-4 text-sm text-muted-foreground">
                              You do not have any reusable sandboxes yet.
                            </div>
                          )}
                        </div>
                        {leaseError && <p className="mt-2 text-xs text-destructive">{leaseError}</p>}
                      </div>
                    </div>
                  ) : showRecipeDetailsStep ? (
                    <div className="space-y-4">
                      <button
                        type="button"
                        onClick={() => setConfigStep(1)}
                        className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
                      >
                        <ArrowLeft className="h-4 w-4" />
                        返回上一步
                      </button>
                      <div className="rounded-2xl border border-border bg-background/70 p-4">
                        <div className="text-sm font-medium text-foreground">{activeRecipe?.label ?? "选择 recipe"}</div>
                        <div className="mt-2 text-sm text-muted-foreground">
                          {PROVIDER_TYPE_LABELS[activeRecipe?.providerType ?? "local"] ?? activeRecipe?.providerName}
                          {" "}会基于这个默认 recipe 创建新的 sandbox。
                        </div>
                      </div>
                      {canToggleLarkCli && (
                        <button
                          type="button"
                          onClick={() => setDraftLarkCliEnabled((current) => !current)}
                          className={cn(
                            "w-full rounded-2xl border px-4 py-3 text-left transition-colors",
                            draftLarkCliEnabled
                              ? "border-foreground/30 bg-accent/60"
                              : "border-border bg-card hover:bg-accent/30",
                          )}
                        >
                          <div className="text-sm font-medium text-foreground">Lark CLI</div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            {draftLarkCliEnabled ? "将在 sandbox 初始化时懒安装并校验。": "保持默认环境，不注入 Lark CLI。"}
                          </div>
                        </button>
                      )}
                      <div className="rounded-2xl border border-dashed border-border px-4 py-3 text-sm text-muted-foreground">
                        {draftLarkCliEnabled
                          ? "确认后，这次 thread 会使用开启了 Lark CLI 的 recipe 变体。"
                          : "确认后，这次 thread 会使用默认 recipe。"}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="grid gap-2 sm:grid-cols-2">
                        <button
                          type="button"
                          onClick={() => setDraftCreateMode("new")}
                          className={cn(
                            "rounded-2xl border px-4 py-3 text-left transition-colors",
                            draftCreateMode === "new"
                              ? "border-foreground/30 bg-accent/60"
                              : "border-border bg-card hover:bg-accent/30",
                          )}
                        >
                          <div className="text-sm font-medium text-foreground">New sandbox</div>
                          <div className="mt-1 text-xs text-muted-foreground">
                            Start a fresh sandbox from a default recipe.
                          </div>
                        </button>
                        <button
                          type="button"
                          onClick={() => setDraftCreateMode("existing")}
                          className={cn(
                            "rounded-2xl border px-4 py-3 text-left transition-colors",
                            draftCreateMode === "existing"
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

                      <div className={cn("grid gap-4", draftCreateMode === "new" ? "sm:grid-cols-2" : "sm:grid-cols-1")}>
                        <div>
                          <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Provider</div>
                          <Select
                            value={draftProviderType || "__all__"}
                            onValueChange={(value) => {
                              const nextProvider = value === "__all__" ? "" : value;
                              setDraftProviderType(nextProvider);
                              const nextRecipes = nextProvider
                                ? recipeOptions.filter((item) => item.providerType === nextProvider)
                                : recipeOptions;
                              if (nextRecipes.length > 0 && !nextRecipes.some((item) => item.value === draftRecipeId)) {
                                setDraftRecipeId(nextRecipes[0].value);
                                setDraftLarkCliEnabled(false);
                              }
                            }}
                          >
                            <SelectTrigger className="h-10 text-sm">
                              <SelectValue placeholder="All providers" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__all__">All providers</SelectItem>
                              {providerTypeOptions.map((item) => (
                                <SelectItem key={item.value} value={item.value}>
                                  {item.label}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>

                        {draftCreateMode === "new" && (
                          <div>
                            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Recipe</div>
                            <Select
                              value={draftRecipeId}
                              onValueChange={(value) => {
                                setDraftRecipeId(value);
                                setDraftLarkCliEnabled(false);
                              }}
                            >
                              <SelectTrigger className="h-10 text-sm">
                                <SelectValue placeholder="Choose a recipe" />
                              </SelectTrigger>
                              <SelectContent>
                                {filteredRecipeOptions.map((item) => (
                                  <SelectItem key={item.value} value={item.value}>
                                    {item.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}
                      </div>
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
