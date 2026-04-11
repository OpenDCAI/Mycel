import { Check, Copy } from "lucide-react";
import { memo, useCallback, useState } from "react";
import type { ToolRendererProps } from "./types";
import { asRecord } from "@/lib/records";
import { FEEDBACK_BRIEF } from "@/styles/ux-timing";

function parseArgs(args: unknown): { command?: string; description?: string } {
  const a = asRecord(args);
  if (!a) return {};
  return {
    command: a.command as string | undefined,
    description: a.description as string | undefined,
  };
}

function CopyInline({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), FEEDBACK_BRIEF);
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="flex-shrink-0 p-0.5 rounded text-muted-foreground/70 hover:text-foreground-secondary hover:bg-muted transition-colors duration-fast"
      title="复制命令"
    >
      {copied ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
    </button>
  );
}

export default memo(function BashRenderer({ step, expanded }: ToolRendererProps) {
  const { command, description } = parseArgs(step.args);
  const [outputExpanded, setOutputExpanded] = useState(false);
  const outputLines = step.result?.split("\n") || [];
  const needsOutputExpansion = outputLines.length > 15;
  const displayOutput = outputExpanded ? step.result : outputLines.slice(0, 15).join("\n");

  if (!expanded) {
    return (
      <div className="group flex items-center gap-2 text-xs text-muted-foreground">
        {command && (
          <code className="font-mono text-muted-foreground truncate max-w-[320px]">{command}</code>
        )}
        {!command && description && (
          <span className="text-muted-foreground/70 truncate max-w-[280px]">{description}</span>
        )}
        {step.status === "calling" && <span className="text-muted-foreground/70">...</span>}
        {command && (
          <span className="opacity-0 group-hover:opacity-100 transition-opacity duration-fast">
            <CopyInline text={command} />
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {command && (
        <div className="relative group/cmd">
          <pre className="p-3 rounded-lg text-xs overflow-x-auto font-mono bg-[#171717] text-success border border-[#333]">
            <span className="text-[#555]">$ </span>{command}
          </pre>
          <div className="absolute top-2 right-2 opacity-0 group-hover/cmd:opacity-100 transition-opacity duration-fast">
            <CopyInline text={command} />
          </div>
        </div>
      )}
      {step.result && (
        <div className="relative">
          <pre className="p-3 rounded-lg text-xs overflow-x-auto max-h-[200px] overflow-y-auto font-mono bg-[#171717] border border-[#333] text-[#a3a3a3]">
            {displayOutput}
          </pre>
          {needsOutputExpansion && !outputExpanded && (
            <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-[#171717] to-transparent pointer-events-none" />
          )}
          {needsOutputExpansion && (
            <div className="mt-1 text-center">
              <button
                onClick={() => setOutputExpanded(!outputExpanded)}
                className="text-xs text-muted-foreground hover:text-foreground-secondary hover:underline"
              >
                {outputExpanded ? "收起" : `展开全部 (${outputLines.length} 行)`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
