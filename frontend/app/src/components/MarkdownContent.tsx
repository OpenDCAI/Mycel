import { Streamdown } from "streamdown";

interface MarkdownContentProps {
  content: string;
}

export default function MarkdownContent({ content }: MarkdownContentProps) {
  if (!content) return null;
  return (
    <div className="markdown-content text-[13px] leading-[1.55] text-[#404040]">
      <Streamdown>{content}</Streamdown>
    </div>
  );
}
