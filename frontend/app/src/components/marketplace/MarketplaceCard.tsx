import { Download, GitFork } from "lucide-react";
import type { MarketplaceItemSummary } from "@/store/marketplace-store";
import { typeBadgeColors } from "./constants";
import { marketplaceTypeLabel } from "@/lib/marketplace-types";

interface Props {
  item: MarketplaceItemSummary;
  onClick?: () => void;
  installed?: boolean;
  hasUpdate?: boolean;
}

export default function MarketplaceCard({ item, onClick, installed, hasUpdate }: Props) {
  return (
    <div
      onClick={onClick}
      className="surface-interactive p-4 cursor-pointer group relative"
    >
      <div className="flex items-center gap-2 mb-1.5">
        <h4 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors duration-fast truncate">
          {item.name}
        </h4>
        <span className={`text-2xs px-1.5 py-0.5 rounded-full font-medium shrink-0 ${typeBadgeColors[item.type] || "bg-muted text-muted-foreground"}`}>
          {marketplaceTypeLabel(item.type)}
        </span>
      </div>
      <p className="text-xs text-muted-foreground line-clamp-2">
        {item.description || "No description"}
      </p>
      <div className="flex items-center gap-3 mt-2 text-2xs text-muted-foreground">
        <span>{item.publisher_username}</span>
        <span className="flex items-center gap-1">
          <Download className="w-3 h-3" />
          {item.download_count}
        </span>
        {item.parent_id && (
          <span className="flex items-center gap-1">
            <GitFork className="w-3 h-3" />
            fork
          </span>
        )}
      </div>
      {installed && (
        <div className="absolute top-2 right-2">
          <span className={`text-2xs px-1.5 py-0.5 rounded-full font-medium ${
            hasUpdate ? "bg-primary/10 text-primary" : "bg-success/10 text-success"
          }`}>
            {hasUpdate ? "有可用更新" : "已安装"}
          </span>
        </div>
      )}
    </div>
  );
}
