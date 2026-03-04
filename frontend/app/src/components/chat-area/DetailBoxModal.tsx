import { memo } from "react";
import type { TurnSegment, ToolSegment } from "../../api";
import MarkdownContent from "../MarkdownContent";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { DEFAULT_BADGE, TOOL_BADGE_STYLES } from "./constants";
import { getStepSummary } from "./utils";
import { CheckCircle2, Loader2, XCircle, MessageSquare } from "lucide-react";

interface DetailBoxModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  segments: TurnSegment[];
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "calling":
      return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin flex-shrink-0" />;
    case "done":
      return <CheckCircle2 className="w-3.5 h-3.5 text-green-600 flex-shrink-0" />;
    case "error":
      return <XCircle className="w-3.5 h-3.5 text-red-500 flex-shrink-0" />;
    case "cancelled":
      return <XCircle className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />;
    default:
      return <CheckCircle2 className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />;
  }
}

function ToolEntry({ seg }: { seg: ToolSegment }) {
  const { step } = seg;
  const badge = TOOL_BADGE_STYLES[step.name] ?? { ...DEFAULT_BADGE, label: step.name };
  const hasSubagent = !!step.subagent_stream;

  return (
    <div className="border-l-2 border-gray-200 pl-3 py-1.5">
      <div className="flex items-center gap-1.5">
        <StatusIcon status={step.status} />
        <span className={`inline-flex items-center px-1.5 py-0 rounded text-[10px] font-medium ${badge.bg} ${badge.text}`}>
          {badge.label || step.name}
        </span>
        <span className="text-[12px] text-gray-600 font-mono truncate">
          {getStepSummary(step)}
        </span>
      </div>
      {step.result && (
        <div className="mt-1 text-[11px] text-gray-500 font-mono pl-5 max-h-20 overflow-y-auto whitespace-pre-wrap">
          {step.result.length > 500 ? step.result.slice(0, 500) + "..." : step.result}
        </div>
      )}
      {hasSubagent && step.subagent_stream && (
        <div className="mt-1 pl-5 text-[11px] text-blue-600">
          子 Agent: {step.subagent_stream.description || step.subagent_stream.task_id}
          {step.subagent_stream.status === "completed" && " ✓"}
          {step.subagent_stream.status === "running" && " (运行中...)"}
          {step.subagent_stream.status === "error" && ` ✗ ${step.subagent_stream.error}`}
        </div>
      )}
    </div>
  );
}

function TextEntry({ content }: { content: string }) {
  return (
    <div className="border-l-2 border-blue-200 pl-3 py-1.5">
      <div className="flex items-center gap-1.5 mb-1">
        <MessageSquare className="w-3.5 h-3.5 text-blue-400 flex-shrink-0" />
        <span className="text-[10px] text-blue-400 font-medium">AI Text</span>
      </div>
      <div className="text-[12px] text-gray-700">
        <MarkdownContent content={content} />
      </div>
    </div>
  );
}

function NoticeEntry({ content }: { content: string }) {
  return (
    <div className="border-l-2 border-amber-200 pl-3 py-1.5">
      <div className="text-[11px] text-amber-600 whitespace-pre-wrap">
        {content}
      </div>
    </div>
  );
}

export const DetailBoxModal = memo(function DetailBoxModal({
  open,
  onOpenChange,
  segments,
}: DetailBoxModalProps) {
  const toolCount = segments.filter((s) => s.type === "tool").length;
  const textCount = segments.filter((s) => s.type === "text").length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-sm font-medium">
            Turn 详情 — {toolCount} 工具调用{textCount > 1 ? `, ${textCount} 段文本` : ""}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-2 mt-2">
          {segments.map((seg, i) => {
            if (seg.type === "tool") {
              return <ToolEntry key={seg.step.id} seg={seg as ToolSegment} />;
            }
            if (seg.type === "text" && seg.content.trim()) {
              return <TextEntry key={`text-${i}`} content={seg.content} />;
            }
            if (seg.type === "notice") {
              return <NoticeEntry key={`notice-${i}`} content={seg.content} />;
            }
            return null;
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
});
