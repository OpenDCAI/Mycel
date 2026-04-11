import { Box, Cpu, Activity, AlertCircle, RefreshCw, ChevronLeft, ChevronRight, Ticket, Plus, Trash2, Copy, Check, AlertTriangle, TicketX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useIsMobile } from "../hooks/use-mobile";
import ModelMappingSection from "../components/ModelMappingSection";
import ModelPoolSection from "../components/ModelPoolSection";
import ObservationSection from "../components/ObservationSection";
import ProvidersSection from "../components/ProvidersSection";
import SandboxSection from "../components/SandboxSection";
import WorkspaceSection from "../components/WorkspaceSection";
import { fetchInviteCodes, generateInviteCode, revokeInviteCode } from "@/api/client";
import type { InviteCode } from "@/api/client";
import { toast } from "sonner";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { authFetch } from "../store/auth-store";

interface AvailableModelsData {
  models: Array<{
    id: string;
    name: string;
    provider?: string;
    context_length?: number;
    custom?: boolean;
  }>;
  virtual_models: Array<{
    id: string;
    name: string;
    description: string;
    icon: string;
  }>;
}

interface Settings {
  model_mapping: Record<string, string>;
  enabled_models: string[];
  custom_config: Record<string, { based_on?: string | null; context_limit?: number | null }>;
  providers: Record<string, { api_key: string | null; base_url: string | null }>;
  default_workspace: string | null;
  default_model: string;
}

type Tab = "model" | "sandbox" | "observation" | "invite";

const TABS: { id: Tab; label: string; icon: typeof Cpu; desc: string }[] = [
  { id: "model", label: "模型", icon: Cpu, desc: "模型、提供商与映射" },
  { id: "sandbox", label: "沙箱", icon: Box, desc: "执行环境配置" },
  { id: "observation", label: "追踪", icon: Activity, desc: "Agent 可观测性" },
  { id: "invite", label: "邀请码", icon: Ticket, desc: "管理注册邀请码" },
];

function isActiveSettingsRoute(): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path === "/settings";
}

function formatInviteDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "—";
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function InviteStatusBadge({ code }: { code: InviteCode }) {
  if (code.used) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-muted text-muted-foreground">
        已使用
      </span>
    );
  }
  if (code.expires_at && new Date(code.expires_at) < new Date()) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-warning/10 text-warning">
        已过期
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-success/10 text-success">
      <span className="w-1.5 h-1.5 rounded-full bg-success" />
      未使用
    </span>
  );
}

function InviteCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success("已复制到剪贴板");
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("复制失败");
    }
  }, [text]);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={handleCopy}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors duration-fast"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
        </button>
      </TooltipTrigger>
      <TooltipContent side="top"><p>复制邀请码</p></TooltipContent>
    </Tooltip>
  );
}

function InviteCodesSection() {
  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInviteCodes();
      setCodes(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const newCode = await generateInviteCode(7);
      setCodes((prev) => [newCode, ...prev]);
      toast.success("邀请码已生成");
    } catch (err) {
      toast.error(`生成失败: ${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setGenerating(false);
    }
  };

  const handleRevoke = async (code: string) => {
    setRevoking(code);
    try {
      await revokeInviteCode(code);
      setCodes((prev) => prev.filter((c) => c.code !== code));
      toast.success("邀请码已吊销");
    } catch (err) {
      toast.error(`吊销失败: ${err instanceof Error ? err.message : "未知错误"}`);
    } finally {
      setRevoking(null);
    }
  };

  const isRevokable = (code: InviteCode) =>
    !code.used && !(code.expires_at && new Date(code.expires_at) < new Date());

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">邀请码</h3>
          <p className="text-xs text-muted-foreground mt-0.5">管理注册邀请码，邀请新成员加入 Mycel</p>
        </div>
        <button
          onClick={() => void handleGenerate()}
          disabled={generating}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity duration-fast"
        >
          <Plus className="w-4 h-4" />
          {generating ? "生成中..." : "生成邀请码"}
        </button>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin mb-3" />
          <p className="text-sm text-muted-foreground">加载中...</p>
        </div>
      ) : error ? (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="w-12 h-12 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
            <AlertTriangle className="w-6 h-6 text-destructive" />
          </div>
          <p className="text-sm font-medium text-foreground mb-1">加载失败</p>
          <p className="text-xs text-muted-foreground mb-4 max-w-xs text-center">{error}</p>
          <button
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 transition-opacity duration-fast"
          >
            <RefreshCw className="w-3.5 h-3.5" />重试
          </button>
        </div>
      ) : codes.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4">
            <Ticket className="w-7 h-7 text-primary" />
          </div>
          <p className="text-sm font-semibold text-foreground mb-1">还没有邀请码</p>
          <p className="text-xs text-muted-foreground mb-5 max-w-[220px] text-center leading-relaxed">
            生成邀请码，邀请新成员加入 Mycel
          </p>
          <button
            onClick={() => void handleGenerate()}
            disabled={generating}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity duration-fast"
          >
            <Plus className="w-3.5 h-3.5" />{generating ? "生成中..." : "生成邀请码"}
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-4 py-2.5 bg-muted/50 border-b border-border text-xs text-muted-foreground font-medium">
            <span>邀请码</span>
            <span className="w-20 text-center">状态</span>
            <span className="w-24 text-center hidden sm:block">创建时间</span>
            <span className="w-24 text-center hidden sm:block">过期时间</span>
            <span className="w-16 text-center">操作</span>
          </div>
          {codes.map((item) => (
            <div
              key={item.code}
              className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-4 px-4 py-3 border-b border-border last:border-b-0 items-center hover:bg-muted/30 transition-colors duration-fast"
            >
              <div className="flex items-center gap-2 min-w-0">
                <code className="text-sm font-mono text-foreground truncate">{item.code}</code>
              </div>
              <div className="w-20 flex justify-center">
                <InviteStatusBadge code={item} />
              </div>
              <div className="w-24 text-center hidden sm:block">
                <span className="text-xs text-muted-foreground">{formatInviteDate(item.created_at)}</span>
              </div>
              <div className="w-24 text-center hidden sm:block">
                <span className="text-xs text-muted-foreground">{formatInviteDate(item.expires_at)}</span>
              </div>
              <div className="w-16 flex items-center justify-center gap-0.5">
                <InviteCopyButton text={item.code} />
                {isRevokable(item) && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => void handleRevoke(item.code)}
                        disabled={revoking === item.code}
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40 transition-colors duration-fast"
                      >
                        {revoking === item.code ? (
                          <div className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
                        ) : (
                          <Trash2 className="w-3.5 h-3.5" />
                        )}
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top"><p>吊销</p></TooltipContent>
                  </Tooltip>
                )}
                {!isRevokable(item) && (
                  <div className="w-7 h-7 flex items-center justify-center text-muted-foreground/20">
                    <TicketX className="w-3.5 h-3.5" />
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const isMobile = useIsMobile();
  const [tab, setTab] = useState<Tab | null>(isMobile ? null : "model");
  const [availableModels, setAvailableModels] = useState<AvailableModelsData | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [sandboxes, setSandboxes] = useState<Record<string, Record<string, unknown>>>({});
  const [observationConfig, setObservationConfig] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [modelsRes, settingsRes, sandboxesRes, observationRes] = await Promise.all([
        authFetch("/api/settings/available-models"),
        authFetch("/api/settings"),
        authFetch("/api/settings/sandboxes"),
        authFetch("/api/settings/observation"),
      ]);

      if (!modelsRes.ok || !settingsRes.ok) {
        throw new Error(`API 请求失败 (${modelsRes.status})`);
      }

      const modelsData = await modelsRes.json();
      const settingsData = await settingsRes.json();
      const sandboxesData = await sandboxesRes.json();
      const observationData = await observationRes.json();

      setAvailableModels(modelsData);
      setSettings(settingsData);
      setSandboxes(sandboxesData.sandboxes || {});
      setObservationConfig(observationData);
    } catch (err) {
      // @@@settings-route-teardown - settings bootstrap requests can finish
      // after navigation already left /settings. Only surface failures while
      // this route is still active; otherwise this is stale UI noise.
      if (!isActiveSettingsRoute()) return;
      console.error("Failed to load settings:", err);
      setError(err instanceof Error ? err.message : "加载设置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleAddCustomModel = async (modelId: string, provider: string, basedOn?: string, contextLimit?: number) => {
    const res = await authFetch("/api/settings/models/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_id: modelId, provider, based_on: basedOn || null, context_limit: contextLimit || null }),
    });
    const data = await res.json();
    if (data.success) {
      const [modelsRes, settingsRes] = await Promise.all([
        authFetch("/api/settings/available-models"),
        authFetch("/api/settings"),
      ]);
      setAvailableModels(await modelsRes.json());
      setSettings(await settingsRes.json());
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (error || !availableModels || !settings) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-3">
          <AlertCircle className="w-8 h-8 text-destructive mx-auto" />
          <p className="text-sm text-muted-foreground">{error || "加载设置失败"}</p>
          <button
            onClick={() => void loadData()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-border rounded-lg hover:bg-muted"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            重试
          </button>
        </div>
      </div>
    );
  }

  const activeTab = tab ?? "model";

  const renderContent = () => (
    <div className="max-w-2xl mx-auto py-6 px-6 space-y-6">
      {activeTab === "model" && (
        <>
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">默认模型</h3>
            <p className="text-xs text-muted-foreground">新对话的默认虚拟模型</p>
            <div className="flex gap-2 flex-wrap">
              {(["leon:mini", "leon:medium", "leon:large", "leon:max"] as const).map((id) => {
                const label = id.split(":")[1].charAt(0).toUpperCase() + id.split(":")[1].slice(1);
                const active = settings.default_model === id;
                return (
                  <button
                    key={id}
                    onClick={async () => {
                      setSettings({ ...settings, default_model: id });
                      await authFetch("/api/settings/default-model", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ model: id }),
                      });
                    }}
                    className={`px-4 py-2 text-sm rounded-lg border transition-colors duration-fast ${
                      active
                        ? "bg-primary/10 border-primary/40 text-primary font-medium"
                        : "border-border text-muted-foreground hover:border-primary/20 hover:text-foreground"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          <ModelMappingSection
            virtualModels={availableModels.virtual_models}
            availableModels={availableModels.models}
            modelMapping={settings.model_mapping}
            enabledModels={settings.enabled_models}
            onUpdate={(mapping) => setSettings({ ...settings, model_mapping: mapping })}
          />
          <ModelPoolSection
            models={availableModels.models}
            enabledModels={settings.enabled_models}
            customConfig={settings.custom_config || {}}
            providers={settings.providers}
            onToggle={(modelId, enabled) => {
              const newEnabled = enabled
                ? [...settings.enabled_models, modelId]
                : settings.enabled_models.filter((id) => id !== modelId);
              setSettings({ ...settings, enabled_models: newEnabled });
            }}
            onAddCustomModel={handleAddCustomModel}
            onRemoveCustomModel={async (modelId) => {
              const res = await authFetch(`/api/settings/models/custom?model_id=${encodeURIComponent(modelId)}`, {
                method: "DELETE",
              });
              const data = await res.json();
              if (data.success) {
                const [modelsRes, settingsRes] = await Promise.all([
                  authFetch("/api/settings/available-models"),
                  authFetch("/api/settings"),
                ]);
                setAvailableModels(await modelsRes.json());
                setSettings(await settingsRes.json());
              }
            }}
          />
          <ProvidersSection
            providers={settings.providers}
            onUpdate={(provider, config) => {
              setSettings({
                ...settings,
                providers: { ...settings.providers, [provider]: config },
              });
            }}
          />
        </>
      )}

      {activeTab === "sandbox" && (
        <>
          <WorkspaceSection
            defaultWorkspace={settings.default_workspace}
            onUpdate={(ws) => setSettings({ ...settings, default_workspace: ws })}
          />
          <SandboxSection
            sandboxes={sandboxes}
            onUpdate={(name, config) => {
              setSandboxes({ ...sandboxes, [name]: config });
            }}
          />
        </>
      )}

      {activeTab === "observation" && (
        <ObservationSection
          config={observationConfig}
          onUpdate={(cfg) => setObservationConfig(cfg)}
        />
      )}

      {activeTab === "invite" && (
        <InviteCodesSection />
      )}
    </div>
  );

  const renderTabList = () => (
    <div className="space-y-1">
      {TABS.map((t) => {
        const Icon = t.icon;
        const active = tab === t.id;
        return (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors duration-fast group ${
              active
                ? "bg-primary/5 border border-primary/15"
                : "hover:bg-muted border border-transparent"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Icon className={`w-4 h-4 ${active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"}`} />
              <span className={`text-sm font-medium ${active ? "text-foreground" : "text-muted-foreground group-hover:text-foreground"}`}>
                {t.label}
              </span>
              {isMobile && <ChevronRight className="w-4 h-4 text-muted-foreground ml-auto" />}
            </div>
            <p className={`text-xs mt-0.5 ml-[26px] ${active ? "text-muted-foreground" : "text-muted-foreground/60"}`}>
              {t.desc}
            </p>
          </button>
        );
      })}
    </div>
  );

  if (isMobile) {
    if (tab === null) {
      return (
        <div className="h-full flex flex-col bg-background">
          <div className="px-4 pt-4 pb-2">
            <h1 className="text-lg font-semibold">设置</h1>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-2">
            {renderTabList()}
          </div>
        </div>
      );
    }
    const currentTab = TABS.find(t => t.id === tab);
    return (
      <div className="h-full flex flex-col bg-background">
        <div className="px-4 pt-4 pb-2 flex items-center gap-3">
          <button
            onClick={() => setTab(null)}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-muted-foreground hover:bg-muted"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
          <h1 className="text-lg font-semibold">{currentTab?.label}</h1>
        </div>
        <div className="flex-1 overflow-y-auto">
          {renderContent()}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex">
      <div className="w-[200px] shrink-0 border-r border-border bg-card flex flex-col">
        <div className="px-4 py-5 border-b border-border">
          <span className="text-sm font-semibold text-foreground">设置</span>
        </div>
        <div className="flex-1 px-3 py-4">
          {renderTabList()}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto bg-background">
        {renderContent()}
      </div>
    </div>
  );
}
