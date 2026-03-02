import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

interface ProviderConfig {
  api_key: string | null;
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

export default function ProvidersSection({ providers, onUpdate }: ProvidersSectionProps) {
  const [saving, setSaving] = useState<string | null>(null);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleSave = async (providerId: string, config: ProviderConfig) => {
    setSaving(providerId);
    onUpdate(providerId, config);

    try {
      await fetch("/api/settings/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: providerId,
          api_key: config.api_key,
          base_url: config.base_url,
        }),
      });

      // Show success feedback
      setSuccessMessage(providerId);
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (error) {
      console.error("Failed to save provider:", error);
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Section header */}
      <div className="flex items-center gap-3">
        <div className="w-1 h-6 bg-gradient-to-b from-[#0ea5e9] to-[#0284c7] rounded-full" />
        <h2 className="text-lg font-bold text-[#1e293b]" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
          API 提供商
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {PROVIDER_CONFIGS.map((providerConfig, index) => {
          const config = providers[providerConfig.id] || { api_key: null, base_url: null };
          const hasApiKey = !!config.api_key;
          const showKey = showKeys[providerConfig.id] || false;
          const isSaving = saving === providerConfig.id;

          return (
            <div
              key={providerConfig.id}
              className="border border-[#e2e8f0] rounded-xl p-5 bg-white hover:border-[#0ea5e9] hover:shadow-lg hover:shadow-[#0ea5e9]/10 transition-all duration-300 space-y-4"
              style={{
                animation: `fadeInUp 0.5s ease-out ${index * 0.1}s both`
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold text-[#1e293b]" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
                    {providerConfig.name}
                  </h3>
                </div>
                {isSaving && (
                  <span className="text-xs text-[#0ea5e9] font-medium animate-pulse">保存中...</span>
                )}
                {successMessage === providerConfig.id && !isSaving && (
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-[#10b981]/10 rounded-full animate-fadeIn">
                    <svg className="w-4 h-4 text-[#10b981]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-xs text-[#10b981] font-medium">已保存</span>
                  </div>
                )}
              </div>

              {/* API Key */}
              <div className="space-y-2">
                <label className="text-xs font-medium text-[#64748b]">API 密钥</label>
                <div className="relative">
                  <input
                    type={showKey ? "text" : "password"}
                    // @@@provider-key-value - Keep the real key in state; password type already masks UI text.
                    value={config.api_key || ""}
                    onChange={(e) => {
                      const newConfig = { ...config, api_key: e.target.value || null };
                      void handleSave(providerConfig.id, newConfig);
                    }}
                    placeholder={`输入 ${providerConfig.name} API 密钥`}
                    className="w-full px-3 py-2 pr-10 border border-[#e2e8f0] rounded-lg text-sm text-[#1e293b] bg-[#f8fafc] font-mono hover:border-[#0ea5e9] focus:outline-none focus:border-[#0ea5e9] focus:ring-2 focus:ring-[#0ea5e9]/20 transition-all duration-200"
                  />
                  {hasApiKey && (
                    <button
                      onClick={() => setShowKeys({ ...showKeys, [providerConfig.id]: !showKey })}
                      className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-[#94a3b8] hover:text-[#0ea5e9] rounded transition-colors"
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
                    checked={!!config.base_url}
                    onChange={(e) => {
                      const newConfig = {
                        ...config,
                        base_url: e.target.checked ? providerConfig.defaultBaseUrl : null,
                      };
                      void handleSave(providerConfig.id, newConfig);
                    }}
                    className="w-4 h-4 rounded border-[#e2e8f0] text-[#0ea5e9] focus:ring-2 focus:ring-[#0ea5e9]/20"
                  />
                  <label htmlFor={`${providerConfig.id}-override`} className="text-xs font-medium text-[#64748b]">
                    自定义 Base URL
                  </label>
                </div>

                {config.base_url !== null && (
                  <input
                    type="text"
                    value={config.base_url || ""}
                    onChange={(e) => {
                      const newConfig = { ...config, base_url: e.target.value || null };
                      void handleSave(providerConfig.id, newConfig);
                    }}
                    placeholder={providerConfig.defaultBaseUrl}
                    className="w-full px-3 py-2 border border-[#e2e8f0] rounded-lg text-sm text-[#1e293b] bg-[#f8fafc] font-mono hover:border-[#0ea5e9] focus:outline-none focus:border-[#0ea5e9] focus:ring-2 focus:ring-[#0ea5e9]/20 transition-all duration-200"
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        @keyframes fadeInUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }

        .animate-fadeIn {
          animation: fadeIn 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}
