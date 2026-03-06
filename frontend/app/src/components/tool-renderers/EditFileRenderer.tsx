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
      <div className="flex items-center gap-2 text-xs text-[#737373]">
        <span className="text-[#525252]">编辑</span>
        <code className="font-mono text-[#737373] truncate max-w-[280px]">{file_path ?? shortPath}</code>
        {step.status === "calling" && <span className="text-[#a3a3a3]">...</span>}
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
        <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[100px] overflow-y-auto font-mono bg-[#fafafa] border border-[#e5e5e5] text-[#525252]">
          {step.result}
        </pre>
      )}
    </div>
  );
});
