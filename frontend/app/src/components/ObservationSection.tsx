import { Eye, EyeOff, Check, X, Loader2, ChevronRight } from "lucide-react";
import { useState } from "react";
import { saveObservationConfig, verifyObservation } from "../api";
import { asRecord } from "../lib/records";
import { FEEDBACK_BRIEF } from "@/styles/ux-timing";

interface ObservationSectionProps {
  config: Record<string, unknown>;
  onUpdate: (config: Record<string, unknown>) => void;
}

interface FieldDef {
  key: string;
  label: string;
  type: "text" | "password";
  required: boolean;
  placeholder?: string;
  helpText?: string;
  nested: string;
}

interface ProviderDef {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  fields: FieldDef[];
}

function LangfuseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M8 1L14 5.5V10.5L8 15L2 10.5V5.5L8 1Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M8 5.5L11 7.5V10L8 12L5 10V7.5L8 5.5Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
    </svg>
  );
}

function LangSmithIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M3 8H7M9 8H13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="8" r="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M4 4L6.5 6.5M9.5 9.5L12 12" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
const PROVIDERS: ProviderDef[] = [
  {
    id: "langfuse",
    name: "Langfuse",
    description: "开源 LLM 可观测性平台",
    icon: <LangfuseIcon />,
    fields: [
      { key: "secret_key", label: "Secret Key", type: "password", required: true, nested: "langfuse" },
      { key: "public_key", label: "Public Key", type: "password", required: true, nested: "langfuse" },
      { key: "host", label: "主机地址", type: "text", required: false, placeholder: "https://cloud.langfuse.com", helpText: "自托管 Langfuse 实例 URL", nested: "langfuse" },
    ],
  },
  {
    id: "langsmith",
    name: "LangSmith",
    description: "LangChain 追踪与评估平台",
    icon: <LangSmithIcon />,
    fields: [
      { key: "api_key", label: "API 密钥", type: "password", required: true, nested: "langsmith" },
      { key: "project", label: "项目名称", type: "text", required: false, placeholder: "default", helpText: "LangSmith 项目名称", nested: "langsmith" },
      { key: "endpoint", label: "端点", type: "text", required: false, placeholder: "https://api.smith.langchain.com", helpText: "自定义 API 端点", nested: "langsmith" },
    ],
  },
];

function getNestedValue(config: Record<string, unknown>, field: FieldDef): string {
  const nested = asRecord(config[field.nested]);
  return String(nested?.[field.key] ?? "");
}

function setNestedValue(config: Record<string, unknown>, field: FieldDef, value: string): Record<string, unknown> {
  const updated = { ...config };
  const nested = { ...(asRecord(config[field.nested]) || {}) };
  nested[field.key] = value || undefined;
  updated[field.nested] = nested;
  return updated;
}

function maskValue(val: string) {
  if (!val || val.length <= 8) return "•".repeat(val?.length || 0);
  return val.slice(0, 4) + "•".repeat(Math.min(val.length - 8, 20)) + val.slice(-4);
}

export default function ObservationSection({ config, onUpdate }: ObservationSectionProps) {
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [savedFields, setSavedFields] = useState<Record<string, boolean>>({});
  const [advancedOpen, setAdvancedOpen] = useState<Record<string, boolean>>({});
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ success: boolean; error?: string; traces?: unknown[] } | null>(null);

  const active = (config.active as string | null) ?? null;

  const handleActiveChange = async (providerId: string) => {
    const newActive = active === providerId ? null : providerId;
    const updated = { ...config, active: newActive };
    onUpdate(updated);
    setVerifyResult(null);
    try {
      await saveObservationConfig(newActive);
    } catch (err) {
      console.error("Failed to save observation config:", err);
    }
  };

  const handleFieldSave = async (providerId: string, field: FieldDef, value: string) => {
    const updatedConfig = setNestedValue(config, field, value);
    onUpdate(updatedConfig);
    try {
      await saveObservationConfig(
        updatedConfig.active as string | null,
        { [providerId]: updatedConfig[providerId] },
      );
      const fieldId = `${providerId}-${field.key}`;
      setSavedFields((prev) => ({ ...prev, [fieldId]: true }));
      setTimeout(() => setSavedFields((prev) => ({ ...prev, [fieldId]: false })), FEEDBACK_BRIEF);
    } catch (err) {
      console.error("Failed to save observation config:", err);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    try {
      const result = await verifyObservation();
      setVerifyResult(result);
    } catch (err) {
      setVerifyResult({ success: false, error: err instanceof Error ? err.message : "验证失败" });
    } finally {
      setVerifying(false);
    }
  };

  const renderField = (providerId: string, field: FieldDef) => {
    const value = getNestedValue(config, field);
    const showKeyId = `${providerId}-${field.key}`;
    const isSecret = field.type === "password";
    const showKey = showKeys[showKeyId] || false;
    const saved = savedFields[showKeyId] || false;

    return (
      <div key={field.key} className="space-y-1">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-muted-foreground">{field.label}</label>
          {!field.required && (
            <span className="text-2xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded">可选</span>
          )}
          {saved && (
            <span className="text-success animate-fadeIn"><Check className="w-3 h-3" /></span>
          )}
        </div>
        <div className="relative">
          <input
            type={isSecret && !showKey ? "password" : "text"}
            value={isSecret && !showKey ? maskValue(value) : value}
            onChange={(e) => void handleFieldSave(providerId, field, e.target.value)}
            onFocus={() => { if (isSecret && !showKey) setShowKeys((s) => ({ ...s, [showKeyId]: true })); }}
            placeholder={field.placeholder}
            className="w-full px-3 py-2 pr-10 border border-border rounded-lg text-sm text-foreground bg-card font-mono hover:border-border focus:outline-none focus:border-info focus:ring-2 focus:ring-info/20 transition-all duration-fast"
          />
          {isSecret && value && (
            <button
              onClick={() => setShowKeys((s) => ({ ...s, [showKeyId]: !showKey }))}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-muted-foreground rounded transition-colors duration-fast"
            >
              {showKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
        {field.helpText && <p className="text-xs text-muted-foreground mt-1">{field.helpText}</p>}
      </div>
    );
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">连接可观测性提供商以追踪 Agent 运行。同时只能激活一个提供商。</p>
      {PROVIDERS.map((provider) => {
        const isActive = active === provider.id;
        const requiredFields = provider.fields.filter((f) => f.required);
        const optionalFields = provider.fields.filter((f) => !f.required);
        const hasAdvanced = optionalFields.length > 0;
        const advOpen = advancedOpen[provider.id] || false;

        return (
          <div
            key={provider.id}
            className={`border rounded-xl bg-card transition-all duration-normal ${
              isActive
                ? "border-info shadow-lg shadow-info/5"
                : "border-border hover:border-border"
            }`}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4">
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                  isActive ? "bg-info/10 text-info" : "bg-muted text-muted-foreground"
                }`}>
                  {provider.icon}
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">{provider.name}</div>
                  <div className="text-xs text-muted-foreground">{provider.description}</div>
                </div>
              </div>
              {/* Toggle */}
              <button
                onClick={() => void handleActiveChange(provider.id)}
                className="relative w-9 h-5 rounded-full transition-colors duration-normal focus:outline-none focus:ring-2 focus:ring-info/20"
                style={{ backgroundColor: isActive ? "hsl(var(--info))" : "hsl(var(--border))" }}
                role="switch"
                aria-checked={isActive}
                aria-label={`切换 ${provider.name}`}
              >
                <span
                  className="absolute top-0.5 left-0.5 w-4 h-4 bg-card rounded-full shadow transition-transform duration-normal"
                  style={{ transform: isActive ? "translateX(var(--move-lg))" : "translateX(0)" }}
                />
              </button>
            </div>

            {/* Expandable body */}
            <div
              className="grid transition-[grid-template-rows] duration-normal ease-io"
              style={{ gridTemplateRows: isActive ? "1fr" : "0fr" }}
            >
              <div className="overflow-hidden">
                <div className="px-5 pb-5 space-y-4">
                  {/* Required fields */}
                  <div className="bg-muted rounded-lg p-4 space-y-3">
                    {requiredFields.map((field) => renderField(provider.id, field))}
                  </div>

                  {/* Optional fields */}
                  {hasAdvanced && (
                    <div>
                      <button
                        onClick={() => setAdvancedOpen((s) => ({ ...s, [provider.id]: !advOpen }))}
                        className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground-secondary transition-colors duration-fast"
                      >
                        <ChevronRight className={`w-3 h-3 transition-transform duration-fast ${advOpen ? "rotate-90" : ""}`} />
                        可选参数
                      </button>
                      <div
                        className="grid transition-[grid-template-rows] duration-fast ease-io"
                        style={{ gridTemplateRows: advOpen ? "1fr" : "0fr" }}
                      >
                        <div className="overflow-hidden">
                          <div className="pt-3 space-y-3">
                            {optionalFields.map((field) => renderField(provider.id, field))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Verify result banner */}
                  {verifyResult && (
                    <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs ${
                      verifyResult.success
                        ? "bg-success/5 border border-success/20 text-success"
                        : "bg-destructive/10 border border-destructive/20 text-destructive"
                    }`}>
                      {verifyResult.success
                        ? <><span className="w-1.5 h-1.5 rounded-full bg-success shrink-0" /> 已连接 · {(verifyResult.traces as unknown[])?.length ?? 0} 条近期追踪</>
                        : <><X className="w-3.5 h-3.5 shrink-0" /> 连接失败：{verifyResult.error}</>
                      }
                    </div>
                  )}

                  {/* Test Connection button */}
                  <div className="flex justify-end">
                    <button
                      onClick={() => void handleVerify()}
                      disabled={verifying}
                      className="text-xs font-medium text-info hover:text-info disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-fast flex items-center gap-1.5"
                    >
                      {verifying && <Loader2 className="w-3 h-3 animate-spin" />}
                      {verifying ? "测试中..." : "测试连接"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        );
      })}

    </div>
  );
}
