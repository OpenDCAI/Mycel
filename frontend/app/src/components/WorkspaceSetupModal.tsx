import { useEffect, useState } from "react";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import FilesystemBrowser from "./FilesystemBrowser";
import { authFetch } from "@/store/auth-store";
import { asRecord, recordString } from "@/lib/records";

interface WorkspaceSetupModalProps {
  open: boolean;
  onClose: () => void;
  onWorkspaceSet: (workspace: string) => void;
}

export default function WorkspaceSetupModal({
  open,
  onClose,
  onWorkspaceSet,
}: WorkspaceSetupModalProps) {
  const [workspace, setWorkspace] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      // Pre-fill with user's home directory
      setWorkspace("~");
      setError("");
    }
  }, [open]);

  function handleBrowserSelect(path: string) {
    setWorkspace(path);
  }

  async function handleSave() {
    if (!workspace.trim()) {
      setError("请输入工作区路径");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const response = await authFetch("/api/settings/workspace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace: workspace.trim() }),
      });

      if (!response.ok) {
        const data = asRecord(await response.json());
        throw new Error(data ? recordString(data, "detail") || "保存失败" : "保存失败");
      }

      const data = asRecord(await response.json());
      const savedWorkspace = data ? recordString(data, "workspace") : undefined;
      if (!savedWorkspace) {
        throw new Error("保存失败");
      }
      onWorkspaceSet(savedWorkspace);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>设置默认工作区</DialogTitle>
          <DialogDescription>
            请选择一个文件夹作为默认工作区。所有新创建的会话将在此目录下工作。
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="browse" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="browse">浏览文件夹</TabsTrigger>
            <TabsTrigger value="manual">手动输入</TabsTrigger>
          </TabsList>

          <TabsContent value="browse" className="space-y-4">
            <FilesystemBrowser
              onSelect={handleBrowserSelect}
              initialPath="~"
            />
            {workspace && (
              <div className="text-sm text-muted-foreground">
                已选择: {workspace}
              </div>
            )}
          </TabsContent>

          <TabsContent value="manual" className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="workspace">工作区路径</Label>
              <Input
                id="workspace"
                value={workspace}
                onChange={(e) => setWorkspace(e.target.value)}
                placeholder="例如: ~/Projects 或 /Users/username/workspace"
              />
              <p className="text-sm text-muted-foreground">
                提示：可以使用 ~ 代表用户主目录
              </p>
            </div>
          </TabsContent>
        </Tabs>

        {error && <p className="text-sm text-red-500">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={saving || !workspace.trim()}>
            {saving ? "保存中..." : "保存"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
