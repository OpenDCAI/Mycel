import { ChevronDown, Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { saveSandboxConfig } from "../api";

interface SandboxSectionProps {
  sandboxes: Record<string, Record<string, unknown>>;
  onUpdate: (name: string, config: Record<string, unknown>) => void;
}

interface FieldDef {
  key: string;
  label: string;
  type: "text" | "password" | "number" | "select";
  options?: string[];
  placeholder?: string;
  nested?: string;
}

// @@@ field-lookup-by-provider-type - one field table per provider type lets multiple named configs reuse the same schema
const PROVIDER_FIELDS: Record<string, FieldDef[]> = {
  agentbay: [
    { key: "api_key", label: "API 密钥", type: "password", nested: "agentbay" },
    { key: "region_id", label: "区域", type: "text", placeholder: "ap-southeast-1", nested: "agentbay" },
    { key: "context_path", label: "上下文路径", type: "text", placeholder: "/home/wuying", nested: "agentbay" },
    { key: "image_id", label: "镜像 ID", type: "text", nested: "agentbay" },
  ],
  docker: [
    { key: "image", label: "镜像", type: "text", placeholder: "python:3.12-slim", nested: "docker" },
    { key: "mount_path", label: "挂载路径", type: "text", placeholder: "/workspace", nested: "docker" },
  ],
  e2b: [
    { key: "api_key", label: "API 密钥", type: "password", nested: "e2b" },
    { key: "template", label: "模板", type: "text", placeholder: "base", nested: "e2b" },
    { key: "cwd", label: "工作目录", type: "text", placeholder: "/home/user", nested: "e2b" },
    { key: "timeout", label: "超时 (秒)", type: "number", nested: "e2b" },
  ],
  daytona: [
    { key: "api_key", label: "API 密钥", type: "password", nested: "daytona" },
    { key: "api_url", label: "API URL", type: "text", placeholder: "https://app.daytona.io/api", nested: "daytona" },
    { key: "target", label: "目标", type: "text", placeholder: "local", nested: "daytona" },
    { key: "cwd", label: "工作目录", type: "text", placeholder: "/home/daytona", nested: "daytona" },
  ],
};

const COMMON_FIELDS: FieldDef[] = [
  { key: "on_exit", label: "退出时", type: "select", options: ["pause", "destroy"] },
  { key: "init_commands", label: "初始化命令", type: "text", placeholder: "逗号分隔的命令" },
];

function getNestedValue(config: Record<string, unknown>, field: FieldDef): string {
  if (field.nested) {
    const nested = config[field.nested] as Record<string, unknown> | undefined;
    return String(nested?.[field.key] ?? "");
  }
  if (field.key === "init_commands") {
    const cmds = config[field.key];
    return Array.isArray(cmds) ? cmds.join(", ") : "";
  }
  return String(config[field.key] ?? "");
}

function setNestedValue(config: Record<string, unknown>, field: FieldDef, value: string): Record<string, unknown> {
  const updated = { ...config };
  if (field.nested) {
    const nested = { ...(config[field.nested] as Record<string, unknown> || {}) };
    nested[field.key] = field.type === "number" ? (Number(value) || 0) : (value || undefined);
    updated[field.nested] = nested;
  } else if (field.key === "init_commands") {
    updated[field.key] = value ? value.split(",").map((s) => s.trim()).filter(Boolean) : [];
  } else {
    updated[field.key] = value || undefined;
  }
  return updated;
}

function displayName(name: string): string {
  return name
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function SandboxSection({ sandboxes, onUpdate }: SandboxSectionProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  const handleSave = async (configName: string, config: Record<string, unknown>) => {
    setSaving(configName);
    onUpdate(configName, config);
    try {
      await saveSandboxConfig(configName, config);
    } catch (error) {
      console.error("Failed to save sandbox config:", error);
    } finally {
      setSaving(null);
    }
  };

  const maskValue = (val: string) => {
    if (!val || val.length <= 8) return "*".repeat(val?.length || 0);
    return val.slice(0, 4) + "*".repeat(Math.min(val.length - 8, 20)) + val.slice(-4);
  };

  const renderField = (configName: string, field: FieldDef, config: Record<string, unknown>) => {
    const value = getNestedValue(config, field);
    const showKeyId = `${configName}-${field.key}`;
    const isSecret = field.type === "password";
    const showKey = showKeys[showKeyId] || false;
    // @@@masked-secret-input-guard - keep masked secrets non-editable to avoid persisting placeholder asterisks as real credentials
    const isMaskedSecret = isSecret && !showKey && value.length > 0;

    if (field.type === "select") {
      return (
        <select
          value={value || field.options?.[0] || ""}
          onChange={(e) => void handleSave(configName, setNestedValue(config, field, e.target.value))}
          className="flex-1 min-w-0 px-2 py-1 border border-[#e2e8f0] rounded text-xs text-[#1e293b] bg-[#f8fafc] focus:outline-none focus:border-[#0ea5e9] transition-colors"
        >
          {field.options?.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      );
    }

    return (
      <div className="relative flex-1 min-w-0">
        <input
          type={isSecret && !showKey ? "password" : "text"}
          value={isMaskedSecret ? maskValue(value) : value}
          readOnly={isMaskedSecret}
          onChange={(e) => {
            if (isMaskedSecret) return;
            void handleSave(configName, setNestedValue(config, field, e.target.value));
          }}
          placeholder={field.placeholder}
          title={isMaskedSecret ? "点击眼睛图标进行编辑" : undefined}
          className="w-full px-2 py-1 pr-7 border border-[#e2e8f0] rounded text-xs text-[#1e293b] bg-[#f8fafc] font-mono focus:outline-none focus:border-[#0ea5e9] transition-colors"
        />
        {isSecret && value && (
          <button
            onClick={() => setShowKeys({ ...showKeys, [showKeyId]: !showKey })}
            className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 text-[#94a3b8] hover:text-[#0ea5e9] rounded transition-colors"
          >
            {showKey ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
          </button>
        )}
      </div>
    );
  };

  const entries = Object.entries(sandboxes);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="w-1 h-6 bg-gradient-to-b from-[#0ea5e9] to-[#0284c7] rounded-full" />
        <h2 className="text-lg font-bold text-[#1e293b]" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
          沙箱提供商
        </h2>
        <span className="text-xs text-[#94a3b8]">{entries.length} 个配置</span>
      </div>

      <div className="border border-[#e2e8f0] rounded-lg overflow-hidden divide-y divide-[#e2e8f0]">
        {entries.map(([configName, rawConfig]) => {
          const config = rawConfig as Record<string, unknown>;
          const providerType = String(config.provider ?? configName);
          const fields = PROVIDER_FIELDS[providerType] ?? [];
          const isExpanded = expanded === configName;
          const isSaving = saving === configName;

          return (
            <div key={configName}>
              <button
                onClick={() => setExpanded(isExpanded ? null : configName)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-[#f8fafc] transition-colors"
              >
                <ChevronDown className={`w-3.5 h-3.5 text-[#94a3b8] transition-transform duration-150 ${isExpanded ? "" : "-rotate-90"}`} />
                <span className="text-sm font-medium text-[#1e293b]">{displayName(configName)}</span>
                {configName !== providerType && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#f1f5f9] text-[#64748b]">{providerType}</span>
                )}
                <span className="text-[10px] text-[#cbd5e1] ml-auto">
                  {isSaving ? "保存中..." : `${fields.length + COMMON_FIELDS.length} 个字段`}
                </span>
              </button>

              {isExpanded && (
                <div className="px-4 pb-3 pt-1 bg-[#fafbfc]">
                  <div className="space-y-1.5">
                    {[...fields, ...COMMON_FIELDS].map((field) => (
                      <div key={field.key} className="flex items-center gap-3">
                        <label className="w-24 shrink-0 text-xs text-[#64748b] text-right">{field.label}</label>
                        {renderField(configName, field, config)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
