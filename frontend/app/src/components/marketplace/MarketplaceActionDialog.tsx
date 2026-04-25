import { PackagePlus, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useMarketplaceStore, type MarketplaceItemDetail } from "@/store/marketplace-store";
import { useAppStore } from "@/store/app-store";
import { toast } from "sonner";
import { HUB_AGENT_USER_ITEM_TYPE, marketplaceTypeLabel } from "@/lib/marketplace-types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: MarketplaceItemDetail;
}

export default function MarketplaceActionDialog({ open, onOpenChange, item }: Props) {
  const applyItem = useMarketplaceStore((s) => s.applyItem);
  const applying = useMarketplaceStore((s) => s.applying);
  const agentList = useAppStore((s) => s.agentList);
  const ensureAgents = useAppStore((s) => s.ensureAgents);
  const fetchAgents = useAppStore((s) => s.fetchAgents);
  const fetchLibrary = useAppStore((s) => s.fetchLibrary);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [assignToAgent, setAssignToAgent] = useState(false);

  const latestVersion = item.versions?.[0]?.version || "latest";
  const itemTypeLabel = marketplaceTypeLabel(item.type);
  const isSkill = item.type === "skill";
  const isHubAgentUser = item.type === HUB_AGENT_USER_ITEM_TYPE;
  const actionVerb = isHubAgentUser ? "添加" : "保存";
  const ActionIcon = isHubAgentUser ? UserPlus : PackagePlus;
  const targetAgents = agentList.filter((agent) => !agent.builtin);

  useEffect(() => {
    if (!open || !isSkill) return;
    void ensureAgents();
  }, [ensureAgents, isSkill, open]);

  useEffect(() => {
    if (!isSkill || selectedAgentId || targetAgents.length === 0) return;
    setSelectedAgentId(targetAgents[0].id);
  }, [targetAgents, isSkill, selectedAgentId]);

  const handleAction = async () => {
    try {
      const targetAgentId = isSkill && assignToAgent ? selectedAgentId : undefined;
      if (isSkill && assignToAgent && !targetAgentId) {
        toast.error("请先选择要接收该 Skill 的 Agent");
        return;
      }
      const result = await applyItem(item.id, targetAgentId);
      if (isSkill) {
        await fetchLibrary("skill");
        if (targetAgentId) await fetchAgents();
      } else if (isHubAgentUser) {
        await fetchAgents();
      }
      const resultTypeLabel = result.type === "user" ? "Agent" : result.type;
      toast.success(
        isSkill && targetAgentId
          ? `${item.name} 已保存到 Library，并已赋给 Agent`
          : isHubAgentUser
            ? `${item.name} 已添加到 Agent 列表`
          : `${item.name} 已保存到 ${result.type === "skill" ? "Library" : `Library（${resultTypeLabel}）`}`,
      );
      onOpenChange(false);
    } catch (e) {
      toast.error(`${actionVerb}失败：${e instanceof Error ? e.message : "unknown error"}`);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <ActionIcon className="w-4 h-4 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">{actionVerb} {item.name}</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                Version <span className="font-mono text-foreground">v{latestVersion}</span> by {item.publisher_username}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="py-3">
          <p className="text-sm text-muted-foreground">
            {isSkill
              ? "这将把该 Skill 保存到 Library，之后可以在 Agent 配置页中添加使用。"
              : isHubAgentUser
                ? "这将把该 Agent 添加到你的 Agent 列表。"
              : `这将把该 ${itemTypeLabel} 保存到 Library，之后可以在 Agent 配置页中添加使用。`}
          </p>
          {isSkill && (
            <div className="mt-3 space-y-2">
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 rounded border-border"
                  checked={assignToAgent}
                  disabled={targetAgents.length === 0}
                  onChange={(event) => setAssignToAgent(event.target.checked)}
                />
                保存到 Library 后赋给 Agent
              </label>
              {assignToAgent && (
                <label className="block text-xs text-muted-foreground">
                  选择 Agent
                  <select
                    className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                    value={selectedAgentId}
                    onChange={(event) => setSelectedAgentId(event.target.value)}
                  >
                    {targetAgents.map((agent) => (
                      <option key={agent.id} value={agent.id}>{agent.name}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
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
          <Button onClick={handleAction} disabled={applying || (isSkill && assignToAgent && !selectedAgentId)}>
            <ActionIcon className="w-3.5 h-3.5 mr-1.5" />
            {applying
              ? `${actionVerb}中...`
              : isSkill && assignToAgent
                ? "保存到 Library 并赋给 Agent"
                : isHubAgentUser
                  ? "添加 Agent"
                  : "保存到 Library"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
