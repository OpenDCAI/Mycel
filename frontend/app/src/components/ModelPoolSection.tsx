
import { useState } from "react";

interface Model {
  id: string;
  name: string;
  custom?: boolean;
  provider?: string;
}

interface ModelPoolSectionProps {
  models: Model[];
  enabledModels: string[];
  customConfig: Record<string, { based_on?: string | null; context_limit?: number | null }>;
  providers: Record<string, { api_key: string | null; base_url: string | null }>;
  onToggle: (modelId: string, enabled: boolean) => void;
  onAddCustomModel: (modelId: string, provider: string, basedOn?: string, contextLimit?: number) => Promise<void>;
  onRemoveCustomModel: (modelId: string) => Promise<void>;
}

export default function ModelPoolSection({ models, enabledModels, customConfig, providers, onToggle, onAddCustomModel, onRemoveCustomModel }: ModelPoolSectionProps) {
  const [toggling, setToggling] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [testStatus, setTestStatus] = useState<Record<string, "idle" | "testing" | "ok" | "fail">>({});
  const [testError, setTestError] = useState<Record<string, string>>({});
  const [selectedProvider, setSelectedProvider] = useState("");
  const [addAlias, setAddAlias] = useState("");
  const [addContextLimit, setAddContextLimit] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [editingModel, setEditingModel] = useState<string | null>(null);
  const [editAlias, setEditAlias] = useState("");
  const [editContextLimit, setEditContextLimit] = useState("");

  const handleToggle = async (modelId: string, enabled: boolean) => {
    setToggling(modelId);
    onToggle(modelId, enabled);
    try {
      await fetch("/api/settings/models/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId, enabled }),
      });
      setSuccessMessage(enabled ? "模型已启用" : "模型已禁用");
      setTimeout(() => setSuccessMessage(null), 2000);
    } finally {
      setToggling(null);
    }
  };

  const handleTest = async (modelId: string) => {
    setTestStatus((s) => ({ ...s, [modelId]: "testing" }));
    setTestError((s) => ({ ...s, [modelId]: "" }));
    try {
      const res = await fetch("/api/settings/models/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId }),
      });
      const data = await res.json();
      setTestStatus((s) => ({ ...s, [modelId]: data.success ? "ok" : "fail" }));
      if (!data.success) setTestError((s) => ({ ...s, [modelId]: data.error || "测试失败" }));
    } catch {
      setTestStatus((s) => ({ ...s, [modelId]: "fail" }));
      setTestError((s) => ({ ...s, [modelId]: "网络错误" }));
    }
  };

  const handleSaveConfig = async (modelId: string) => {
    await fetch("/api/settings/models/custom/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_id: modelId,
        based_on: editAlias || null,
        context_limit: editContextLimit ? parseInt(editContextLimit) : null,
      }),
    });
    setEditingModel(null);
    setSuccessMessage("配置已保存");
    setTimeout(() => setSuccessMessage(null), 2000);
  };

  const handleAdd = async () => {
    if (!searchQuery.trim() || !selectedProvider) return;
    setAdding(true);
    try {
      await onAddCustomModel(
        searchQuery.trim(),
        selectedProvider,
        addAlias || undefined,
        addContextLimit ? parseInt(addContextLimit) : undefined,
      );
      setSearchQuery("");
      setSelectedProvider("");
      setAddAlias("");
      setAddContextLimit("");
      setShowAdvanced(false);
      setSuccessMessage("模型已添加");
      setTimeout(() => setSuccessMessage(null), 2000);
    } finally {
      setAdding(false);
    }
  };

  const providerNames = Object.keys(providers);
  const filtered = models.filter((m) => m.id.toLowerCase().includes(searchQuery.toLowerCase()));
  const sorted = [...filtered].sort((a, b) => {
    const aOn = enabledModels.includes(a.id) ? 0 : 1;
    const bOn = enabledModels.includes(b.id) ? 0 : 1;
    return aOn - bOn;
  });
  const exactMatch = models.some((m) => m.id.toLowerCase() === searchQuery.toLowerCase());
  const showAddForm = searchQuery.trim() && !exactMatch;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-[#1e293b]">模型池</h3>
          <p className="text-xs text-[#94a3b8]">启用/禁用模型，添加自定义模型</p>
        </div>
        {successMessage && (
          <span className="text-xs text-[#10b981] bg-[#10b981]/10 px-2 py-1 rounded">{successMessage}</span>
        )}
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="搜索或输入模型 ID..."
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        className="w-full px-3 py-2 text-sm border border-[#e2e8f0] rounded-lg bg-white focus:outline-none focus:border-[#0ea5e9] transition-colors"
      />

      {/* Add custom model form */}
      {showAddForm && (
        <div className="border border-dashed border-[#0ea5e9]/40 rounded-lg bg-[#f0f9ff]/50 p-4 space-y-3">
          <div className="text-sm font-medium text-[#0ea5e9]">添加 "{searchQuery.trim()}"</div>
          <div className="flex gap-2">
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              className="flex-1 px-3 py-1.5 text-sm border border-[#e2e8f0] rounded-lg bg-white focus:outline-none focus:border-[#0ea5e9]"
            >
              <option value="" disabled>选择提供商</option>
              {providerNames.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <button
              onClick={handleAdd}
              disabled={adding || !selectedProvider}
              className="px-4 py-1.5 text-sm bg-[#0ea5e9] text-white rounded-lg hover:bg-[#0ea5e9]/90 disabled:opacity-50 transition-colors"
            >
              {adding ? "添加中..." : "添加"}
            </button>
          </div>
          {/* Collapsible advanced */}
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-[#94a3b8] hover:text-[#64748b] transition-colors"
          >
            {showAdvanced ? "▾ 高级选项" : "▸ 高级选项"}
          </button>
          {showAdvanced && (
            <div className="grid grid-cols-2 gap-2">
              <input
                type="text"
                placeholder="基于（如 deepseek-chat）"
                value={addAlias}
                onChange={(e) => setAddAlias(e.target.value)}
                className="px-3 py-1.5 text-sm border border-[#e2e8f0] rounded-lg bg-white focus:outline-none focus:border-[#0ea5e9]"
              />
              <input
                type="number"
                placeholder="上下文限制"
                value={addContextLimit}
                onChange={(e) => setAddContextLimit(e.target.value)}
                className="px-3 py-1.5 text-sm border border-[#e2e8f0] rounded-lg bg-white focus:outline-none focus:border-[#0ea5e9]"
              />
            </div>
          )}
        </div>
      )}

      {/* Model list */}
      <div className="max-h-[400px] overflow-y-auto space-y-1">
        {sorted.map((model) => {
          const enabled = enabledModels.includes(model.id);
          const cfg = customConfig[model.id];
          const status = testStatus[model.id];
          const isEditing = editingModel === model.id;
          return (
            <div key={model.id}>
              <div className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${enabled ? "bg-white" : "bg-[#f8f9fa]"}`}>
                <button
                  onClick={() => handleToggle(model.id, !enabled)}
                  disabled={toggling === model.id}
                  className={`w-8 h-4 rounded-full transition-colors relative shrink-0 ${enabled ? "bg-[#0ea5e9]" : "bg-[#cbd5e1]"}`}
                >
                  <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-transform ${enabled ? "left-4" : "left-0.5"}`} />
                </button>
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-[#1e293b] truncate block">{model.id}</span>
                  {cfg?.based_on && <span className="text-[10px] text-[#94a3b8]">based on: {cfg.based_on}</span>}
                </div>
                {model.custom && <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#f0f9ff] text-[#0ea5e9]">自定义</span>}
                <div className="flex gap-1 shrink-0">
                  {model.custom && (
                    <>
                      <button
                        onClick={() => {
                          if (isEditing) { setEditingModel(null); } else {
                            setEditingModel(model.id);
                            setEditAlias(cfg?.based_on || "");
                            setEditContextLimit(cfg?.context_limit?.toString() || "");
                          }
                        }}
                        className="text-[11px] px-2 py-0.5 rounded border border-[#e2e8f0] text-[#64748b] hover:border-[#94a3b8] transition-colors"
                      >
                        {isEditing ? "关闭" : "配置"}
                      </button>
                      <button
                        onClick={() => onRemoveCustomModel(model.id)}
                        className="text-[11px] px-2 py-0.5 rounded border border-[#e2e8f0] text-[#ef4444] hover:border-[#ef4444] transition-colors"
                      >
                        移除
                      </button>
                    </>
                  )}
                  {(status === "ok" || status === "fail") ? (
                    <div className="flex items-center gap-1">
                      <span className={`text-[11px] px-1.5 py-0.5 rounded ${status === "ok" ? "text-[#10b981]" : "text-[#ef4444]"}`}>
                        {status === "ok" ? "✓" : "✗"}
                      </span>
                      <button
                        onClick={() => {
                          setTestStatus((s) => ({ ...s, [model.id]: "idle" }));
                          setTestError((s) => ({ ...s, [model.id]: "" }));
                        }}
                        className="text-[11px] px-1 py-0.5 rounded text-[#94a3b8] hover:text-[#64748b] transition-colors"
                        title="关闭"
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => handleTest(model.id)}
                      disabled={status === "testing"}
                      className="text-[11px] px-2 py-0.5 rounded border border-[#e2e8f0] text-[#64748b] hover:border-[#94a3b8] disabled:opacity-50 transition-colors"
                    >
                      {status === "testing" ? "测试中…" : "测试"}
                    </button>
                  )}
                </div>
              </div>
              {status === "fail" && testError[model.id] && (
                <div className="mx-3 mt-1 text-[11px] text-[#ef4444]">{testError[model.id]}</div>
              )}
              {isEditing && (
                <div className="mx-3 mt-2 mb-1 p-3 border border-[#e2e8f0] rounded-lg bg-[#f8f9fa] space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[11px] text-[#94a3b8] block mb-1">基于模型</label>
                      <input type="text" placeholder="如 deepseek-chat" value={editAlias} onChange={(e) => setEditAlias(e.target.value)}
                        className="w-full px-2 py-1 text-sm border border-[#e2e8f0] rounded bg-white focus:outline-none focus:border-[#0ea5e9]" />
                    </div>
                    <div>
                      <label className="text-[11px] text-[#94a3b8] block mb-1">上下文限制</label>
                      <input type="number" placeholder="上下文限制" value={editContextLimit} onChange={(e) => setEditContextLimit(e.target.value)}
                        className="w-full px-2 py-1 text-sm border border-[#e2e8f0] rounded bg-white focus:outline-none focus:border-[#0ea5e9]" />
                    </div>
                  </div>
                  <button onClick={() => handleSaveConfig(model.id)}
                    className="text-xs px-3 py-1 bg-[#0ea5e9] text-white rounded hover:bg-[#0ea5e9]/90 transition-colors">
                    保存
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
