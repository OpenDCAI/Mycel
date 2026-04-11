import { FolderOpen } from "lucide-react";
import { useState } from "react";
import { FEEDBACK_NORMAL } from "@/styles/ux-timing";
import { authFetch } from "@/store/auth-store";
import { asRecord, recordString } from "@/lib/records";

interface WorkspaceSectionProps {
  defaultWorkspace: string | null;
  onUpdate: (workspace: string) => void;
}

export default function WorkspaceSection({ defaultWorkspace, onUpdate }: WorkspaceSectionProps) {
  const [path, setPath] = useState(defaultWorkspace || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  function applySaveResponse(value: unknown): boolean {
    const data = asRecord(value);
    if (!data) {
      setError("保存失败");
      return false;
    }
    if (data.success === true) {
      const workspace = recordString(data, "workspace");
      if (!workspace) {
        setError("保存失败");
        return false;
      }
      onUpdate(workspace);
      setPath(workspace);
      setSuccess(true);
      setTimeout(() => setSuccess(false), FEEDBACK_NORMAL);
      return true;
    }
    setError(recordString(data, "detail") || "保存失败");
    return false;
  }

  const handleSave = async () => {
    if (!path.trim()) return;
    setSaving(true);
    setError("");
    setSuccess(false);
    try {
      const res = await authFetch("/api/settings/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: path.trim() }),
      });
      const data = await res.json();
      applySaveResponse(data);
    } catch {
      setError("网络错误");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="w-1 h-6 bg-gradient-to-b from-info to-info rounded-full" />
        <h2 className="text-lg font-bold text-foreground">
          本地工作区
        </h2>
      </div>
      <p className="text-xs text-muted-foreground">本地沙箱的默认工作目录</p>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <FolderOpen className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="~/workspace"
            className="w-full pl-8 pr-3 py-2 text-sm border border-border rounded-lg bg-card font-mono focus:outline-none focus:border-info transition-colors duration-fast"
          />
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !path.trim()}
          className="px-4 py-2 text-sm bg-info text-info-foreground rounded-lg hover:bg-info/90 disabled:opacity-50 transition-colors duration-fast"
        >
          {saving ? "保存中…" : success ? "已保存" : "保存"}
        </button>
      </div>
      {error && <div className="text-xs text-destructive">{error}</div>}
    </div>
  );
}
