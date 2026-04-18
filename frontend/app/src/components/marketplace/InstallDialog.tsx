import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useMarketplaceStore, type MarketplaceItemDetail } from "@/store/marketplace-store";
import { useAppStore } from "@/store/app-store";
import { toast } from "sonner";
import { marketplaceTypeLabel } from "@/lib/marketplace-types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: MarketplaceItemDetail;
}

export default function InstallDialog({ open, onOpenChange, item }: Props) {
  const download = useMarketplaceStore((s) => s.download);
  const downloading = useMarketplaceStore((s) => s.downloading);
  const agentList = useAppStore((s) => s.agentList);
  const ensureAgents = useAppStore((s) => s.ensureAgents);
  const [selectedAgentId, setSelectedAgentId] = useState("");

  const latestVersion = item.versions?.[0]?.version || "latest";
  const itemTypeLabel = marketplaceTypeLabel(item.type);
  const isSkill = item.type === "skill";
  const installableAgents = agentList.filter((agent) => !agent.builtin);

  useEffect(() => {
    if (!open || !isSkill) return;
    void ensureAgents();
  }, [ensureAgents, isSkill, open]);

  useEffect(() => {
    if (!isSkill || selectedAgentId || installableAgents.length === 0) return;
    setSelectedAgentId(installableAgents[0].id);
  }, [installableAgents, isSkill, selectedAgentId]);

  const handleDownload = async () => {
    try {
      const targetAgentId = isSkill ? selectedAgentId : undefined;
      if (isSkill && !targetAgentId) {
        toast.error("请先选择要安装 Skill 的 Agent");
        return;
      }
      const result = await download(item.id, targetAgentId);
      const resultTypeLabel = result.type === "user" ? "Agent" : result.type;
      toast.success(
        isSkill
          ? `${item.name} installed to Agent (${result.resource_id})`
          : `${item.name} downloaded to library (${resultTypeLabel})`,
      );
      onOpenChange(false);
    } catch (e) {
      toast.error(`Download failed: ${e instanceof Error ? e.message : "unknown error"}`);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Download className="w-4 h-4 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">下载 {item.name}</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                Version <span className="font-mono text-foreground">v{latestVersion}</span> by {item.publisher_username}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="py-3">
          <p className="text-sm text-muted-foreground">
            {isSkill
              ? "这将把该 Skill 直接安装到选中的 Agent，随后对话运行时可通过 load_skill 按需加载。"
              : `这将把该 ${itemTypeLabel} 保存到本地库，之后可以在 Agent 配置页中添加使用。`}
          </p>
          {isSkill && (
            <label className="block mt-3 text-xs text-muted-foreground">
              安装到 Agent
              <select
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={selectedAgentId}
                onChange={(event) => setSelectedAgentId(event.target.value)}
              >
                {installableAgents.map((agent) => (
                  <option key={agent.id} value={agent.id}>{agent.name}</option>
                ))}
              </select>
            </label>
          )}
          {item.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-3">
              {item.tags.map((tag) => (
                <span key={tag} className="text-2xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleDownload} disabled={downloading || (isSkill && !selectedAgentId)}>
            <Download className="w-3.5 h-3.5 mr-1.5" />
            {downloading ? "下载中..." : isSkill ? "安装到 Agent" : "下载到库"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
