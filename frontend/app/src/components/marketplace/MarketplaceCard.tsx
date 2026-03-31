import { Download, GitFork, Star } from "lucide-react";
import type { MarketplaceItemSummary } from "@/store/marketplace-store";

const typeBadgeColors: Record<string, string> = {
  member: "bg-blue-500/10 text-blue-600",
  agent: "bg-purple-500/10 text-purple-600",
  skill: "bg-amber-500/10 text-amber-600",
  env: "bg-green-500/10 text-green-600",
};

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
        <h4 className="text-sm font-medium text-foreground group-hover:text-primary transition-colors truncate">
          {item.name}
        </h4>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium shrink-0 ${typeBadgeColors[item.type] || "bg-muted text-muted-foreground"}`}>
          {item.type}
        </span>
        {item.featured && (
          <Star className="w-3 h-3 text-amber-500 fill-amber-500 shrink-0" />
        )}
      </div>
      <p className="text-xs text-muted-foreground line-clamp-2">
        {item.description || "No description"}
      </p>
      <div className="flex items-center gap-3 mt-2 text-[11px] text-muted-foreground">
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
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
            hasUpdate ? "bg-primary/10 text-primary" : "bg-green-500/10 text-green-600"
          }`}>
            {hasUpdate ? "Update available" : "Installed"}
          </span>
        </div>
      )}
    </div>
  );
}
