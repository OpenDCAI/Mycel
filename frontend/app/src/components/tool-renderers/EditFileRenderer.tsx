import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { DiffBlock } from "../shared/DiffBlock";

function parseArgs(args: unknown): { file_path?: string; old_string?: string; new_string?: string } {
  if (args && typeof args === "object") return args as { file_path?: string; old_string?: string; new_string?: string };
  return {};
}

export default memo(function EditFileRenderer({ step, expanded }: ToolRendererProps) {
  const { file_path, old_string, new_string } = parseArgs(step.args);
  const shortPath = file_path?.split("/").filter(Boolean).pop() ?? "file";

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="text-foreground-secondary">编辑</span>
        <code className="font-mono text-muted-foreground truncate max-w-[280px]">{file_path ?? shortPath}</code>
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {old_string && new_string && (
        <DiffBlock
          oldText={old_string}
          newText={new_string}
          fileName={file_path}
          maxLines={20}
        />
      )}
      {step.result && (
        <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[100px] overflow-y-auto font-mono bg-muted border border-border text-foreground-secondary">
          {step.result}
        </pre>
      )}
    </div>
  );
});
