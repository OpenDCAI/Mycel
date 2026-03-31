import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import type { AssistantTurn, ToolStep } from "../../api";
import { useThreadData } from "../../hooks/use-thread-data";
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

  const focused = steps.find((s) => s.id === selectedAgentId) ?? null;
  const stream = focused?.subagent_stream;
  const threadId = stream?.thread_id || undefined;
  const isRunning = stream?.status === "running" || focused?.status === "calling";

  const { entries, loading, refreshThread } = useThreadData(threadId);

  // Poll every second while sub-agent is running
  useEffect(() => {
    if (!isRunning || !threadId) return;
    const id = setInterval(() => { void refreshThread(); }, 1000);
    return () => clearInterval(id);
  }, [isRunning, threadId, refreshThread]);

  const flowItems = useMemo<FlowItem[]>(() => {
    const items: FlowItem[] = [];
    for (const entry of entries) {
      if (entry.role !== "assistant") continue;
      for (const seg of (entry as AssistantTurn).segments) {
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
          timestamp: Date.now(),
        },
        turnId: "live",
      });
    }

    // 3) If stream has text but entries are empty (first poll pending), show it
    if (stream.text.trim() && !items.some((i) => i.type === "text")) {
      items.push({ type: "text", content: stream.text, turnId: "live" });
    }

    return items;
  }, [entries]);

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
      <div className="h-full flex items-center justify-center text-sm text-[#a3a3a3]">
        暂无助手任务
      </div>
    );
  }

  return (
    <div className="h-full flex bg-white">
      {/* Left sidebar - agent list */}
      <div className="flex-shrink-0 border-r border-[#e5e5e5] flex flex-col" style={{ width: `${leftWidth}px` }}>
        <div className="px-3 py-2 border-b border-[#e5e5e5]">
          <div className="text-xs text-[#737373] font-medium">助手任务</div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {steps.map((step) => (
            <AgentListItem
              key={step.id}
              step={step}
              isSelected={step.id === selectedAgentId}
              onClick={() => setSelectedAgentId(step.id)}
            />
          ))}
        </div>
      </div>

      {/* Resizable divider */}
      <div
        className={`w-1 flex-shrink-0 cursor-col-resize hover:bg-blue-400 transition-colors duration-fast ${
          isDragging ? "bg-blue-500" : "bg-transparent"
        }`}
        onMouseDown={handleMouseDown}
      />

      {/* Right detail */}
      <div className="flex-1 flex flex-col min-w-0">
        {!focused ? (
          <div className="h-full flex items-center justify-center text-sm text-[#a3a3a3]">
            选择一个助手查看详情
          </div>
        ) : (
          <>
            <AgentDetailHeader focused={focused} stream={stream} />
            <AgentPromptSection args={focused.args} />
            {loading ? (
              <div className="h-full flex items-center justify-center">
                <Loader2 className="w-5 h-5 text-[#a3a3a3] animate-spin" />
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

function AgentListItem({ step, isSelected, onClick }: { step: ToolStep; isSelected: boolean; onClick: () => void }) {
  const args = parseAgentArgs(step.args);
  const ss = step.subagent_stream;
  const displayName = ss?.description || args.description || args.prompt?.slice(0, 40) || "子任务";
  const prompt = args.prompt || "";
  const isRunning = ss?.status === "running" || (step.status === "calling" && ss?.status !== "completed");
  const isError = step.status === "error" || ss?.status === "error";
  const isDone = !isRunning && !isError && (step.status === "done" || ss?.status === "completed");
  const statusDot = isRunning ? "bg-green-400 animate-pulse" : isError ? "bg-red-400" : isDone ? "bg-green-500" : "bg-yellow-400 animate-pulse";

  return (
    <button
      className={`w-full text-left px-3 py-2.5 border-b border-[#f5f5f5] transition-colors duration-fast ${
        isSelected ? "bg-blue-50" : "hover:bg-[#f5f5f5]"
      }`}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot}`} />
        <div className="text-[11px] font-semibold text-[#171717] truncate">{displayName}</div>
      </div>
      {prompt && (
        <div className="text-[10px] text-[#737373] truncate mt-0.5 pl-4">{prompt}</div>
      )}
    </button>
  );
}

/* -- Agent detail header -- */

function getStatusLabel(focused: ToolStep, stream: SubagentStream | undefined): string {
  if (stream?.status === "running") return "运行中";
  if (stream?.status === "error") return "出错";
  if (focused.status === "calling") return "启动中";
  return "已完成";
}

function getStatusDotClass(focused: ToolStep, stream: SubagentStream | undefined): string {
  if (stream?.status === "running") return "bg-green-400 animate-pulse";
  if (stream?.status === "error") return "bg-red-400";
  if (focused.status === "calling") return "bg-yellow-400 animate-pulse";
  return "bg-green-500";
}

function AgentDetailHeader({ focused, stream }: { focused: ToolStep; stream: SubagentStream | undefined }) {
  const args = parseAgentArgs(focused.args);
  const displayName = stream?.description || args.description || args.prompt?.slice(0, 40) || "子任务";
  const agentType = args.subagent_type;
  return (
    <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#e5e5e5] bg-[#fafafa] flex-shrink-0">
      {agentType && (
        <span className="text-[10px] font-mono bg-[#e5e5e5] text-[#525252] px-1.5 py-0.5 rounded flex-shrink-0">{agentType}</span>
      )}
      <div className="text-sm font-medium text-[#171717] truncate flex-1">{displayName}</div>
      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${getStatusDotClass(focused, stream)}`} />
      <span className="text-[10px] text-[#a3a3a3] flex-shrink-0">{getStatusLabel(focused, stream)}</span>
    </div>
  );
}

/* -- Sub-agent prompt display -- */

function AgentPromptSection({ args }: { args: unknown }) {
  const { prompt } = parseAgentArgs(args);
  if (!prompt) return null;

  return (
    <div className="px-4 py-2.5 border-b border-[#e5e5e5] bg-[#f9fafb] flex-shrink-0">
      <div className="text-[10px] text-[#a3a3a3] font-medium mb-1">PROMPT</div>
      <div className="text-[12px] text-[#525252] leading-relaxed whitespace-pre-wrap break-words max-h-[120px] overflow-y-auto">
        {prompt}
      </div>
    </div>
  );
}

