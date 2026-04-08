import { useEffect, useMemo, useState } from "react";
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
import { getDefaultThreadConfig, listMyLeases, saveDefaultThreadConfig } from "../api/client";
import type { RecipeFeatureOption, RecipeSnapshot, ThreadLaunchConfig, UserLeaseSummary } from "../api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import { cn } from "../lib/utils";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (value: boolean) => void;
  setSessionsOpen: (value: boolean) => void;
}

function ResolveStateCard({
  memberName,
  memberAvatarUrl,
  title,
  description,
  destructive = false,
}: {
  memberName: string;
  memberAvatarUrl?: string;
  title: string;
  description: string;
  destructive?: boolean;
}) {
  return (
    <div className="flex-1 flex items-center justify-center relative">
      <div className="w-full max-w-[420px] px-6 text-center">
        <div className="flex justify-center mb-4">
          <MemberAvatar name={memberName} avatarUrl={memberAvatarUrl} type="mycel_agent" size="lg" />
        </div>
        <h1 className="text-xl font-medium text-foreground mb-2">{title}</h1>
        <p className={`text-sm ${destructive ? "text-destructive" : "text-muted-foreground"}`}>
          {description}
        </p>
      </div>
    </div>
  );
}

const PROVIDER_TYPE_LABELS: Record<string, string> = {
  local: "Local",
  daytona: "Daytona",
  docker: "Docker",
  e2b: "E2B",
  agentbay: "AgentBay",
};

const MODEL_OPTIONS = [
  { value: "leon:mini", label: "Mini" },
  { value: "leon:medium", label: "Medium" },
  { value: "leon:large", label: "Large" },
  { value: "leon:max", label: "Max" },
] as const;

type ConfigSnapshot = {
  createMode: "new" | "existing";
  selectedLeaseId: string;
  selectedRecipeId: string;
  selectedRecipeFeatures: Record<string, boolean>;
  selectedWorkspace: string;
  selectedProviderConfig: string;
};

function providerConfigLabel(name: string): string {
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function providerTypeFromName(name: string): string {
  if (name.startsWith("daytona")) return "daytona";
  if (name.startsWith("docker")) return "docker";
  if (name.startsWith("e2b")) return "e2b";
  if (name.startsWith("agentbay")) return "agentbay";
  return "local";
}

function leaseStateMeta(state?: string | null): { dot: string; label: string } {
  switch (state) {
    case "running":
    case "started":
      return { dot: "bg-emerald-500", label: "运行中" };
    case "paused":
    case "stopped":
      return { dot: "bg-amber-500", label: "已暂停" };
    case "error":
    case "failed":
      return { dot: "bg-rose-500", label: "异常" };
    default:
      return { dot: "bg-zinc-400", label: "未知" };
  }
}

function enabledFeatureLabels(recipe: RecipeSnapshot | null): string[] {
  if (!recipe?.feature_options?.length) return [];
  return recipe.feature_options
    .filter((item) => recipe.features?.[item.key])
    .map((item) => item.name);
}

export default function NewChatPage({ mode = "member" }: { mode?: "member" | "new" }) {
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId: string }>();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread, handleGetDefaultThread } = tm;
  const { settings, loading, hasWorkspace, refreshSettings, setDefaultWorkspace } = useWorkspaceSettings();
  const shouldResolveDefaultThread = mode === "member";
  const [error, setError] = useState<string | null>(null);
  const [resolveState, setResolveState] = useState<"resolving" | "ready" | "error">(
    shouldResolveDefaultThread ? "resolving" : "ready",
  );
  const [showWorkspaceSetup, setShowWorkspaceSetup] = useState(false);
  const [createMode, setCreateMode] = useState<"new" | "existing">("new");
  const [leaseOptions, setLeaseOptions] = useState<UserLeaseSummary[]>([]);
  const [leaseError, setLeaseError] = useState<string | null>(null);
  const [leaseLoading, setLeaseLoading] = useState(true);
  const [selectedLeaseId, setSelectedLeaseId] = useState<string>("");
  const [selectedRecipeId, setSelectedRecipeId] = useState<string>("");
  const [selectedRecipeFeatures, setSelectedRecipeFeatures] = useState<Record<string, boolean>>({});
  const [selectedProviderConfig, setSelectedProviderConfig] = useState<string>("");
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [configStep, setConfigStep] = useState<1 | 2 | 3>(1);
  const [createModeInitialized, setCreateModeInitialized] = useState(false);
  const [configDefaultsLoading, setConfigDefaultsLoading] = useState(true);
  const [configSnapshot, setConfigSnapshot] = useState<ConfigSnapshot | null>(null);

  const authAgent = useAuthStore(s => s.agent);
  const agentList = useAppStore(s => s.agentList);
  const libraryRecipes = useAppStore(s => s.libraryRecipes);
  const decodedAgentId = agentId ? decodeURIComponent(agentId) : null;
  const resolvedMember = decodedAgentId ? agentList.find(m => m.id === decodedAgentId) : undefined;
  const isOwnedAgent = decodedAgentId === authAgent?.id;
  const memberName = resolvedMember?.name ?? (isOwnedAgent ? (authAgent?.name || "Agent") : "Agent");
  const memberAvatarUrl = resolvedMember?.avatar_url;

  useEffect(() => {
    if (!shouldResolveDefaultThread) return;

    let cancelled = false;
    const ac = new AbortController();

    async function resolveDefaultThread() {
      if (!decodedAgentId) {
        setError("Missing agent ID");
        setResolveState("error");
        return;
      }

      try {
        const thread = await handleGetDefaultThread(decodedAgentId, ac.signal);
        if (cancelled) return;
        if (thread) {
          navigate(`/chat/hire/thread/${thread.thread_id}`, { replace: true });
          return;
        }
        setResolveState("ready");
      } catch (err) {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        const message = err instanceof Error ? err.message : "无法获取默认线程";
        console.error("[NewChatPage] resolve default thread failed:", err);
        setError(message);
        setResolveState("error");
      }
    }

    void resolveDefaultThread();
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, [decodedAgentId, handleGetDefaultThread, navigate, shouldResolveDefaultThread]);

  useEffect(() => {
    let cancelled = false;
    const ac = new AbortController();

    async function loadLeases() {
      setLeaseLoading(true);
      setLeaseError(null);
      try {
        const leases = await listMyLeases(ac.signal);
        if (cancelled) return;
        setLeaseOptions(leases);
        setSelectedLeaseId((current) => current || leases[0]?.lease_id || "");
      } catch (err) {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setLeaseError(err instanceof Error ? err.message : "Failed to load leases");
      } finally {
        if (!cancelled && !ac.signal.aborted) setLeaseLoading(false);
      }
    }

    void loadLeases();
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, []);

  const recipeOptions = useMemo(() => (
    libraryRecipes
      .filter((item) => item.available !== false && item.provider_type)
      .map((item) => ({
        value: item.id,
        label: item.name,
        recipe: {
          id: item.id,
          name: item.name,
          desc: item.desc,
          provider_type: item.provider_type as string,
          features: (item as { features?: Record<string, boolean> }).features ?? {},
          configurable_features: (item as { configurable_features?: Record<string, boolean> }).configurable_features ?? {},
          feature_options: (item as { feature_options?: RecipeFeatureOption[] }).feature_options ?? [],
        } satisfies RecipeSnapshot,
      }))
  ), [libraryRecipes]);
  const selectedLease = leaseOptions.find((lease) => lease.lease_id === selectedLeaseId) ?? null;
  const providerConfigOptions = useMemo(
    () =>
      sandboxTypes
        .filter((item) => item.available)
        .map((item) => ({
          value: item.name,
          label: providerConfigLabel(item.name),
          providerType: item.provider || providerTypeFromName(item.name),
        })),
    [sandboxTypes],
  );
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
    if (createModeInitialized || leaseLoading) return;
    setCreateMode(leaseOptions.length > 0 ? "existing" : "new");
    setCreateModeInitialized(true);
  }, [createModeInitialized, leaseLoading, leaseOptions.length]);

  useEffect(() => {
    if (leaseLoading || configDefaultsLoading) return;
    if (selectedProviderConfig) return;
    const nextConfig = leaseOptions[0]?.provider_name || providerConfigOptions[0]?.value || selectedSandbox || "local";
    if (nextConfig) setSelectedProviderConfig(nextConfig);
  }, [configDefaultsLoading, leaseLoading, leaseOptions, providerConfigOptions, selectedProviderConfig, selectedSandbox]);

  useEffect(() => {
    if (!selectedWorkspace && settings?.default_workspace) {
      setSelectedWorkspace(settings.default_workspace);
    }
  }, [selectedWorkspace, settings?.default_workspace]);

  useEffect(() => {
    if (!decodedAgentId) {
      setConfigDefaultsLoading(false);
      return;
    }
    const agentIdForDefaults = decodedAgentId;
    let cancelled = false;
    const ac = new AbortController();

    async function loadDefaultConfig() {
      setConfigDefaultsLoading(true);
      try {
        const payload = await getDefaultThreadConfig(agentIdForDefaults, ac.signal);
        if (cancelled) return;
        applyResolvedConfig(payload.config);
        setCreateModeInitialized(true);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        console.error("[NewChatPage] load default thread config failed:", err);
      } finally {
        if (!cancelled && !ac.signal.aborted) setConfigDefaultsLoading(false);
      }
    }

    void loadDefaultConfig();
    return () => {
      cancelled = true;
      ac.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [decodedAgentId]);

  const selectedRecipe = useMemo(
    () => recipeOptions.find((item) => item.value === selectedRecipeId)?.recipe ?? recipeOptions[0]?.recipe ?? null,
    [recipeOptions, selectedRecipeId],
  );
  useEffect(() => {
    if (!selectedRecipe) return;
    setSelectedRecipeFeatures(selectedRecipe.features ?? {});
  }, [selectedRecipeId, selectedRecipe]);

  const selectedRecipeSnapshot = selectedRecipe
    ? {
      ...selectedRecipe,
      features: { ...(selectedRecipe.features ?? {}), ...selectedRecipeFeatures },
    }
    : null;
  const activeWorkspace = selectedWorkspace || settings?.default_workspace || "";
  const localRecipeSelected = createMode === "new" && selectedRecipe?.provider_type === "local";
  const workspaceRequired = createMode === "new"
    && selectedRecipe?.provider_type === "local"
    && !activeWorkspace;

  async function handleSend(message: string, model: string) {
    const workspace = selectedWorkspace || settings?.default_workspace || undefined;
    if (createMode === "new" && selectedRecipeSnapshot?.provider_type === "local" && !workspace && !hasWorkspace) {
      setShowWorkspaceSetup(true);
      return;
    }
    if (!decodedAgentId) {
      throw new Error("Cannot create thread without agent ID");
    }

    let threadId: string;
    if (createMode === "existing") {
      if (!selectedLease) {
        throw new Error("Choose an existing sandbox first");
      }
      threadId = await handleCreateThread(
        selectedLease.provider_name,
        undefined,
        decodedAgentId,
        model,
        selectedLease.lease_id,
      );
    } else {
      if (!selectedRecipeSnapshot) {
        throw new Error("Recipe not found");
      }
      const cwd = workspace || settings?.default_workspace || undefined;
      threadId = await handleCreateThread(
        selectedProviderConfig || selectedSandbox,
        cwd,
        decodedAgentId,
        model,
        undefined,
        selectedRecipeSnapshot,
      );
    }
    postRun(threadId, message, undefined, model ? { model } : undefined).catch(err => {
      console.error("[NewChatPage] postRun failed:", err);
    });
    navigate(`/chat/hire/thread/${threadId}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  async function handleWorkspaceSet() {
    await refreshSettings();
    setShowWorkspaceSetup(false);
  }

  function applyResolvedConfig(config: ThreadLaunchConfig) {
    setCreateMode(config.create_mode);
    setSelectedProviderConfig(config.provider_config || "");
    setSelectedLeaseId(config.lease_id || "");
    setSelectedRecipeId(config.recipe?.id || "");
    setSelectedRecipeFeatures(config.recipe?.features ?? {});
    setSelectedWorkspace(config.workspace || "");
    setSelectedModel(config.model || settings?.default_model || "leon:large");
  }

  function summarizeEnvironment() {
    if (createMode === "existing") {
      if (!selectedLease) return "复用旧沙盒";
      return `${selectedLease.provider_name} · ${selectedLease.recipe_name}`;
    }
    const recipe = selectedRecipeSnapshot;
    if (!recipe) return "选择 recipe";
    const featureSuffix = enabledFeatureLabels(recipe).join(" · ");
    if (recipe.provider_type !== "local") return [recipe.name, featureSuffix].filter(Boolean).join(" · ");
    if (!activeWorkspace) return [recipe.name, featureSuffix, "选择工作区"].filter(Boolean).join(" · ");
    const parts = activeWorkspace.split("/").filter(Boolean);
    return [recipe.name, featureSuffix, parts.at(-1) ?? activeWorkspace].filter(Boolean).join(" · ");
  }

  function buildConfigSnapshot(): ConfigSnapshot {
    return {
      createMode,
      selectedLeaseId: selectedLeaseId || leaseOptions[0]?.lease_id || "",
      selectedRecipeId,
      selectedRecipeFeatures: { ...selectedRecipeFeatures },
      selectedWorkspace: activeWorkspace,
      selectedProviderConfig: selectedProviderConfig || selectedSandbox || "local",
    };
  }

  function resetConfigPanel() {
    setConfigSnapshot(null);
    setConfigStep(1);
  }

  function openConfigSnapshot() {
    setConfigStep(1);
    setConfigSnapshot(buildConfigSnapshot());
  }

  function cancelConfigChanges() {
    if (!configSnapshot) return resetConfigPanel();
    setCreateMode(configSnapshot.createMode);
    setSelectedLeaseId(configSnapshot.selectedLeaseId);
    setSelectedRecipeId(configSnapshot.selectedRecipeId);
    setSelectedRecipeFeatures(configSnapshot.selectedRecipeFeatures);
    setSelectedWorkspace(configSnapshot.selectedWorkspace);
    setSelectedProviderConfig(configSnapshot.selectedProviderConfig);
    resetConfigPanel();
  }

  async function persistDefaultConfig(draftModel: string, workspace: string | null) {
    if (!decodedAgentId) return;
    await saveDefaultThreadConfig(decodedAgentId, {
      create_mode: createMode,
      provider_config: selectedProviderConfig,
      recipe: selectedRecipeSnapshot,
      lease_id: createMode === "existing" ? selectedLeaseId || null : null,
      model: draftModel,
      workspace,
    });
  }

  async function applyConfigChanges(draftModel: string) {
    if (configStep === 1) {
      setConfigStep(2);
      return false;
    }
    if (configStep === 2) {
      if (localRecipeSelected) {
        setConfigStep(3);
        return false;
      }
      const workspace = createMode === "existing" ? selectedLease?.cwd || null : activeWorkspace || null;
      await persistDefaultConfig(draftModel, workspace);
      setSelectedModel(draftModel);
      resetConfigPanel();
      return true;
    }
    const nextWorkspace = activeWorkspace;
    if (createMode === "new" && selectedRecipeSnapshot?.provider_type === "local" && nextWorkspace) {
      await setDefaultWorkspace(nextWorkspace);
    }
    await persistDefaultConfig(draftModel, nextWorkspace || null);
    setSelectedModel(draftModel);
    resetConfigPanel();
    return true;
  }

  function stepBack() {
    if (configStep === 3) {
      setConfigStep(2);
      return;
    }
    if (configStep === 2) {
      setConfigStep(1);
    }
  }

  const selectedProviderType = providerConfigOptions.find((item) => item.value === selectedProviderConfig)?.providerType
    || providerTypeFromName(selectedProviderConfig || "local");
  useEffect(() => {
    if (createMode !== "new") return;
    const firstMatchingRecipe = recipeOptions.find((item) => item.recipe.provider_type === selectedProviderType);
    if (!firstMatchingRecipe) return;
    if (selectedRecipe?.provider_type === selectedProviderType) return;
    setSelectedRecipeId(firstMatchingRecipe.value);
  }, [createMode, recipeOptions, selectedProviderType, selectedRecipe?.provider_type]);

  const providerSummaryLabel = selectedProviderConfig
    ? providerConfigLabel(selectedProviderConfig)
    : "未选择 provider";
  const recipeSummaryLabel = selectedRecipe?.name ?? "未选择 recipe";
  const stepSummary = createMode === "existing"
    ? `复用 ${providerSummaryLabel} 的现有 sandbox`
    : `新建 ${providerSummaryLabel} sandbox · ${recipeSummaryLabel}`;

  // @@@defer-default-config - default config should refine the create form, not block
  // entry into the no-main-thread UI. If the config fetch stalls, users still need the
  // create-chat surface with sane local defaults.
  if (loading || resolveState === "resolving") {
    return (
      <ResolveStateCard
        memberName={memberName}
        memberAvatarUrl={memberAvatarUrl ?? undefined}
        title={`正在检查 ${memberName} 的默认线程`}
        description="如果没有默认线程，这里会进入创建界面。"
      />
    );
  }

  if (resolveState === "error") {
    return (
      <ResolveStateCard
        memberName={memberName}
        memberAvatarUrl={memberAvatarUrl ?? undefined}
        title={`无法检查 ${memberName} 的默认线程`}
        description={error ?? "未知错误"}
        destructive
      />
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
            {mode === "new" ? `为 ${memberName} 创建新对话` : `开始与 ${memberName} 对话`}
          </h1>
          <p className="text-sm text-muted-foreground">
            {mode === "new"
              ? "先确认这次要复用还是新建 sandbox，再发送第一条消息。"
              : isOwnedAgent
                ? "选择好环境后，直接发送第一条消息开始主线对话。"
                : `${memberName} 已准备好，先确认环境再开始。`}
          </p>
        </div>

        <CenteredInputBox
          defaultModel={selectedModel || settings?.default_model || "leon:large"}
          environmentControl={{
            panelClassName: "max-h-[calc(100vh-4rem)]",
            applyLabel: configStep === 3 ? "确认" : (configStep === 1 ? "下一步" : (localRecipeSelected ? "下一步" : "确认")),
            applyDisabled: (configStep === 2 && createMode === "existing" && !selectedLeaseId)
              || (configStep === 3 && workspaceRequired),
            showBack: configStep > 1,
            backLabel: "返回上一步",
            onBack: stepBack,
            summary: summarizeEnvironment(),
            onOpen: openConfigSnapshot,
            onCancel: cancelConfigChanges,
            onApply: applyConfigChanges,
            renderPanel: ({ draftModel, setDraftModel }) => {
              const activeRecipe = selectedRecipe;
              const filteredRecipeOptions = selectedProviderType
                ? recipeOptions.filter((item) => item.recipe.provider_type === selectedProviderType)
                : recipeOptions;
              const filteredLeaseOptions = selectedProviderConfig
                ? leaseOptions.filter((lease) => lease.provider_name === selectedProviderConfig)
                : leaseOptions;
              const configurableFeatureOptions = (activeRecipe?.feature_options ?? [])
                .filter((item) => activeRecipe?.configurable_features?.[item.key]);
              const existingCount = filteredLeaseOptions.length;
              const totalSteps = localRecipeSelected ? 3 : 2;
              const renderModelChoices = (compact = false) => (
                <div className={cn("flex flex-wrap items-center", compact ? "gap-1.5" : "gap-2")}>
                  {MODEL_OPTIONS.map((entry) => (
                    <button
                      key={entry.value}
                      type="button"
                      onClick={() => setDraftModel(entry.value)}
                      className={cn(
                        "border transition-colors",
                        compact ? "rounded-lg px-2.5 py-1 text-xs" : "rounded-xl px-3 py-1.5 text-sm",
                        draftModel === entry.value
                          ? "border-foreground bg-foreground text-background"
                          : "border-border bg-card text-foreground hover:bg-accent",
                      )}
                    >
                      {entry.label}
                    </button>
                  ))}
                </div>
              );

              return (
                <div className="space-y-3">
                  <div className="flex items-center justify-center gap-2 pb-1">
                    {Array.from({ length: totalSteps }, (_, index) => index + 1).map((step) => (
                      <div
                        key={step}
                        className={cn(
                          "h-1.5 rounded-full transition-colors",
                          step === configStep ? "w-6 bg-foreground" : "w-1.5 bg-border",
                        )}
                      />
                    ))}
                  </div>

                  {configStep === 1 ? (
                    <div className="space-y-4">
                      <div>
                        <div className="text-sm font-medium text-foreground">先确定模型与沙盒来源</div>
                      </div>

                      <div>
                        <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Model</div>
                        {renderModelChoices()}
                      </div>

                      <div className="grid gap-2 sm:grid-cols-2">
                        <button
                          type="button"
                          onClick={() => setCreateMode("new")}
                          className={cn(
                            "rounded-2xl border px-4 py-3 text-left transition-colors",
                            createMode === "new"
                              ? "border-foreground/30 bg-accent/60"
                              : "border-border bg-background hover:bg-accent/30",
                          )}
                        >
                          <div className="text-sm font-medium text-foreground">New sandbox</div>
                          <div className="mt-1 text-xs text-muted-foreground">新建一个 sandbox，再进入这次 thread。</div>
                        </button>
                        <button
                          type="button"
                          onClick={() => setCreateMode("existing")}
                          className={cn(
                            "rounded-2xl border px-4 py-3 text-left transition-colors",
                            createMode === "existing"
                              ? "border-foreground/30 bg-accent/60"
                              : "border-border bg-background hover:bg-accent/30",
                          )}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-sm font-medium text-foreground">Existing sandbox</div>
                            <span className="rounded-full bg-card px-2 py-0.5 text-[11px] text-muted-foreground">{existingCount}</span>
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">复用你已经拥有的 sandbox lease。</div>
                        </button>
                      </div>

                      <div>
                        <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Provider</div>
                        <Select
                          value={selectedProviderConfig}
                          onValueChange={(value) => {
                            const nextProviderConfig = value;
                            const nextProviderType = providerConfigOptions.find((item) => item.value === nextProviderConfig)?.providerType
                              || providerTypeFromName(nextProviderConfig);
                            setSelectedProviderConfig(nextProviderConfig);
                            const nextRecipes = recipeOptions.filter((item) => item.recipe.provider_type === nextProviderType);
                            if (nextRecipes.length > 0 && !nextRecipes.some((item) => item.value === selectedRecipeId)) {
                              setSelectedRecipeId(nextRecipes[0].value);
                            }
                            const nextLease = leaseOptions.find((lease) => lease.provider_name === nextProviderConfig);
                            if (createMode === "existing") {
                              setSelectedLeaseId(nextLease?.lease_id || "");
                            }
                          }}
                        >
                          <SelectTrigger className="h-10 text-sm">
                            <SelectValue placeholder="Choose a provider" />
                          </SelectTrigger>
                          <SelectContent>
                            {providerConfigOptions.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {item.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                  ) : null}

                  {configStep === 2 && (
                    <div className="space-y-4">
                      <div>
                        <div>
                          <div className="text-sm font-medium text-foreground">
                            {createMode === "new" ? "确认 Recipe 与工具" : "选择要复用的 sandbox"}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">{stepSummary}</div>
                        </div>
                      </div>

                      {createMode === "new" && (
                        <>
                          <div>
                            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">Recipe</div>
                            <Select value={selectedRecipeId} onValueChange={setSelectedRecipeId}>
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

                          {configurableFeatureOptions.length > 0 && (
                            <div className="space-y-2">
                              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">临时修改</div>
                              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                                {configurableFeatureOptions.map((option) => {
                                  const checked = Boolean(selectedRecipeFeatures[option.key]);
                                  return (
                                    <div
                                      key={option.key}
                                      onClick={() => {
                                        setSelectedRecipeFeatures((current) => ({
                                          ...current,
                                          [option.key]: !checked,
                                        }));
                                      }}
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter" || event.key === " ") {
                                          event.preventDefault();
                                          setSelectedRecipeFeatures((current) => ({
                                            ...current,
                                            [option.key]: !checked,
                                          }));
                                        }
                                      }}
                                      role="button"
                                      tabIndex={0}
                                      className={cn(
                                        "rounded-xl border px-3 py-2.5 text-left transition-colors",
                                        checked
                                          ? "border-foreground/30 bg-accent/60"
                                          : "border-border bg-background hover:bg-accent/30",
                                      )}
                                    >
                                      <div className="flex items-start gap-2.5">
                                        <Checkbox checked={checked} className="pointer-events-none mt-0.5 shrink-0" />
                                        <div className="min-w-0">
                                          <div className="flex items-center gap-2">
                                            <div className="text-sm font-medium text-foreground">{option.name}</div>
                                            {option.icon === "feishu" && (
                                              <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[10px] font-medium text-sky-700">
                                                飞书
                                              </span>
                                            )}
                                          </div>
                                          <div className="mt-0.5 text-xs text-muted-foreground">{option.description}</div>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </>
                      )}

                      {createMode === "existing" && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between gap-3">
                            <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">My Leases</div>
                            <div className="text-xs text-muted-foreground">{existingCount} available</div>
                          </div>
                          <div className="max-h-[320px] space-y-2 overflow-y-auto pr-1">
                            {filteredLeaseOptions.map((lease) => {
                              const isActive = selectedLeaseId === lease.lease_id;
                              const stateMeta = leaseStateMeta(lease.observed_state);
                              return (
                                <button
                                  key={lease.lease_id}
                                  type="button"
                                  onClick={() => setSelectedLeaseId(lease.lease_id)}
                                  className={cn(
                                    "w-full rounded-2xl border p-3 text-left transition-colors",
                                    isActive ? "border-primary/40 bg-primary/5" : "border-border bg-background hover:bg-accent/40",
                                  )}
                                >
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                      <div className="flex items-center gap-2">
                                        <span className={cn("h-2 w-2 rounded-full", stateMeta.dot)} />
                                        <div className="text-sm font-medium text-foreground">
                                          {PROVIDER_TYPE_LABELS[providerTypeFromName(lease.provider_name)] ?? lease.provider_name} · {lease.recipe_name}
                                        </div>
                                      </div>
                                      <div className="mt-1 text-xs text-muted-foreground">
                                        {stateMeta.label} · {lease.cwd || "No working directory"}
                                      </div>
                                    </div>
                                    <div className="flex -space-x-2">
                                      {lease.agents.slice(0, 4).map((agent) => (
                                        <MemberAvatar
                                          key={agent.thread_id}
                                          name={agent.agent_name}
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
                                你还没有可复用的 sandbox。
                              </div>
                            )}
                          </div>
                          {leaseError && <p className="mt-2 text-xs text-destructive">{leaseError}</p>}
                        </div>
                      )}
                    </div>
                  )}

                  {configStep === 3 && localRecipeSelected && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="truncate text-xs text-muted-foreground">
                          {[recipeSummaryLabel, ...enabledFeatureLabels(selectedRecipeSnapshot)].join(" · ")}
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium text-foreground">选择工作区</div>
                        </div>
                      </div>

                      <div className="max-h-[360px] overflow-y-auto">
                        <FilesystemBrowser
                          onSelect={(path) => {
                            setSelectedWorkspace(path);
                          }}
                          initialPath={activeWorkspace || "~"}
                        />
                      </div>

                      {workspaceRequired && (
                        <div className="text-xs text-destructive">
                          Local sandbox 需要先选择一个工作区，才能确认配置。
                        </div>
                      )}
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
