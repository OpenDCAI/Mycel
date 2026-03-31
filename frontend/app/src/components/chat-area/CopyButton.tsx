import { Check, Copy } from "lucide-react";
import { useCallback, useState } from "react";
import { FEEDBACK_NORMAL } from "@/styles/ux-timing";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), FEEDBACK_NORMAL);
    });
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 text-2xs text-muted-foreground/70 hover:text-foreground-secondary transition-colors duration-fast px-1.5 py-0.5 rounded hover:bg-muted"
      title="复制"
    >
      {copied ? (
        <>
          <Check className="w-3 h-3" />
          <span>已复制</span>
        </>
      ) : (
        <>
          <Copy className="w-3 h-3" />
          <span>复制</span>
        </>
      )}
    </button>
  );
}
