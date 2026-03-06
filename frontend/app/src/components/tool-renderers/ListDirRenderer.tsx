import { memo } from "react";
import type { ToolRendererProps } from "./types";
import { CodeBlock } from "../shared/CodeBlock";

function parseArgs(args: unknown): { path?: string; dir_path?: string } {
  if (args && typeof args === "object") return args as { path?: string; dir_path?: string };
  return {};
}

export default memo(function ListDirRenderer({ step, expanded }: ToolRendererProps) {
  const { path, dir_path } = parseArgs(step.args);
  const dirPath = path || dir_path || ".";

  if (!expanded) {
    return (
      <div className="flex items-center gap-2 text-xs text-[#737373]">
        <span className="text-[#525252]">浏览</span>
        <code className="font-mono text-[#737373] truncate max-w-[280px]">{dirPath}</code>
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
