import { useMemo } from "react";
import { Streamdown } from "streamdown";

interface MarkdownContentProps {
  content: string;
}

/** Strip <system-reminder>...</system-reminder> blocks that LLM may echo. */
function stripSystemReminders(text: string): string {
  return text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, "").trim();
}

export default function MarkdownContent({ content }: MarkdownContentProps) {
  const cleaned = useMemo(() => stripSystemReminders(content), [content]);
  if (!cleaned) return null;
  return (
    <div className="markdown-content text-sm leading-[1.2] text-foreground-secondary break-all overflow-hidden">
      <Streamdown>{cleaned}</Streamdown>
    </div>
  );
}
