export const STREAM_EVENT_TYPES = [
  // Content (5)
  "text", "tool_call", "tool_result", "error", "cancelled",
  // Lifecycle (3) — background task
  "task_start", "task_done", "task_error",
  // Control (3) — run boundaries + runtime status
  "status", "run_start", "run_done",
  // Retry notification
  "retry",
  // Notice — system notification emitted before run_start
  "notice",
  // @@@display-builder — backend-owned display model
  "user_message", "display_delta",
] as const;

export type StreamEventType = (typeof STREAM_EVENT_TYPES)[number];

export interface StreamEvent {
  type: StreamEventType;
  data?: unknown;
}

export interface ThreadSummary {
  thread_id: string;
  sandbox?: string;
  sandbox_info?: SandboxInfo;
  preview?: string;
  updated_at?: string;
  running?: boolean;
  member_id?: string;
  member_name?: string;
  /** Canonical thread/entity display name. Main: {member}. Child: {member} · 分身N */
  entity_name?: string;
  branch_index?: number;
  sidebar_label?: string | null;
  avatar_url?: string;
  is_main?: boolean;
}

export interface ThreadDetail {
  thread_id: string;
  entries: ChatEntry[];
  display_seq: number;
  sandbox: SandboxInfo | null;
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

export type NotificationType = "steer" | "command" | "agent" | "chat";

export interface NoticeSegment {
  type: "notice";
  content: string;
  notification_type?: NotificationType;
}

export interface RetrySegment {
  type: "retry";
  attempt: number;
  maxAttempts: number;
  waitSeconds: number;
}

export type TurnSegment = TextSegment | ToolSegment | NoticeSegment | RetrySegment;

export interface AssistantTurn {
  id: string;
  messageIds?: string[];
  role: "assistant";
  segments: TurnSegment[];
  timestamp: number;
  endTimestamp?: number;
  streaming?: boolean;
  /** Backend-computed: is this turn visible to thread owner? */
  showing?: boolean;
  senderName?: string;
}

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
  timestamp: number;
  /** Backend-computed: is this message visible to thread owner? */
  showing?: boolean;
  senderName?: string;
  senderAvatarUrl?: string;
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
  run_start_seq?: number;
}

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

// --- Entity Chat types ---

export interface ChatEntity {
  id: string;
  name: string;
  type: string;
  avatar_url?: string;
  owner_name?: string | null;
  member_name?: string | null;
  thread_id?: string | null;
  is_main?: boolean | null;
  branch_index?: number | null;
}

export interface ChatSummary {
  id: string;
  title: string | null;
  entities: ChatEntity[];
  last_message?: { content: string; sender_name: string; created_at: number };
  unread_count: number;
  has_mention: boolean;
}

export interface ChatDetail {
  id: string;
  title: string | null;
  status: string;
  created_at: number;
  entities: ChatEntity[];
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  sender_entity_id: string;
  sender_name: string;
  content: string;
  mentioned_entity_ids: string[];
  created_at: number;
}
