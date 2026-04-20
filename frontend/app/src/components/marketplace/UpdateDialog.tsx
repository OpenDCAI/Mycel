import { RefreshCw } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useMarketplaceStore, type UpdateAvailable } from "@/store/marketplace-store";
import { useAppStore } from "@/store/app-store";
import { toast } from "sonner";
import { useState } from "react";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: string;
  update: UpdateAvailable;
  agentName: string;
}

export default function UpdateDialog({ open, onOpenChange, agentId, update, agentName }: Props) {
  const upgrade = useMarketplaceStore((s) => s.upgrade);
  const fetchAgents = useAppStore((s) => s.fetchAgents);
  const [upgrading, setUpgrading] = useState(false);

  const handleUpgrade = async () => {
    try {
      setUpgrading(true);
      await upgrade(agentId, update.marketplace_item_id);
      await fetchAgents();
      toast.success(`${agentName} updated to v${update.latest_version}`);
      onOpenChange(false);
    } catch (e) {
      toast.error(`Update failed: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setUpgrading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <RefreshCw className="w-4 h-4 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">更新 {agentName}</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                <span className="font-mono text-foreground">v{update.installed_version}</span> → <span className="font-mono text-primary">v{update.latest_version}</span>
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="py-3 space-y-3">
          {update.release_notes && (
            <div>
              <p className="text-xs font-medium text-foreground mb-1">Release Notes</p>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{update.release_notes}</p>
            </div>
          )}
          <div className="p-3 rounded-lg bg-warning/5 border border-warning/20">
            <p className="text-xs text-warning">This will overwrite your local configuration. Any local modifications will be lost.</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleUpgrade} disabled={upgrading}>
            {upgrading ? "更新中..." : "更新"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
