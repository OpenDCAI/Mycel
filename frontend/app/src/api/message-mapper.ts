import type { AssistantTurn, BackendMessage, ChatEntry, DisplayMode, NoticeMessage, NotificationType, ToolSegment, TurnSegment, WaterlineEntry } from "./types";

function extractTextContent(raw: unknown): string {
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    return raw
      .map((block) => {
        if (typeof block === "string") return block;
        if (block && typeof block === "object" && (block as { type?: string }).type === "text") {
          return (block as { text?: string }).text ?? "";
        }
        return "";
      })
      .join("");
  }
  return String(raw ?? "");
}

/** Strip <system-reminder>...</system-reminder> blocks from text content. */
function stripSystemReminders(text: string): string {
  return text.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, "").trim();
}


function buildToolSegments(toolCalls: unknown[], msgIndex: number, now: number): TurnSegment[] {
  return toolCalls.map((raw, j) => {
    const call = raw as { id?: string; name?: string; args?: unknown };
    return {
      type: "tool" as const,
      step: {
        id: call.id ?? `hist-tc-${msgIndex}-${j}`,
        name: call.name ?? "unknown",
        args: call.args ?? {},
        status: "calling" as const,
        timestamp: now,
      },
    };
  });
}

function createTurn(msgId: string, segments: TurnSegment[], now: number): AssistantTurn {
  return { id: msgId, messageIds: [msgId], role: "assistant", segments, timestamp: now };
}

function appendToTurn(turn: AssistantTurn, msgId: string, segments: TurnSegment[]): void {
  turn.segments.push(...segments);
  turn.messageIds?.push(msgId);
}

interface MapState {
  entries: ChatEntry[];
  currentTurn: AssistantTurn | null;
  currentRunId: string | null;
  now: number;
  // @@@display-carry — carried from HumanMessage to subsequent AI/Tool messages
  _displayMode: DisplayMode | undefined;
  _senderName: string | undefined;
}

function handleHuman(msg: BackendMessage, i: number, state: MapState): void {
  const display = (msg as any).display as { mode?: string; run_source?: string; sender_name?: string } | undefined;
  const mode = display?.mode;

  // @@@waterline — owner steers into external run
  if (mode === "waterline") {
    state.currentTurn = null;
    state.currentRunId = null;
    state._displayMode = "expanded";
    state._senderName = undefined;
    const entry: WaterlineEntry = {
      id: msg.id ?? `waterline-${i}`,
      role: "waterline",
      content: extractTextContent(msg.content),
      timestamp: state.now,
    };
    state.entries.push(entry);
    return;
  }

  // @@@collapsed-human — external message, don't show as UserBubble
  if (mode === "collapsed") {
    state.currentTurn = null;
    state.currentRunId = null;
    state._displayMode = "collapsed";
    state._senderName = display?.sender_name;
    return;
  }

  // System-injected messages (steer reminders, task notifications) → notice
  if (msg.metadata?.source === "system") {
    const content = extractTextContent(msg.content);
    const msgRunId = (msg.metadata?.run_id as string) || null;
    const ntype = msg.metadata?.notification_type as NotificationType | undefined;

    if (state.currentTurn && msgRunId && msgRunId === state.currentRunId) {
      state.currentTurn.segments.push({ type: "notice", content, notification_type: ntype });
      return;
    }
    if (state.currentTurn && !msgRunId) {
      state.currentTurn.segments.push({ type: "notice", content, notification_type: ntype });
      return;
    }
    state.currentTurn = null;
    state.currentRunId = null;
    const notice: NoticeMessage = {
      id: msg.id ?? `hist-notice-${i}`,
      role: "notice",
      content,
      notification_type: ntype,
      timestamp: state.now,
    };
    state.entries.push(notice);
    return;
  }

  // Normal user message (expanded) → breaks current turn
  state.currentTurn = null;
  state.currentRunId = null;
  state._displayMode = "expanded";
  state._senderName = undefined;
  state.entries.push({
    id: msg.id ?? `hist-user-${i}`,
    role: "user",
    content: extractTextContent(msg.content),
    timestamp: state.now,
  });
}

function handleAI(msg: BackendMessage, i: number, state: MapState): void {
  const display = (msg as any).display as { mode?: string; sender_name?: string } | undefined;
  const textContent = stripSystemReminders(extractTextContent(msg.content));
  const toolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];
  const msgId = msg.id ?? `hist-turn-${i}`;
  const msgRunId = (msg.metadata?.run_id as string) || null;

  const segments: TurnSegment[] = [];
  if (textContent) segments.push({ type: "text", content: textContent });
  if (toolCalls.length > 0) segments.push(...buildToolSegments(toolCalls, i, state.now));

  // Group by run_id: same run_id = same Turn
  if (state.currentTurn && msgRunId && msgRunId === state.currentRunId) {
    appendToTurn(state.currentTurn, msgId, segments);
    // punch_through AIMessage upgrades the turn's displayMode if it was collapsed
    if (display?.mode === "punch_through" && state.currentTurn.displayMode === "collapsed") {
      state.currentTurn.displayMode = "collapsed"; // keep collapsed, punch_through segments handled in rendering
    }
  } else if (state.currentTurn && !msgRunId && !state.currentRunId) {
    appendToTurn(state.currentTurn, msgId, segments);
  } else {
    // New run_id or first message → new Turn
    state.currentTurn = createTurn(msgId, segments, state.now);
    state.currentRunId = msgRunId;
    // @@@display-mode-carry — set displayMode from display annotation or carried state
    state.currentTurn.displayMode = (display?.mode ?? state._displayMode) as DisplayMode | undefined;
    state.currentTurn.senderName = display?.sender_name ?? state._senderName;
    state.entries.push(state.currentTurn);
  }
}

function handleTool(msg: BackendMessage, _i: number, state: MapState): void {
  if (!state.currentTurn) return;
  const seg = state.currentTurn.segments.find(
    (s): s is ToolSegment => s.type === "tool" && s.step.id === msg.tool_call_id,
  );
  if (seg) {
    const contentStr = extractTextContent(msg.content);
    seg.step.result = contentStr;
    seg.step.status = "done";

    // Restore subagent_stream from persisted metadata (history replay path)
    let taskId = msg.metadata?.task_id as string | undefined;
    let threadId = (msg.metadata?.subagent_thread_id as string | undefined)
      || (taskId ? `subagent-${taskId}` : undefined);

    // For Agent tool calls: also try parsing JSON content for task_id/thread_id
    // (background agents return JSON with task_id; metadata may be empty)
    if (!taskId && seg.step.name === "Agent") {
      try {
        const parsed = JSON.parse(contentStr) as Record<string, unknown>;
        if (parsed?.task_id) {
          taskId = parsed.task_id as string;
          threadId = (parsed.thread_id as string | undefined) || `subagent-${taskId}`;
        }
      } catch { /* not JSON, foreground agent text result */ }
    }

    if (threadId && !seg.step.subagent_stream) {
      seg.step.subagent_stream = {
        task_id: taskId || "",
        thread_id: threadId,
        description: (msg.metadata?.description as string) || undefined,
        text: "",
        tool_calls: [],
        status: "completed",
      };
    }
  }
}

const MSG_HANDLERS: Record<string, (msg: BackendMessage, i: number, state: MapState) => void> = {
  HumanMessage: handleHuman,
  AIMessage: handleAI,
  ToolMessage: handleTool,
};

export function mapBackendEntries(payload: unknown): ChatEntry[] {
  if (!Array.isArray(payload)) return [];
  const state: MapState = { entries: [], currentTurn: null, currentRunId: null, now: Date.now(), _displayMode: undefined, _senderName: undefined };

  for (let i = 0; i < payload.length; i += 1) {
    const msg = payload[i] as BackendMessage | undefined;
    if (!msg || typeof msg !== "object") continue;
    MSG_HANDLERS[msg.type]?.(msg, i, state);
  }

  return state.entries;
}
