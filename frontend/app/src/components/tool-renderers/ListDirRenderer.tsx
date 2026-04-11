import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";
import { asRecord, recordString } from "@/lib/records";

function parseArgs(args: unknown): { path?: string; dir_path?: string } {
  const record = asRecord(args);
  if (!record) return {};
  return {
    path: recordString(record, "path"),
    dir_path: recordString(record, "dir_path"),
  };
}

export default memo(function ListDirRenderer({ step, expanded }: ToolRendererProps) {
  const { path, dir_path } = parseArgs(step.args);
  const dirPath = path || dir_path || ".";

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-foreground-secondary">浏览</span>
        <code className="font-mono text-muted-foreground truncate max-w-[280px]">{dirPath}</code>
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
