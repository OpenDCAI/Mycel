import { memo, useState } from "react";
import { isToolSegment, type TurnSegment, type ToolSegment } from "../../api";
import MarkdownContent from "../MarkdownContent";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { DEFAULT_BADGE, TOOL_BADGE_STYLES } from "./constants";
import { getStepSummary, getStepResultSummary } from "./utils";
import { CheckCircle2, Loader2, XCircle, MessageSquare, ChevronRight, ChevronDown } from "lucide-react";
import { ToolRenderer } from "../tool-renderers";

interface DetailBoxModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  segments: TurnSegment[];
}

function StatusIcon({ status }: { status: string }) {
  switch (status) {
    case "calling":
      return <Loader2 className="w-3.5 h-3.5 text-info animate-spin flex-shrink-0" />;
    case "done":
      return <CheckCircle2 className="w-3.5 h-3.5 text-success flex-shrink-0" />;
    case "error":
      return <XCircle className="w-3.5 h-3.5 text-destructive flex-shrink-0" />;
    case "cancelled":
      return <XCircle className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />;
    default:
      return <CheckCircle2 className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />;
  }
}

function ToolEntry({ seg }: { seg: ToolSegment }) {
  const { step } = seg;
  const [expanded, setExpanded] = useState(false);
  const badge = TOOL_BADGE_STYLES[step.name] ?? { ...DEFAULT_BADGE, label: step.name };
  const hasSubagent = !!step.subagent_stream;
  const resultSummary = getStepResultSummary(step);

  return (
    <div className="border-l-2 border-border pl-3 py-1.5">
      <div
        className="flex items-center gap-1.5 cursor-pointer hover:bg-muted -ml-3 pl-3 -mr-3 pr-3 py-1 rounded transition-colors duration-fast"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground flex-shrink-0" />
        )}
        <StatusIcon status={step.status} />
        <span className={`inline-flex items-center px-1.5 py-0 rounded text-2xs font-medium ${badge.bg} ${badge.text}`}>
          {badge.label || step.name}
        </span>
        <span className="text-xs text-gray-600 font-mono truncate">
          {resultSummary ?? getStepSummary(step)}
        </span>
      </div>

      {expanded && (
        <div className="mt-2 pl-5 min-w-0 overflow-hidden">
          <ToolRenderer step={step} expanded={true} />
        </div>
      )}

      {hasSubagent && step.subagent_stream && (
        <div className="mt-1 pl-5 text-xs text-info">
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
    <div className="border-l-2 border-info/20 pl-3 py-1.5">
      <div className="flex items-center gap-1.5 mb-1">
        <MessageSquare className="w-3.5 h-3.5 text-info flex-shrink-0" />
        <span className="text-2xs text-info font-medium">AI Text</span>
      </div>
      <div className="text-xs text-gray-700 min-w-0 overflow-hidden">
        <MarkdownContent content={content} />
      </div>
    </div>
  );
}

function NoticeEntry({ content }: { content: string }) {
  return (
    <div className="border-l-2 border-amber-200 pl-3 py-1.5">
      <div className="text-xs text-amber-600 whitespace-pre-wrap">
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
          <DialogDescription className="sr-only">
            查看本轮对话的完整执行细节，包括工具调用和文本输出
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 mt-2">
          {segments.filter((s) => s.type !== "retry").map((seg, i) => {
            if (isToolSegment(seg)) {
              return <ToolEntry key={seg.step.id} seg={seg} />;
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
