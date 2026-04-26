import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { FEEDBACK_NORMAL } from "@/styles/ux-timing";
import { authFetch } from "@/store/auth-store";

interface ProviderConfig {
  api_key: string | null;
  has_api_key?: boolean;
  credential_source?: "platform" | "user";
  base_url: string | null;
}

interface ProvidersSectionProps {
  providers: Record<string, ProviderConfig>;
  onUpdate: (provider: string, config: ProviderConfig) => void;
}

const PROVIDER_CONFIGS = [
  {
    id: "anthropic",
    name: "Anthropic",
    icon: "🤖",
    defaultBaseUrl: "https://api.anthropic.com",
  },
  {
    id: "openai",
    name: "OpenAI",
    icon: "✨",
    defaultBaseUrl: "https://api.openai.com/v1",
  },
];

function isActiveSettingsRoute(): boolean {
  const path = window.location.pathname.replace(/\/+$/, "");
  return path === "/settings";
}

export default function ProvidersSection({ providers, onUpdate }: ProvidersSectionProps) {
  const [saving, setSaving] = useState<string | null>(null);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [drafts, setDrafts] = useState<Record<string, Partial<ProviderConfig>>>({});
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSave = async (
    providerId: string,
    config: ProviderConfig,
    persistedConfig: ProviderConfig = config,
  ) => {
    setSaving(providerId);
    setErrorMessage(null);

    try {
      const response = await authFetch("/api/settings/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: providerId,
          credential_source: config.credential_source ?? "platform",
          api_key: config.api_key,
          base_url: config.base_url,
        }),
      });
      if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);

      onUpdate(providerId, persistedConfig);
      setDrafts((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
      setSuccessMessage(providerId);
      setTimeout(() => setSuccessMessage(null), FEEDBACK_NORMAL);
    } catch (error) {
      // @@@provider-route-teardown - provider saves can resolve after
      // navigation already left /settings. Only log while the settings route
      // is still active; otherwise this is stale UI noise.
      if (!isActiveSettingsRoute()) return;
      console.error("Failed to save provider:", error);
      setErrorMessage(`保存失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center gap-3">
        <div className="w-1 h-6 bg-gradient-to-b from-info to-info rounded-full" />
        <h2 className="text-lg font-bold text-foreground">
          API 提供商
        </h2>
      </div>
      {errorMessage && (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PROVIDER_CONFIGS.map((providerConfig, index) => {
          const config = providers[providerConfig.id] || {
            api_key: null,
            has_api_key: false,
            credential_source: "platform" as const,
            base_url: null,
          };
          const draft = drafts[providerConfig.id] || {};
          const hasApiKey = !!config.api_key || !!config.has_api_key;
          const credentialSource = draft.credential_source || config.credential_source || (hasApiKey ? "user" : "platform");
          const apiKeyValue = "api_key" in draft ? draft.api_key || "" : config.api_key || "";
          const baseUrlValue = "base_url" in draft ? draft.base_url ?? null : config.base_url;
          const showKey = showKeys[providerConfig.id] || false;
          const isSaving = saving === providerConfig.id;
          const canSaveUserConfig = credentialSource !== "user" || apiKeyValue.length > 0 || hasApiKey;

          const updateDraft = (patch: Partial<ProviderConfig>) => {
            setDrafts((prev) => ({
              ...prev,
              [providerConfig.id]: { ...prev[providerConfig.id], ...patch },
            }));
          };

          const saveUserConfig = () => {
            if (!canSaveUserConfig) {
              setErrorMessage("请输入 API 密钥后再保存");
              return;
            }
            const payload: ProviderConfig = {
              api_key: apiKeyValue || null,
              has_api_key: hasApiKey,
              credential_source: "user",
              base_url: baseUrlValue,
            };
            const persisted: ProviderConfig = {
              api_key: null,
              has_api_key: true,
              credential_source: "user",
              base_url: baseUrlValue,
            };
            void handleSave(providerConfig.id, payload, persisted);
          };

          return (
            <div
              key={providerConfig.id}
              className="border border-border rounded-xl p-5 bg-card hover:border-info hover:shadow-lg hover:shadow-info/10 transition-all duration-normal space-y-4"
              style={{
                animation: `motionFadeInUp var(--duration-slow) var(--ease-out) calc(${index} * var(--duration-instant)) both`
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-foreground">
                    {providerConfig.name}
                  </h3>
                </div>
                {isSaving && (
                  <span className="text-xs text-info font-medium animate-pulse">保存中...</span>
                )}
                {successMessage === providerConfig.id && !isSaving && (
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-success/10 rounded-full animate-fadeIn">
                    <svg className="w-4 h-4 text-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-xs text-success font-medium">已保存</span>
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground">密钥来源</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    aria-label={`${providerConfig.name} 使用平台资源`}
                    onClick={() => {
                      const newConfig = { ...config, credential_source: "platform" as const, api_key: null };
                      const persistedConfig = { ...newConfig, has_api_key: false };
                      void handleSave(providerConfig.id, newConfig, persistedConfig);
                    }}
                    className={`rounded-lg border px-3 py-2 text-xs font-medium transition-colors duration-fast ${
                      credentialSource === "platform"
                        ? "border-info bg-info/10 text-info"
                        : "border-border text-muted-foreground hover:border-info/40"
                    }`}
                  >
                    使用平台资源
                  </button>
                  <button
                    type="button"
                    aria-label={`${providerConfig.name} 使用自己的 API Key`}
                    onClick={() => updateDraft({ credential_source: "user" })}
                    className={`rounded-lg border px-3 py-2 text-xs font-medium transition-colors duration-fast ${
                      credentialSource === "user"
                        ? "border-info bg-info/10 text-info"
                        : "border-border text-muted-foreground hover:border-info/40"
                    }`}
                  >
                    使用自己的 Key
                  </button>
                </div>
                <p className="text-2xs text-muted-foreground">
                  {credentialSource === "platform"
                    ? "默认使用平台资源额度。"
                    : hasApiKey
                      ? "当前提供商将使用你保存的密钥。"
                      : "输入密钥并保存后启用 BYOK。"}
                </p>
              </div>

              {credentialSource === "user" && (
                <>
                  {/* API Key */}
                  <div className="space-y-2">
                    <label className="text-xs font-medium text-muted-foreground">API 密钥</label>
                    <div className="relative">
                      <input
                        type={showKey ? "text" : "password"}
                        value={apiKeyValue}
                        onChange={(e) => updateDraft({
                          credential_source: "user",
                          api_key: e.target.value || null,
                        })}
                        placeholder={config.has_api_key ? "已配置；输入新密钥可替换" : `输入 ${providerConfig.name} API 密钥`}
                        className="w-full px-3 py-2 pr-10 border border-border rounded-lg text-sm text-foreground bg-muted font-mono hover:border-info focus:outline-none focus:border-info focus:ring-2 focus:ring-info/20 transition-all duration-normal"
                      />
                      {config.api_key && (
                        <button
                          onClick={() => setShowKeys({ ...showKeys, [providerConfig.id]: !showKey })}
                          className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-muted-foreground hover:text-info rounded transition-colors duration-fast"
                        >
                          {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Base URL Override */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id={`${providerConfig.id}-override`}
                        checked={!!baseUrlValue}
                        onChange={(e) => updateDraft({ base_url: e.target.checked ? providerConfig.defaultBaseUrl : null })}
                        className="w-4 h-4 rounded border-border text-info focus:ring-2 focus:ring-info/20"
                      />
                      <label htmlFor={`${providerConfig.id}-override`} className="text-xs font-medium text-muted-foreground">
                        自定义 Base URL
                      </label>
                    </div>

                    {baseUrlValue !== null && (
                      <input
                        type="text"
                        value={baseUrlValue || ""}
                        onChange={(e) => updateDraft({ base_url: e.target.value || null })}
                        placeholder={providerConfig.defaultBaseUrl}
                        className="w-full px-3 py-2 border border-border rounded-lg text-sm text-foreground bg-muted font-mono hover:border-info focus:outline-none focus:border-info focus:ring-2 focus:ring-info/20 transition-all duration-normal"
                      />
                    )}
                  </div>

                  <button
                    type="button"
                    aria-label={`保存 ${providerConfig.name} 设置`}
                    disabled={isSaving || !canSaveUserConfig}
                    onClick={saveUserConfig}
                    className="w-full rounded-lg border border-info/30 bg-info/10 px-3 py-2 text-xs font-medium text-info transition-colors duration-fast hover:bg-info/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    保存设置
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>

    </div>
  );
}
