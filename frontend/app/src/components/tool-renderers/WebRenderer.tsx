import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";
import { asRecord, recordString } from "@/lib/records";

function parseArgs(args: unknown): { url?: string; query?: string; prompt?: string } {
  const record = asRecord(args);
  if (!record) return {};
  return {
    url: recordString(record, "url"),
    query: recordString(record, "query"),
    prompt: recordString(record, "prompt"),
  };
}

export default memo(function WebRenderer({ step, expanded }: ToolRendererProps) {
  const { url, query, prompt } = parseArgs(step.args);
  let label = url || query || prompt || "";
  if (url) {
    try { label = new URL(url).hostname; } catch { /* keep raw */ }
  }

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-foreground-secondary">访问</span>
        <span className="truncate max-w-[280px]">{label}</span>
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
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
