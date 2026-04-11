import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { isAssistantTurn, type ToolStep } from "../../api";
import { useThreadData } from "../../hooks/use-thread-data";
import { useDisplayDeltas } from "../../hooks/use-display-deltas";
import { useThreadStream } from "../../hooks/use-thread-stream";
import { resolveAgentVisualStatus, type AgentVisualStatus } from "./agent-visual-status";
import { parseAgentArgs } from "./utils";
import type { FlowItem } from "./utils";
import { FlowList } from "./flow-items";


type SubagentStream = NonNullable<ToolStep["subagent_stream"]>;


interface AgentsViewProps {
  steps: ToolStep[];
}

export function AgentsView({ steps }: AgentsViewProps) {
  const [leftWidth, setLeftWidth] = useState(280);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [agentFocusedStepId, setAgentFocusedStepId] = useState<string | null>(null);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);

  const effectiveSelectedAgentId = useMemo(() => {
    if (steps.length === 0) return null;
    if (selectedAgentId && steps.some((step) => step.id === selectedAgentId)) return selectedAgentId;
    return (
      [...steps].reverse().find((step) => {
        const status = step.subagent_stream?.status;
        return status === "running" || step.status === "calling";
      })?.id ?? steps[steps.length - 1].id
    );
  }, [steps, selectedAgentId]);

  const focused = steps.find((s) => s.id === effectiveSelectedAgentId) ?? null;
  const stream = focused?.subagent_stream;
  const threadId = stream?.thread_id || undefined;
  const { entries, loading, refreshThread, setEntries, displaySeq } = useThreadData(threadId);
  const refreshThreads = useCallback(async () => {}, []);
  // @@@child-thread-live-bridge - the Agent pane must subscribe to the child
  // thread's own SSE stream. Polling child detail alone misses the running
  // window and makes the pane look empty until a later refresh.
  const childStream = useThreadStream(threadId ?? "", {
    loading: loading || !threadId,
    refreshThreads,
  });
  const childDisplay = useDisplayDeltas({
    threadId: threadId ?? "",
    onUpdate: setEntries,
    displaySeq,
    stream: childStream,
  });
  const focusedStatus =
    focused
      ? resolveAgentVisualStatus(focused, {
        childDisplayRunning: childDisplay.isRunning,
        childRuntimeState: childStream.runtimeStatus?.state?.state ?? null,
      })
      : null;
  const isRunning = focusedStatus === "running";

  // Poll every second while sub-agent is running
  useEffect(() => {
    if (!isRunning || !threadId) return;
    const id = setInterval(() => { void refreshThread(); }, 1000);
    return () => clearInterval(id);
  }, [isRunning, threadId, refreshThread]);

  const flowItems = useMemo<FlowItem[]>(() => {
    const items: FlowItem[] = [];
    for (const entry of entries) {
      if (!isAssistantTurn(entry)) continue;
      for (const seg of entry.segments) {
        if (seg.type === "tool") {
          items.push({ type: "tool", step: seg.step, turnId: entry.id });
        } else if (seg.type === "text" && seg.content.trim()) {
          items.push({ type: "text", content: seg.content, turnId: entry.id });
        }
      }
    }

    if (!stream) return items;

    // 2) Append live tool calls from SSE that polling hasn't caught up to
    const knownToolIds = new Set(items.filter((i) => i.type === "tool").map((i) => i.step!.id));
    for (const tc of stream.tool_calls) {
      if (knownToolIds.has(tc.id)) continue;
      items.push({
        type: "tool",
        step: {
          id: tc.id, name: tc.name, args: tc.args,
          status: tc.status === "done" ? "done" : "calling",
          result: tc.result,
          timestamp: focused?.timestamp ?? 0,
        },
        turnId: "live",
      });
    }

    // 3) If stream has text but entries are empty (first poll pending), show it
    if (stream.text.trim() && !items.some((i) => i.type === "text")) {
      items.push({ type: "text", content: stream.text, turnId: "live" });
    }

    return items;
  }, [entries, stream, focused?.timestamp]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = leftWidth;
  }, [leftWidth]);

  useEffect(() => {
    if (!isDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      const delta = e.clientX - dragStartX.current;
      const newWidth = Math.max(200, Math.min(600, dragStartWidth.current + delta));
      setLeftWidth(newWidth);
    };
    const handleMouseUp = () => setIsDragging(false);
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);

  if (steps.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-muted-foreground/70">
        暂无助手任务
      </div>
    );
  }

  return (
    <div className="h-full flex bg-background">
      {/* Left sidebar - agent list */}
      <div className="flex-shrink-0 border-r border-border flex flex-col" style={{ width: `${leftWidth}px` }}>
        <div className="px-3 py-2 border-b border-border">
          <div className="text-xs text-muted-foreground font-medium">助手任务</div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {steps.map((step) => (
            <AgentListItem
              key={step.id}
              step={step}
              visualStatus={step.id === effectiveSelectedAgentId ? focusedStatus ?? null : null}
              isSelected={step.id === effectiveSelectedAgentId}
              onClick={() => setSelectedAgentId(step.id)}
            />
          ))}
        </div>
      </div>

      {/* Resizable divider */}
      <div
        className={`w-1 flex-shrink-0 cursor-col-resize hover:bg-info transition-colors duration-fast ${
          isDragging ? "bg-info" : "bg-transparent"
        }`}
        onMouseDown={handleMouseDown}
      />

      {/* Right detail */}
      <div className="flex-1 flex flex-col min-w-0">
        {!focused ? (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground/70">
            选择一个助手查看详情
          </div>
        ) : (
          <>
            <AgentDetailHeader focused={focused} stream={stream} visualStatus={focusedStatus ?? "completed"} />
            <AgentPromptSection args={focused.args} />
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <Loader2 className="w-5 h-5 text-muted-foreground/70 animate-spin" />
              </div>
            ) : (
              <FlowList
                flowItems={flowItems}
                focusedStepId={agentFocusedStepId}
                onFocusStep={setAgentFocusedStepId}
                autoScroll={!!isRunning}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* -- Agent list item -- */

function AgentListItem({
  step,
  visualStatus,
  isSelected,
  onClick,
}: {
  step: ToolStep;
  visualStatus: AgentVisualStatus | null;
  isSelected: boolean;
  onClick: () => void;
}) {
  const args = parseAgentArgs(step.args);
  const ss = step.subagent_stream;
  const displayName = ss?.description || args.description || args.prompt?.slice(0, 40) || "子任务";
  const prompt = args.prompt || "";
  const status = resolveAgentVisualStatus(step, { statusOverride: visualStatus });
  const isRunning = status === "running";
  const isError = status === "error";
  const isDone = status === "completed";
  const statusDot = isRunning ? "bg-success animate-pulse" : isError ? "bg-destructive" : isDone ? "bg-success" : "bg-warning animate-pulse";

  return (
    <button
      className={`w-full text-left px-3 py-2.5 border-b border-muted transition-colors duration-fast ${
        isSelected ? "bg-info/10" : "hover:bg-muted"
      }`}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot}`} />
        <div className="text-xs font-semibold text-foreground truncate">{displayName}</div>
      </div>
      {prompt && (
        <div className="text-2xs text-muted-foreground truncate mt-0.5 pl-4">{prompt}</div>
      )}
    </button>
  );
}

/* -- Agent detail header -- */

function getStatusLabel(status: AgentVisualStatus): string {
  if (status === "running") return "运行中";
  if (status === "error") return "出错";
  return "已完成";
}

function getStatusDotClass(status: AgentVisualStatus): string {
  if (status === "running") return "bg-success animate-pulse";
  if (status === "error") return "bg-destructive";
  return "bg-success";
}

function AgentDetailHeader({
  focused,
  stream,
  visualStatus,
}: {
  focused: ToolStep;
  stream: SubagentStream | undefined;
  visualStatus: AgentVisualStatus;
}) {
  const args = parseAgentArgs(focused.args);
  const displayName = stream?.description || args.description || args.prompt?.slice(0, 40) || "子任务";
  const agentType = args.subagent_type;
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-muted flex-shrink-0">
      {agentType && (
        <span className="text-2xs font-mono bg-border text-foreground-secondary px-1.5 py-0.5 rounded flex-shrink-0">{agentType}</span>
      )}
      <div className="text-sm font-medium text-foreground truncate flex-1">{displayName}</div>
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${getStatusDotClass(visualStatus)}`} />
      <span className="text-2xs text-muted-foreground/70 flex-shrink-0">{getStatusLabel(visualStatus)}</span>
    </div>
  );
}

/* -- Sub-agent prompt display -- */

function AgentPromptSection({ args }: { args: unknown }) {
  const { prompt } = parseAgentArgs(args);
  if (!prompt) return null;

  return (
    <div className="px-4 py-2.5 border-b border-border bg-muted flex-shrink-0">
      <div className="text-2xs text-muted-foreground/70 font-medium mb-1">PROMPT</div>
      <div className="text-xs text-foreground-secondary leading-relaxed whitespace-pre-wrap break-words max-h-[120px] overflow-y-auto">
        {prompt}
      </div>
    </div>
  );
}
