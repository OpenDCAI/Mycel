import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";

function parseArgs(args: unknown): { url?: string; query?: string; prompt?: string } {
  if (args && typeof args === "object") return args as { url?: string; query?: string; prompt?: string };
  return {};
}

export default memo(function WebRenderer({ step, expanded }: ToolRendererProps) {
  const { url, query, prompt } = parseArgs(step.args);
  let label = url || query || prompt || "";
  if (url) {
    try { label = new URL(url).hostname; } catch { /* keep raw */ }
  }

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-[#737373]">
        <span className="text-[#525252]">访问</span>
        <span className="truncate max-w-[280px]">{label}</span>
        {step.status === "calling" && <span className="text-[#a3a3a3]">...</span>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {step.result && (
        <CodeBlock
          code={step.result}
          maxLines={20}
        />
      )}
    </div>
  );
});
