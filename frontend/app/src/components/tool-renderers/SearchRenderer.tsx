import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";
import { asRecord, recordString } from "@/lib/records";

function parseArgs(args: unknown): { pattern?: string; path?: string; glob?: string } {
  const record = asRecord(args);
  if (!record) return {};
  return {
    pattern: recordString(record, "pattern"),
    path: recordString(record, "path"),
    glob: recordString(record, "glob"),
  };
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
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-foreground-secondary">搜索</span>
        {query && <code className="font-mono text-muted-foreground truncate max-w-[240px]">{query}</code>}
        {shortPath && <span className="text-muted-foreground/70">in {shortPath}</span>}
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
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
