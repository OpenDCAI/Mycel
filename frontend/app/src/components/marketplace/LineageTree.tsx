import { GitFork, ChevronRight } from "lucide-react";
import type { LineageNode } from "@/store/marketplace-store";

interface Props {
  ancestors: LineageNode[];
  children: LineageNode[];
  currentName: string;
  onNodeClick?: (id: string) => void;
}

export default function LineageTree({ ancestors, children, currentName, onNodeClick }: Props) {
  if (ancestors.length === 0 && children.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <GitFork className="w-3.5 h-3.5" />
        <span>Lineage</span>
      </div>
      <div className="space-y-1">
        {/* Ancestors */}
        {ancestors.map((node, i) => (
          <div key={node.id} className="flex items-center gap-1.5" style={{ paddingLeft: `${i * 16}px` }}>
            <ChevronRight className="w-3 h-3 text-muted-foreground" />
            <button
              onClick={() => onNodeClick?.(node.id)}
              className="text-xs text-primary hover:underline truncate"
            >
              {node.name}
            </button>
            <span className="text-2xs text-muted-foreground">by {node.publisher_username}</span>
          </div>
        ))}

        {/* Current */}
        <div className="flex items-center gap-1.5" style={{ paddingLeft: `${ancestors.length * 16}px` }}>
          <ChevronRight className="w-3 h-3 text-foreground" />
          <span className="text-xs font-semibold text-foreground">{currentName}</span>
          <span className="text-2xs text-muted-foreground">(current)</span>
        </div>

        {/* Children */}
        {children.map((node) => (
          <div key={node.id} className="flex items-center gap-1.5" style={{ paddingLeft: `${(ancestors.length + 1) * 16}px` }}>
            <ChevronRight className="w-3 h-3 text-muted-foreground" />
            <button
              onClick={() => onNodeClick?.(node.id)}
              className="text-xs text-primary hover:underline truncate"
            >
              {node.name}
            </button>
            <span className="text-2xs text-muted-foreground">by {node.publisher_username}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
