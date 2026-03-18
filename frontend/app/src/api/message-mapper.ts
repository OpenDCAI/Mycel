import type { AssistantTurn, BackendMessage, ChatEntry, NoticeMessage, NotificationType, ToolSegment, TurnSegment } from "./types";

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

/** Extract the actual chat message content from <chat-message> tags inside system-reminder. */
function extractChatMessage(text: string): string | null {
  const m = text.match(/<chat-message[^>]*>([\s\S]*?)<\/chat-message>/);
  return m ? m[1].trim() : null;
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

// @@@display — read backend-computed display metadata
interface DisplayAnnotation {
  showing?: boolean;
  is_tell_owner?: boolean;
  sender_name?: string;
}

function getDisplay(msg: BackendMessage): DisplayAnnotation {
  return (msg as any).display ?? {};
}

interface MapState {
  entries: ChatEntry[];
  currentTurn: AssistantTurn | null;
  currentRunId: string | null;
  showHidden: boolean;
  now: number;
}

function handleHuman(msg: BackendMessage, i: number, state: MapState): void {
  const display = getDisplay(msg);
  const meta = msg.metadata || {};

  // Hidden HumanMessage: each run = independent turn, just break the current turn.
  // When showHidden, also emit a dimmed user entry.
  if (display.showing === false) {
    state.currentTurn = null;
    state.currentRunId = null;
    if (state.showHidden) {
      const rawContent = extractTextContent(msg.content);
      const chatMsg = extractChatMessage(rawContent);
      state.entries.push({
        id: msg.id ?? `hist-user-${i}`,
        role: "user",
        content: chatMsg || stripSystemReminders(rawContent) || "(external message)",
        timestamp: state.now,
        showing: false,
        senderName: (meta.sender_name as string) || undefined,
        senderAvatarUrl: (meta.sender_avatar_url as string) || undefined,
      });
    }
    return;
  }

  // System-injected messages → notice
  if (meta.source === "system") {
    const content = extractTextContent(msg.content);
    const msgRunId = (meta.run_id as string) || null;
    const ntype = meta.notification_type as NotificationType | undefined;

    // Fold into current turn if same run or no run tracking
    if (state.currentTurn && (!msgRunId || msgRunId === state.currentRunId)) {
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

  // Normal visible user message
  state.currentTurn = null;
  state.currentRunId = null;
  state.entries.push({
    id: msg.id ?? `hist-user-${i}`,
    role: "user",
    content: extractTextContent(msg.content),
    timestamp: state.now,
  });
}

function handleAI(msg: BackendMessage, i: number, state: MapState): void {
  const display = getDisplay(msg);
  const textContent = stripSystemReminders(extractTextContent(msg.content));
  const toolCalls = Array.isArray(msg.tool_calls) ? msg.tool_calls : [];
  const msgId = msg.id ?? `hist-turn-${i}`;
  const msgRunId = (msg.metadata?.run_id as string) || null;

  // Hidden: skip (unless tell_owner or showHidden)
  if (display.showing === false && !display.is_tell_owner && !state.showHidden) {
    return;
  }

  // tell_owner from hidden run: extract tell_owner content only
  if (display.showing === false && display.is_tell_owner) {
    const tellMsgs: string[] = [];
    for (const tc of toolCalls) {
      const call = tc as { name?: string; args?: unknown };
      if (call.name === "tell_owner") {
        const args = call.args as { message?: string } | undefined;
        if (args?.message) tellMsgs.push(args.message);
      }
    }
    if (tellMsgs.length > 0) {
      const turn = createTurn(msgId, tellMsgs.map(t => ({ type: "text" as const, content: t })), state.now);
      turn.isTellOwner = true;
      turn.showing = true; // tell_owner content IS shown
      state.entries.push(turn);
    }
    return;
  }

  // showHidden dimmed turn — hidden AI rendered separately, not merged
  if (display.showing === false && state.showHidden) {
    const segments: TurnSegment[] = [];
    if (textContent) segments.push({ type: "text", content: textContent });
    if (toolCalls.length > 0) segments.push(...buildToolSegments(toolCalls, i, state.now));
    const turn = createTurn(msgId, segments, state.now);
    turn.showing = false;
    turn.senderName = display.sender_name;
    state.currentTurn = turn;
    state.currentRunId = msgRunId;
    state.entries.push(turn);
    return;
  }

  // Visible: normal turn building
  const segments: TurnSegment[] = [];
  if (textContent) segments.push({ type: "text", content: textContent });
  if (toolCalls.length > 0) segments.push(...buildToolSegments(toolCalls, i, state.now));

  // @@@turn-merge — merge within same run_id, or when both have no run tracking.
  if (state.currentTurn && msgRunId && msgRunId === state.currentRunId) {
    appendToTurn(state.currentTurn, msgId, segments);
  } else if (state.currentTurn && !msgRunId && !state.currentRunId) {
    appendToTurn(state.currentTurn, msgId, segments);
  } else {
    state.currentTurn = createTurn(msgId, segments, state.now);
    state.currentRunId = msgRunId;
    state.currentTurn.showing = true;
    state.entries.push(state.currentTurn);
  }
}

function handleTool(msg: BackendMessage, _i: number, state: MapState): void {
  const display = getDisplay(msg);

  // Hidden: skip (unless tell_owner result or showHidden)
  if (display.showing === false && !display.is_tell_owner && !state.showHidden) {
    return;
  }

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

export function mapBackendEntries(payload: unknown, showHidden = false): ChatEntry[] {
  if (!Array.isArray(payload)) return [];
  const state: MapState = { entries: [], currentTurn: null, currentRunId: null, showHidden, now: Date.now() };

  for (let i = 0; i < payload.length; i += 1) {
    const msg = payload[i] as BackendMessage | undefined;
    if (!msg || typeof msg !== "object") continue;
    MSG_HANDLERS[msg.type]?.(msg, i, state);
  }

  return state.entries;
}
