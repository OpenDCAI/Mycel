import { useEffect, useRef, useState } from "react";
import { streamThreadEvents } from "../api/streaming";
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

    void streamThreadEvents(
      threadId,
      (event: StreamEvent) => {
        const data = event.data as Record<string, unknown> | undefined;
        const agentId = data?.agent_id as string | undefined;

        // Only process events from non-main agents
        if (!agentId || agentId === "main") return;

        if (event.type === "text") {
          if (data?.content) {
            textRef.current += data.content as string;
            setFlowItems(buildItems());
          }
        } else if (event.type === "tool_call") {
          if (data?.id) {
            toolCallsRef.current.set(data.id as string, {
              id: data.id as string,
              name: (data.name as string) ?? "unknown",
              args: data.args ?? {},
              status: "calling",
              timestamp: Date.now(),
            });
            setFlowItems(buildItems());
          }
        } else if (event.type === "tool_result") {
          const tcId = data?.tool_call_id as string | undefined;
          if (tcId) {
            const tc = toolCallsRef.current.get(tcId);
            if (tc) {
              tc.status = "done";
              tc.result = (data?.content as string) ?? "";
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
