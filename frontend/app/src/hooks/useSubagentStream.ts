import { useEffect, useRef, useState } from "react";
import { streamEvents } from "../api/streaming";
import type { StreamEvent } from "../api/types";
import type { FlowItem } from "../components/computer-panel/utils";

/**
 * Subscribe to a subagent's dedicated SSE stream and build FlowItem[] incrementally.
 * Only active when `isRunning=true`; aborts on cleanup or when thread changes.
 */
export function useSubagentStream(
  threadId: string | undefined,
  isRunning: boolean,
): FlowItem[] {
  const [flowItems, setFlowItems] = useState<FlowItem[]>([]);
  const toolCallsRef = useRef<
    Map<string, { id: string; name: string; args: unknown; status: "calling" | "done"; result?: string; timestamp: number }>
  >(new Map());
  const textRef = useRef<string>("");

  // Reset live state when thread changes
  useEffect(() => {
    setFlowItems([]);
    toolCallsRef.current = new Map();
    textRef.current = "";
  }, [threadId]);

  useEffect(() => {
    if (!threadId || !isRunning) return;

    // Fresh state for this run
    toolCallsRef.current = new Map();
    textRef.current = "";
    setFlowItems([]);

    const controller = new AbortController();

    function buildItems(): FlowItem[] {
      const items: FlowItem[] = [];
      for (const tc of toolCallsRef.current.values()) {
        items.push({
          type: "tool",
          step: {
            id: tc.id,
            name: tc.name,
            args: tc.args,
            status: tc.status,
            result: tc.result,
            timestamp: tc.timestamp,
          },
          turnId: "live",
        });
      }
      if (textRef.current.trim()) {
        items.push({ type: "text", content: textRef.current, turnId: "live" });
      }
      return items;
    }

    void streamEvents(
      threadId,
      (event: StreamEvent) => {
        if (event.type === "subagent_task_text") {
          const data = event.data as { content?: string } | undefined;
          if (data?.content) {
            textRef.current += data.content;
            setFlowItems(buildItems());
          }
        } else if (event.type === "subagent_task_tool_call") {
          const data = event.data as { id?: string; name?: string; args?: unknown } | undefined;
          if (data?.id) {
            toolCallsRef.current.set(data.id, {
              id: data.id,
              name: data.name ?? "unknown",
              args: data.args ?? {},
              status: "calling",
              timestamp: Date.now(),
            });
            setFlowItems(buildItems());
          }
        } else if (event.type === "subagent_task_tool_result") {
          const data = event.data as { tool_call_id?: string; content?: string } | undefined;
          if (data?.tool_call_id) {
            const tc = toolCallsRef.current.get(data.tool_call_id);
            if (tc) {
              tc.status = "done";
              tc.result = data.content ?? "";
              setFlowItems(buildItems());
            }
          }
        }
      },
      controller.signal,
    );

    return () => controller.abort();
  }, [threadId, isRunning]);

  return flowItems;
}
