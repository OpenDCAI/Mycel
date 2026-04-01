import { Download } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useMarketplaceStore, type MarketplaceItemDetail } from "@/store/marketplace-store";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  item: MarketplaceItemDetail;
}

export default function InstallDialog({ open, onOpenChange, item }: Props) {
  const download = useMarketplaceStore((s) => s.download);
  const downloading = useMarketplaceStore((s) => s.downloading);

  const latestVersion = item.versions?.[0]?.version || "latest";

  const handleDownload = async () => {
    try {
      const result = await download(item.id);
      toast.success(`${item.name} downloaded to library (${result.type})`);
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
            这将把该 {item.type} 保存到本地库，之后可以在成员配置页中添加使用。
          </p>
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
          <Button onClick={handleDownload} disabled={downloading}>
            <Download className="w-3.5 h-3.5 mr-1.5" />
            {downloading ? "下载中..." : "下载到库"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
