import { useEffect, useMemo, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { postRun } from "../api";
import CenteredInputBox from "../components/CenteredInputBox";
import type { ThreadManagerState, ThreadManagerActions } from "../hooks/use-thread-manager";
import { useWorkspaceSettings } from "../hooks/use-workspace-settings";
import { useAuthStore } from "../store/auth-store";
import { useAppStore } from "../store/app-store";
import ActorAvatar from "../components/ActorAvatar";
import FilesystemBrowser from "../components/FilesystemBrowser";
import { getDefaultThreadConfig, listMyLeases, saveDefaultThreadConfig } from "../api/client";
import { fetchAccountResourceLimits } from "../api/settings";
import type { AccountResourceLimit, RecipeFeatureOption, SandboxTemplateSnapshot, ThreadLaunchConfig, UserLeaseSummary } from "../api/types";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import { cn } from "../lib/utils";

interface OutletContext {
  tm: ThreadManagerState & ThreadManagerActions;
}

function ResolveStateCard({
  agentName,
  agentAvatarUrl,
  title,
  description,
  destructive = false,
}: {
  agentName: string;
  agentAvatarUrl?: string;
  title: string;
  description: string;
  destructive?: boolean;
}) {
  return (
    <div className="flex-1 flex items-center justify-center relative">
      <div className="w-full max-w-[420px] px-6 text-center">
        <div className="flex justify-center mb-4">
          <ActorAvatar name={agentName} avatarUrl={agentAvatarUrl} type="mycel_agent" size="lg" />
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
  selectedExistingSandboxId: string;
  selectedSandboxTemplateId: string;
  selectedSandboxTemplateFeatures: Record<string, boolean>;
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

function enabledFeatureLabels(sandboxTemplate: SandboxTemplateSnapshot | null): string[] {
  if (!sandboxTemplate?.feature_options?.length) return [];
  return sandboxTemplate.feature_options
    .filter((item) => sandboxTemplate.features?.[item.key])
    .map((item) => item.name);
}

function isActiveHireRoute(): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path.startsWith("/chat/hire");
}

export default function NewChatPage({ mode = "agent" }: { mode?: "agent" | "new" }) {
  const navigate = useNavigate();
  const { agentId } = useParams<{ agentId: string }>();
  const { tm } = useOutletContext<OutletContext>();
  const { sandboxTypes, selectedSandbox, handleCreateThread, handleGetDefaultThread } = tm;
  const { settings, loading, setDefaultWorkspace } = useWorkspaceSettings();
  const shouldResolveDefaultThread = mode === "agent";
  const [error, setError] = useState<string | null>(null);
  const [resolveState, setResolveState] = useState<"resolving" | "ready" | "error">(
    shouldResolveDefaultThread ? "resolving" : "ready",
  );
  const [createMode, setCreateMode] = useState<"new" | "existing">("new");
  const [leaseOptions, setLeaseOptions] = useState<UserLeaseSummary[]>([]);
  const [leaseError, setLeaseError] = useState<string | null>(null);
  const [leaseLoading, setLeaseLoading] = useState(true);
  const [selectedExistingSandboxId, setSelectedExistingSandboxId] = useState<string>("");
  const [selectedSandboxTemplateId, setSelectedSandboxTemplateId] = useState<string>("");
  const [selectedSandboxTemplateFeatures, setSelectedSandboxTemplateFeatures] = useState<Record<string, boolean>>({});
  const [selectedProviderConfig, setSelectedProviderConfig] = useState<string>("");
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [configStep, setConfigStep] = useState<1 | 2 | 3>(1);
  const [createModeInitialized, setCreateModeInitialized] = useState(false);
  const [configDefaultsLoading, setConfigDefaultsLoading] = useState(true);
  const [configSnapshot, setConfigSnapshot] = useState<ConfigSnapshot | null>(null);
  const [accountResources, setAccountResources] = useState<AccountResourceLimit[]>([]);
  const [accountResourcesLoading, setAccountResourcesLoading] = useState(true);
  const [accountResourcesError, setAccountResourcesError] = useState<string | null>(null);

  const authAgent = useAuthStore(s => s.agent);
  const agentList = useAppStore(s => s.agentList);
  const librarySandboxTemplates = useAppStore(s => s.librarySandboxTemplates);
  const decodedAgentId = agentId ? decodeURIComponent(agentId) : null;
  const resolvedAgent = decodedAgentId ? agentList.find(agent => agent.id === decodedAgentId) : undefined;
  const isOwnedAgent = decodedAgentId === authAgent?.id;
  const agentName = resolvedAgent?.name ?? (isOwnedAgent ? (authAgent?.name || "Agent") : "Agent");
  const agentAvatarUrl = resolvedAgent?.avatar_url;

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
        // @@@default-thread-route-teardown - default thread resolution can
        // finish after navigation already left the hire flow. Only log while
        // /chat/hire is still active; otherwise this is stale UI noise.
        if (!isActiveHireRoute()) return;
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

    async function loadAccountResources() {
      setAccountResourcesLoading(true);
      setAccountResourcesError(null);
      try {
        const resources = await fetchAccountResourceLimits(ac.signal);
        if (cancelled) return;
        setAccountResources(resources);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setAccountResourcesError(err instanceof Error ? err.message : "Failed to load account resources");
      } finally {
        if (!cancelled && !ac.signal.aborted) setAccountResourcesLoading(false);
      }
    }

    void loadAccountResources();
    return () => {
      cancelled = true;
      ac.abort();
    };
  }, []);

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
        setSelectedExistingSandboxId((current) => current || (leases[0] ? leaseSandboxId(leases[0]) : ""));
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

  const sandboxTemplateOptions = useMemo(() => (
    librarySandboxTemplates
      .filter((item) => item.available !== false && item.provider_type)
      .map((item) => ({
        value: item.id,
        label: item.name,
        sandboxTemplate: {
          id: item.id,
          name: item.name,
          desc: item.desc,
          provider_name: item.provider_name,
          provider_type: item.provider_type as string,
          features: (item as { features?: Record<string, boolean> }).features ?? {},
          configurable_features: (item as { configurable_features?: Record<string, boolean> }).configurable_features ?? {},
          feature_options: (item as { feature_options?: RecipeFeatureOption[] }).feature_options ?? [],
        } satisfies SandboxTemplateSnapshot,
      }))
  ), [librarySandboxTemplates]);
  const selectedLease = leaseOptions.find((lease) => leaseSandboxId(lease) === selectedExistingSandboxId) ?? null;
  const sandboxResourceByProvider = useMemo(() => {
    const map = new Map<string, AccountResourceLimit>();
    for (const item of accountResources) {
      if (item.resource === "sandbox") map.set(item.provider_name, item);
    }
    return map;
  }, [accountResources]);
  const providerConfigOptions = useMemo(
    () =>
      sandboxTypes
        .map((item) => ({
          value: item.name,
          label: sandboxResourceByProvider.get(item.name)?.label ?? providerConfigLabel(item.name),
          providerType: item.provider || providerTypeFromName(item.name),
          resource: sandboxResourceByProvider.get(item.name),
          available: item.available,
          reason: item.reason,
        })),
    [sandboxResourceByProvider, sandboxTypes],
  );
  useEffect(() => {
    if (!selectedSandboxTemplateId && sandboxTemplateOptions[0]?.value) {
      setSelectedSandboxTemplateId(sandboxTemplateOptions[0].value);
    }
  }, [sandboxTemplateOptions, selectedSandboxTemplateId]);

  useEffect(() => {
    if (!selectedExistingSandboxId && leaseOptions[0]) {
      setSelectedExistingSandboxId(leaseSandboxId(leaseOptions[0]));
    }
  }, [leaseOptions, selectedExistingSandboxId]);

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
        // @@@default-config-route-teardown - default thread config can resolve
        // after navigation already left the hire flow. Only log while the
        // /chat/hire route is still active; otherwise this is stale UI noise.
        if (!isActiveHireRoute()) return;
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

  const selectedSandboxTemplate = useMemo(
    () => sandboxTemplateOptions.find((item) => item.value === selectedSandboxTemplateId)?.sandboxTemplate ?? sandboxTemplateOptions[0]?.sandboxTemplate ?? null,
    [sandboxTemplateOptions, selectedSandboxTemplateId],
  );
  useEffect(() => {
    if (!selectedSandboxTemplate) return;
    setSelectedSandboxTemplateFeatures(selectedSandboxTemplate.features ?? {});
  }, [selectedSandboxTemplateId, selectedSandboxTemplate]);

  const selectedSandboxTemplateSnapshot = selectedSandboxTemplate
    ? {
      ...selectedSandboxTemplate,
      features: { ...(selectedSandboxTemplate.features ?? {}), ...selectedSandboxTemplateFeatures },
    }
    : null;
  const activeWorkspace = selectedWorkspace || settings?.default_workspace || "";
  const localSandboxTemplateSelected = createMode === "new" && selectedSandboxTemplate?.provider_type === "local";

  async function handleSend(message: string, model: string) {
    const workspace = selectedWorkspace || settings?.default_workspace || undefined;
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
        leaseSandboxId(selectedLease),
      );
    } else {
      if (!selectedSandboxTemplateSnapshot) {
        throw new Error("沙盒模板不存在");
      }
      const cwd = workspace || settings?.default_workspace || undefined;
      threadId = await handleCreateThread(
        selectedProviderConfig || selectedSandbox,
        cwd,
        decodedAgentId,
        model,
        undefined,
        selectedSandboxTemplateSnapshot.id,
      );
    }
    postRun(threadId, message, undefined, model ? { model } : undefined).catch(err => {
      console.error("[NewChatPage] postRun failed:", err);
    });
    navigate(`/chat/hire/thread/${threadId}`, {
      state: { selectedModel: model, runStarted: true, message },
    });
  }

  function applyResolvedConfig(config: ThreadLaunchConfig) {
    setCreateMode(config.create_mode);
    setSelectedProviderConfig(config.provider_config || "");
    setSelectedExistingSandboxId(config.existing_sandbox_id || "");
    setSelectedSandboxTemplateId(config.sandbox_template_id || config.sandbox_template?.id || "");
    setSelectedSandboxTemplateFeatures(config.sandbox_template?.features ?? {});
    setSelectedWorkspace(config.workspace || "");
    setSelectedModel(config.model || settings?.default_model || "leon:large");
  }

  function summarizeEnvironment() {
    if (createMode === "existing") {
      if (!selectedLease) return "复用旧沙盒";
      return `${selectedLease.provider_name} · ${selectedLease.recipe_name}`;
    }
    const sandboxTemplate = selectedSandboxTemplateSnapshot;
    if (!sandboxTemplate) return "选择沙盒模板";
    const featureSuffix = enabledFeatureLabels(sandboxTemplate).join(" · ");
    if (sandboxTemplate.provider_type !== "local") return [sandboxTemplate.name, featureSuffix].filter(Boolean).join(" · ");
    if (!activeWorkspace) return [sandboxTemplate.name, featureSuffix, "选择工作区"].filter(Boolean).join(" · ");
    const parts = activeWorkspace.split("/").filter(Boolean);
    return [sandboxTemplate.name, featureSuffix, parts.at(-1) ?? activeWorkspace].filter(Boolean).join(" · ");
  }

  function buildConfigSnapshot(): ConfigSnapshot {
    return {
      createMode,
      selectedExistingSandboxId: selectedExistingSandboxId || (leaseOptions[0] ? leaseSandboxId(leaseOptions[0]) : ""),
      selectedSandboxTemplateId,
      selectedSandboxTemplateFeatures: { ...selectedSandboxTemplateFeatures },
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
    setSelectedExistingSandboxId(configSnapshot.selectedExistingSandboxId);
    setSelectedSandboxTemplateId(configSnapshot.selectedSandboxTemplateId);
    setSelectedSandboxTemplateFeatures(configSnapshot.selectedSandboxTemplateFeatures);
    setSelectedWorkspace(configSnapshot.selectedWorkspace);
    setSelectedProviderConfig(configSnapshot.selectedProviderConfig);
    resetConfigPanel();
  }

  async function persistDefaultConfig(draftModel: string, workspace: string | null) {
    if (!decodedAgentId) return;
    await saveDefaultThreadConfig(decodedAgentId, {
      create_mode: createMode,
      provider_config: selectedProviderConfig,
      sandbox_template_id: selectedSandboxTemplateSnapshot?.id || null,
      existing_sandbox_id: createMode === "existing" ? selectedExistingSandboxId || null : null,
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
      if (localSandboxTemplateSelected) {
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
    if (createMode === "new" && selectedSandboxTemplateSnapshot?.provider_type === "local" && nextWorkspace) {
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
    const firstMatchingSandboxTemplate = sandboxTemplateOptions.find((item) => item.sandboxTemplate.provider_type === selectedProviderType);
    if (!firstMatchingSandboxTemplate) return;
    if (selectedSandboxTemplate?.provider_type === selectedProviderType) return;
    setSelectedSandboxTemplateId(firstMatchingSandboxTemplate.value);
  }, [createMode, sandboxTemplateOptions, selectedProviderType, selectedSandboxTemplate?.provider_type]);

  const providerSummaryLabel = selectedProviderConfig
    ? providerConfigLabel(selectedProviderConfig)
    : "未选择 provider";
  const sandboxTemplateSummaryLabel = selectedSandboxTemplate?.name ?? "未选择沙盒模板";
  const selectedProviderResource = selectedProviderConfig
    ? sandboxResourceByProvider.get(selectedProviderConfig)
    : undefined;
  const selectedProviderOption = selectedProviderConfig
    ? providerConfigOptions.find((item) => item.value === selectedProviderConfig)
    : undefined;
  const newSandboxQuotaBlocked = createMode === "new" && selectedProviderResource?.can_create === false;
  const newSandboxProviderUnavailable = createMode === "new" && selectedProviderOption?.available === false;
  const stepSummary = createMode === "existing"
    ? `复用 ${providerSummaryLabel} 的现有沙盒`
    : `新建 ${providerSummaryLabel} 沙盒 · ${sandboxTemplateSummaryLabel}`;

  // @@@defer-default-config - default config should refine the create form, not block
  // entry into the no-main-thread UI. If the config fetch stalls, users still need the
  // create-chat surface with sane local defaults.
  if (loading || resolveState === "resolving") {
    return (
      <ResolveStateCard
        agentName={agentName}
        agentAvatarUrl={agentAvatarUrl ?? undefined}
        title={`正在检查 ${agentName} 的默认线程`}
        description="如果没有默认线程，这里会进入创建界面。"
      />
    );
  }

  if (resolveState === "error") {
    return (
      <ResolveStateCard
        agentName={agentName}
        agentAvatarUrl={agentAvatarUrl ?? undefined}
        title={`无法检查 ${agentName} 的默认线程`}
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
            <ActorAvatar name={agentName} avatarUrl={agentAvatarUrl} type="mycel_agent" size="lg" />
          </div>
          <h1 className="text-2xl font-medium text-foreground mb-2">
            {mode === "new" ? `为 ${agentName} 创建新对话` : `开始与 ${agentName} 对话`}
          </h1>
          <p className="text-sm text-muted-foreground">
            {mode === "new"
              ? "先确认这次要复用还是新建 sandbox，再发送第一条消息。"
              : isOwnedAgent
                ? "选择好环境后，直接发送第一条消息开始主线对话。"
                : `${agentName} 已准备好，先确认环境再开始。`}
          </p>
        </div>

        <CenteredInputBox
          defaultModel={selectedModel || settings?.default_model || "leon:large"}
          environmentControl={{
            panelClassName: "max-h-[calc(100vh-4rem)]",
            applyLabel: configStep === 3 ? "确认" : (configStep === 1 ? "下一步" : (localSandboxTemplateSelected ? "下一步" : "确认")),
            applyDisabled: (configStep === 1 && (newSandboxQuotaBlocked || newSandboxProviderUnavailable))
              || (configStep === 2 && createMode === "existing" && !selectedExistingSandboxId),
            showBack: configStep > 1,
            backLabel: "返回上一步",
            onBack: stepBack,
            summary: summarizeEnvironment(),
            onOpen: openConfigSnapshot,
            onCancel: cancelConfigChanges,
            onApply: applyConfigChanges,
            renderPanel: ({ draftModel, setDraftModel }) => {
              const activeSandboxTemplate = selectedSandboxTemplate;
              const filteredSandboxTemplateOptions = selectedProviderType
                ? sandboxTemplateOptions.filter((item) => item.sandboxTemplate.provider_type === selectedProviderType)
                : sandboxTemplateOptions;
              const filteredLeaseOptions = selectedProviderConfig
                ? leaseOptions.filter((lease) => lease.provider_name === selectedProviderConfig)
                : leaseOptions;
              const configurableFeatureOptions = (activeSandboxTemplate?.feature_options ?? [])
                .filter((item) => activeSandboxTemplate?.configurable_features?.[item.key]);
              const existingCount = filteredLeaseOptions.length;
              const totalSteps = localSandboxTemplateSelected ? 3 : 2;
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
                            const nextSandboxTemplates = sandboxTemplateOptions.filter((item) => item.sandboxTemplate.provider_type === nextProviderType);
                            if (nextSandboxTemplates.length > 0 && !nextSandboxTemplates.some((item) => item.value === selectedSandboxTemplateId)) {
                              setSelectedSandboxTemplateId(nextSandboxTemplates[0].value);
                            }
                            const nextLease = leaseOptions.find((lease) => lease.provider_name === nextProviderConfig);
                            if (createMode === "existing") {
                              setSelectedExistingSandboxId(nextLease ? leaseSandboxId(nextLease) : "");
                            }
                          }}
                        >
                          <SelectTrigger className="h-10 text-sm">
                            <SelectValue placeholder="Choose a provider" />
                          </SelectTrigger>
                          <SelectContent>
                            {providerConfigOptions.map((item) => (
                              <SelectItem key={item.value} value={item.value}>
                                {!item.available
                                  ? `${item.label} · 当前不可用`
                                  : item.resource?.can_create === false ? `${item.label} · 已达上限` : item.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {accountResourcesLoading && (
                          <p className="mt-2 text-xs text-muted-foreground">正在读取账号资源...</p>
                        )}
                        {accountResourcesError && (
                          <p className="mt-2 text-xs text-destructive">{accountResourcesError}</p>
                        )}
                        {newSandboxProviderUnavailable && selectedProviderOption && (
                          <div className="mt-2 space-y-1 text-xs text-destructive">
                            <p>{selectedProviderOption.label} 当前不可用</p>
                            {selectedProviderOption.reason && <p>{selectedProviderOption.reason}</p>}
                          </div>
                        )}
                        {!newSandboxProviderUnavailable && !accountResourcesLoading && selectedProviderResource && (
                          <p className={cn(
                            "mt-2 text-xs",
                            selectedProviderResource.can_create ? "text-muted-foreground" : "text-destructive",
                          )}
                          >
                            {selectedProviderResource.can_create
                              ? `${selectedProviderResource.label} 已用 ${selectedProviderResource.used}/${selectedProviderResource.limit}，剩余 ${selectedProviderResource.remaining}`
                              : `${selectedProviderResource.label} 已达上限`}
                          </p>
                        )}
                      </div>
                    </div>
                  ) : null}

                  {configStep === 2 && (
                    <div className="space-y-4">
                      <div>
                        <div>
                          <div className="text-sm font-medium text-foreground">
                            {createMode === "new" ? "确认沙盒模板与工具" : "选择要复用的沙盒"}
                          </div>
                          <div className="mt-1 text-xs text-muted-foreground">{stepSummary}</div>
                        </div>
                      </div>

                      {createMode === "new" && (
                        <>
                          <div>
                            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">沙盒模板</div>
                            <Select value={selectedSandboxTemplateId} onValueChange={setSelectedSandboxTemplateId}>
                              <SelectTrigger className="h-10 text-sm">
                                <SelectValue placeholder="选择沙盒模板" />
                              </SelectTrigger>
                              <SelectContent>
                                {filteredSandboxTemplateOptions.map((item) => (
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
                                          const checked = Boolean(selectedSandboxTemplateFeatures[option.key]);
                                  return (
                                    <div
                                      key={option.key}
                                      onClick={() => {
                                            setSelectedSandboxTemplateFeatures((current) => ({
                                              ...current,
                                              [option.key]: !checked,
                                            }));
                                      }}
                                      onKeyDown={(event) => {
                                        if (event.key === "Enter" || event.key === " ") {
                                          event.preventDefault();
                                              setSelectedSandboxTemplateFeatures((current) => ({
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
                              const leaseSandboxKey = leaseSandboxId(lease);
                              const isActive = selectedExistingSandboxId === leaseSandboxKey;
                              const stateMeta = leaseStateMeta(lease.observed_state);
                              return (
                                <button
                                  key={lease.lease_id}
                                  type="button"
                                  onClick={() => setSelectedExistingSandboxId(leaseSandboxKey)}
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
                                        <ActorAvatar
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

                  {configStep === 3 && localSandboxTemplateSelected && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="truncate text-xs text-muted-foreground">
                          {[sandboxTemplateSummaryLabel, ...enabledFeatureLabels(selectedSandboxTemplateSnapshot)].join(" · ")}
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
                    </div>
                  )}
                </div>
              );
            },
          }}
          onSend={handleSend}
        />
      </div>
    </div>
  );
}
  function leaseSandboxId(lease: UserLeaseSummary): string {
    return lease.sandbox_id;
  }
