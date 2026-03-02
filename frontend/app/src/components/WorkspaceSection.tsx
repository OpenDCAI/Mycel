import { FolderOpen } from "lucide-react";
import { useState } from "react";

interface WorkspaceSectionProps {
  defaultWorkspace: string | null;
  onUpdate: (workspace: string) => void;
}

export default function WorkspaceSection({ defaultWorkspace, onUpdate }: WorkspaceSectionProps) {
  const [path, setPath] = useState(defaultWorkspace || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSave = async () => {
    if (!path.trim()) return;
    setSaving(true);
    setError("");
    setSuccess(false);
    try {
      const res = await fetch("/api/settings/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: path.trim() }),
      });
      const data = await res.json();
      if (data.success) {
        onUpdate(data.workspace);
        setPath(data.workspace);
        setSuccess(true);
        setTimeout(() => setSuccess(false), 2000);
      } else {
        setError(data.detail || "保存失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="w-1 h-6 bg-gradient-to-b from-[#0ea5e9] to-[#0284c7] rounded-full" />
        <h2 className="text-lg font-bold text-[#1e293b]" style={{ fontFamily: 'Inter, system-ui, sans-serif' }}>
          本地工作区
        </h2>
      </div>
      <p className="text-xs text-[#94a3b8]">本地沙箱的默认工作目录</p>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <FolderOpen className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#94a3b8]" />
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="~/workspace"
            className="w-full pl-8 pr-3 py-2 text-sm border border-[#e2e8f0] rounded-lg bg-white font-mono focus:outline-none focus:border-[#0ea5e9] transition-colors"
          />
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !path.trim()}
          className="px-4 py-2 text-sm bg-[#0ea5e9] text-white rounded-lg hover:bg-[#0ea5e9]/90 disabled:opacity-50 transition-colors"
        >
          {saving ? "保存中…" : success ? "已保存" : "保存"}
        </button>
      </div>
      {error && <div className="text-xs text-[#ef4444]">{error}</div>}
    </div>
  );
}
