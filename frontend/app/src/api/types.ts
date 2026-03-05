export const STREAM_EVENT_TYPES = [
  // Content (5)
  "text", "tool_call", "tool_result", "error", "cancelled",
  // Lifecycle (3) — background task
  "task_start", "task_done", "task_error",
  // Control (3) — run boundaries + runtime status
  "status", "run_start", "run_done",
] as const;

export type StreamEventType = (typeof STREAM_EVENT_TYPES)[number];

export interface StreamEvent {
  type: StreamEventType;
  data?: unknown;
}

/** Common fields injected into all content/lifecycle events by the backend. */
export interface ContentEventData {
  parent_tool_call_id?: string;
  background?: boolean;
  seq: number;
  run_id: string;
  message_id?: string;
}

export interface TaskStartData extends ContentEventData {
  task_id: string;
  subagent_type: string;
  description: string;
}

export interface TaskDoneData extends ContentEventData {
  task_id: string;
  thread_id?: string;
  status: string;
}

export interface TaskErrorData extends ContentEventData {
  task_id: string;
  error: string;
}

export interface ThreadSummary {
  thread_id: string;
  sandbox?: string;
  messages?: BackendMessage[];
  sandbox_info?: SandboxInfo;
  preview?: string;
  updated_at?: string;
  running?: boolean;
  agent?: string | null;
}

export interface SandboxType {
  name: string;
  available: boolean;
  reason?: string;
}

export interface SandboxSession {
  session_id: string;
  thread_id: string;
  provider: string;
  status: string;
  created_at?: string;
  last_active?: string;
  lease_id?: string | null;
  instance_id?: string | null;
  chat_session_id?: string | null;
  source?: string;
}

export interface SandboxInfo {
  type: string;
  status: string | null;
  session_id: string | null;
  terminal_id?: string | null;
}

export interface BackendMessage {
  id?: string;
  type: string;
  content: unknown;
  tool_calls?: unknown[];
  tool_call_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ToolStep {
  id: string;
  name: string;
  args: unknown;
  result?: string;
  status: "calling" | "done" | "error" | "cancelled";
  timestamp: number;
  subagent_stream?: {
    task_id: string;
    thread_id: string;
    description?: string;
    text: string;
    tool_calls: Array<{ id: string; name: string; args: unknown; result?: string; status?: "calling" | "done" }>;
    status: "running" | "completed" | "error";
    error?: string;
  };
}

export interface TextSegment {
  type: "text";
  content: string;
}

export interface ToolSegment {
  type: "tool";
  step: ToolStep;
}

export type NotificationType = "steer" | "command" | "agent";

export interface NoticeSegment {
  type: "notice";
  content: string;
  notification_type?: NotificationType;
}

export type TurnSegment = TextSegment | ToolSegment | NoticeSegment;

export interface AssistantTurn {
  id: string;
  messageIds?: string[];
  role: "assistant";
  segments: TurnSegment[];
  timestamp: number;
  streaming?: boolean;
}

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
  timestamp: number;
}

export interface NoticeMessage {
  id: string;
  role: "notice";
  content: string;
  notification_type?: NotificationType;
  timestamp: number;
}

export type ChatEntry = UserMessage | AssistantTurn | NoticeMessage;

export interface StreamStatus {
  state: { state: string; flags: Record<string, boolean> };
  tokens: { total_tokens: number; input_tokens: number; output_tokens: number; cost: number };
  context: { message_count: number; estimated_tokens: number; usage_percent: number; near_limit: boolean };
  current_tool?: string;
  last_seq?: number;
}

export interface ChatSettings {
  turnGrouping: "merged" | "separate";
}

export const DEFAULT_CHAT_SETTINGS: ChatSettings = { turnGrouping: "merged" };

export interface SessionStatus {
  thread_id: string;
  session_id: string;
  terminal_id: string;
  status: string;
  started_at: string;
  last_active_at: string;
  expires_at: string;
}

export interface TerminalStatus {
  thread_id: string;
  terminal_id: string;
  lease_id: string;
  cwd: string;
  env_delta: Record<string, string>;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface LeaseStatus {
  thread_id: string;
  lease_id: string;
  provider_name: string;
  instance: {
    instance_id: string | null;
    state: string | null;
    started_at: string | null;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceEntry {
  name: string;
  is_dir: boolean;
  size: number;
  children_count?: number | null;
}

export interface WorkspaceListResult {
  thread_id: string;
  path: string;
  entries: WorkspaceEntry[];
}

export interface WorkspaceFileResult {
  thread_id: string;
  path: string;
  content: string;
  size: number;
}

export interface TaskAgentRequest {
  subagent_type: string;
  prompt: string;
  description?: string;
  model?: string;
  max_turns?: number;
}
