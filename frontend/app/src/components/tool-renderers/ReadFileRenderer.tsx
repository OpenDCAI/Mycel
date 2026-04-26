import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";
import { inferLanguage } from "../shared/utils";
import { asRecord, recordNumber, recordString } from "@/lib/records";

function parseArgs(args: unknown): { file_path?: string; limit?: number; offset?: number } {
  const record = asRecord(args);
  if (!record) return {};
  return {
    file_path: recordString(record, "file_path"),
    limit: recordNumber(record, "limit"),
    offset: recordNumber(record, "offset"),
  };
}

export default memo(function ReadFileRenderer({ step, expanded }: ToolRendererProps) {
  const { file_path, limit, offset } = parseArgs(step.args);
  const shortPath = file_path?.split("/").filter(Boolean).pop() ?? "file";
  const rangeHint = offset && limit ? ` L${offset}-${offset + limit}` : limit ? ` L1-${limit}` : "";

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-foreground-secondary">读取</span>
        <code className="font-mono text-muted-foreground truncate max-w-[280px]">{file_path ?? shortPath}</code>
        {rangeHint && <span className="text-muted-foreground/70">{rangeHint}</span>}
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {step.result && (
        <CodeBlock
          code={step.result}
          language={inferLanguage(file_path)}
          startLine={offset || 1}
          maxLines={20}
        />
      )}
    </div>
  );
});
