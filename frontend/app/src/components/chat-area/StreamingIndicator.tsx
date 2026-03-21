import type { AssistantTurn, StreamStatus } from "../../api";

interface StreamingIndicatorProps {
  entries: AssistantTurn[];
  runtimeStatus: StreamStatus | null;
}

export function StreamingIndicator({ entries, runtimeStatus }: StreamingIndicatorProps) {
  if (entries.length === 0) return null;

  const lastEntry = entries[entries.length - 1];
  if (lastEntry.role !== "assistant") return null;

  const hasContent = lastEntry.segments?.some(s =>
    (s.type === 'text' && s.content.trim()) || s.type === 'tool'
  );

  if (hasContent) return null;

  return (
    <div className="flex items-center animate-fade-in">
      <span className="text-sm text-[#a3a3a3]">
        {runtimeStatus?.current_tool
          ? `Mycel 正在使用 ${runtimeStatus.current_tool}...`
          : "Mycel 正在思考..."}
      </span>
    </div>
  );
}
