import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";
import { inferLanguage } from "../shared/utils";

function parseArgs(args: unknown): { file_path?: string; content?: string } {
  if (args && typeof args === "object") return args as { file_path?: string; content?: string };
  return {};
}

export default memo(function WriteFileRenderer({ step, expanded }: ToolRendererProps) {
  const { file_path, content } = parseArgs(step.args);
  const shortPath = file_path?.split("/").filter(Boolean).pop() ?? "file";

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-foreground-secondary">写入</span>
        <code className="font-mono text-muted-foreground truncate max-w-[280px]">{file_path ?? shortPath}</code>
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
      </div>
    );
  }

  const displayContent = content || step.result || "";

  return (
    <div className="space-y-1.5">
      {displayContent && (
        <CodeBlock
          code={displayContent}
          language={inferLanguage(file_path)}
          maxLines={20}
        />
      )}
    </div>
  );
});
