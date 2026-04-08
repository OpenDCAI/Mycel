import { useState } from "react";
import { Tag } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { useAppStore } from "@/store/app-store";
import { useMarketplaceStore } from "@/store/marketplace-store";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: string;
}

type BumpType = "patch" | "minor" | "major";

function bumpVersion(version: string, type: BumpType): string {
  const [major, minor, patch] = version.split(".").map(Number);
  if (type === "major") return `${major + 1}.0.0`;
  if (type === "minor") return `${major}.${minor + 1}.0`;
  return `${major}.${minor}.${patch + 1}`;
}

export default function PublishDialog({ open, onOpenChange, agentId }: Props) {
  const agent = useAppStore(s => s.getAgentById(agentId));
  const publishAgent = useAppStore(s => s.publishAgent);
  const [bumpType, setBumpType] = useState<BumpType>("patch");
  const [notes, setNotes] = useState("");
  const [tags, setTags] = useState("");
  const [publishing, setPublishing] = useState(false);
  const publishToMarketplace = useMarketplaceStore(s => s.publishToMarketplace);

  if (!agent) return null;

  const newVersion = bumpVersion(agent.version, bumpType);

  const handlePublish = async () => {
    try {
      setPublishing(true);
      await publishAgent(agentId, bumpType);
      try {
        await publishToMarketplace(agentId, "member", bumpType, notes, tags.split(",").map(t => t.trim()).filter(Boolean), "public");
      } catch {
        // Hub publish is optional, don't fail the whole publish
      }
      toast.success(`${agent.name} v${newVersion} 已发布`);
      onOpenChange(false);
    } catch (e) {
      toast.error("发布失败，请重试");
    } finally {
      setPublishing(false);
    }
  };

  const bumps: { type: BumpType; label: string; desc: string }[] = [
    { type: "patch", label: "补丁", desc: "修复和微调" },
    { type: "minor", label: "次版本", desc: "新增功能" },
    { type: "major", label: "主版本", desc: "重大变更" },
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Tag className="w-4 h-4 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">发布 {agent.name}</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                当前版本 <span className="font-mono text-foreground">v{agent.version}</span>
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label className="text-sm">版本类型</Label>
            <div className="grid grid-cols-3 gap-2">
              {bumps.map((b) => (
                <button
                  key={b.type}
                  onClick={() => setBumpType(b.type)}
                  className={`p-2.5 rounded-lg border text-center transition-all duration-fast ${
                    bumpType === b.type
                      ? "border-primary/40 bg-primary/5"
                      : "border-border hover:border-primary/20"
                  }`}
                >
                  <p className="text-sm font-medium text-foreground">{b.label}</p>
                  <p className="text-2xs text-muted-foreground mt-0.5">{b.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="p-3 rounded-lg bg-muted text-center">
            <p className="text-xs text-muted-foreground">新版本号</p>
            <p className="text-lg font-mono font-semibold text-primary mt-0.5">v{newVersion}</p>
          </div>

          <div className="space-y-2">
            <Label className="text-sm">发布说明 <span className="text-muted-foreground text-xs">（可选）</span></Label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="描述此版本的变更..."
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label className="text-sm">Tags <span className="text-muted-foreground text-xs">(comma separated)</span></Label>
            <input
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder="e.g. coding, research, writing"
              className="w-full px-3 py-2 rounded-lg bg-card border border-border text-sm text-foreground placeholder:text-muted-foreground outline-none focus:border-primary/40"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handlePublish} disabled={publishing}>
            发布 v{newVersion}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
