import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";

function parseArgs(args: unknown): { pattern?: string; path?: string; glob?: string } {
  if (args && typeof args === "object") return args as { pattern?: string; path?: string; glob?: string };
  return {};
}

// Parse search result lines to find which display lines are actual matches.
// Grep output format: "path/to/file:linenum:content" for matches, "path/to/file-linenum-content" for context.
function parseMatchHighlights(result: string): number[] {
  const lines = result.split("\n");
  const highlights: number[] = [];
  lines.forEach((line, idx) => {
    if (/^[^:]+:\d+:/.test(line)) {
      highlights.push(idx + 1); // 1-based display line number
    }
  });
  return highlights;
}

export default memo(function SearchRenderer({ step, expanded }: ToolRendererProps) {
  const { pattern, path, glob: globPattern } = parseArgs(step.args);
  const query = pattern || globPattern || "";
  const shortPath = path?.split("/").filter(Boolean).pop() ?? "";

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-[#737373]">
        <span className="text-[#525252]">搜索</span>
        {query && <code className="font-mono text-[#737373] truncate max-w-[240px]">{query}</code>}
        {shortPath && <span className="text-[#a3a3a3]">in {shortPath}</span>}
        {step.status === "calling" && <span className="text-[#a3a3a3]">...</span>}
      </div>
    );
  }

  const highlights = step.result ? parseMatchHighlights(step.result) : [];

  return (
    <div className="space-y-1.5">
      {step.result && (
        <CodeBlock
          code={step.result}
          maxLines={20}
          highlights={highlights}
        />
      )}
    </div>
  );
});
