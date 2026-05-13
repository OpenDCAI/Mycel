import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { asRecord } from "@/lib/records";

function summarizeArgs(args: unknown): string {
  if (!args) return "";
  if (typeof args === "string") return args.slice(0, 80);
  const obj = asRecord(args);
  if (obj) {
    const keys = Object.keys(obj);
    if (keys.length === 0) return "";
    // Show first meaningful value
    for (const k of keys) {
      const v = obj[k];
      if (typeof v === "string" && v.length > 0) return v.slice(0, 80);
    }
    return keys.join(", ");
  }
  return "";
}

export default memo(function DefaultRenderer({ step, expanded }: ToolRendererProps) {
  if (!expanded) {
    const summary = summarizeArgs(step.args);
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {summary && <span className="truncate max-w-[320px]">{summary}</span>}
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {step.args !== undefined && (
        <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[200px] overflow-y-auto font-mono bg-muted border border-border text-foreground-secondary">
          {typeof step.args === "string" ? step.args : JSON.stringify(step.args, null, 2)}
        </pre>
      )}
      {step.result && (
        <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[200px] overflow-y-auto font-mono bg-muted border border-border text-foreground-secondary">
          {step.result}
        </pre>
      )}
    </div>
  );
});
