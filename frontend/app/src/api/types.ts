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
  agent?: string;
  sandbox_info?: SandboxInfo;
  preview?: string;
  updated_at?: string;
  running?: boolean;
  /** Actor user backing this thread. */
  agent_user_id?: string;
  /** Thread-facing display label when `sidebar_label` is absent. */
  agent_name?: string;
  branch_index?: number;
  /** Canonical actor-facing label for sidebar/header surfaces. */
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

export interface PermissionRequest {
  request_id: string;
  thread_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  message?: string | null;
}

export interface AskUserQuestionOption {
  label: string;
  description: string;
  preview?: string | null;
}

export interface AskUserQuestionPrompt {
  header: string;
  question: string;
  options: AskUserQuestionOption[];
  multiSelect?: boolean;
}

export interface AskUserAnswer {
  header?: string;
  question?: string;
  selected_options: string[];
  free_text?: string | null;
}

export type PermissionRuleBehavior = "allow" | "deny" | "ask";

export interface ThreadPermissionRules {
  allow: string[];
  deny: string[];
  ask: string[];
}

export interface ThreadPermissions {
  thread_id: string;
  requests: PermissionRequest[];
  session_rules: ThreadPermissionRules;
  managed_only: boolean;
}

export interface SandboxType {
  name: string;
  provider?: string;
  available: boolean;
  reason?: string;
  capability?: {
    can_pause: boolean;
    can_resume: boolean;
    can_destroy: boolean;
    supports_webhook: boolean;
    supports_status_probe: boolean;
    eager_instance_binding: boolean;
    inspect_visible: boolean;
    runtime_kind: string;
    mount: {
      supports_mount: boolean;
      supports_copy: boolean;
      supports_read_only: boolean;
    };
  };
}

export interface RecipeFeatureOption {
  key: string;
  name: string;
  description: string;
  icon?: string;
}

export interface RecipeSnapshot {
  id: string;
  name: string;
  desc?: string;
  provider_name?: string;
  provider_type: string;
  features: Record<string, boolean>;
  configurable_features?: Record<string, boolean>;
  feature_options?: RecipeFeatureOption[];
}

export interface ThreadLaunchConfig {
  create_mode: "new" | "existing";
  provider_config: string;
  recipe_id?: string | null;
  recipe?: RecipeSnapshot | null;
  lease_id?: string | null;
  model?: string | null;
  workspace?: string | null;
}

export interface ThreadLaunchConfigResponse {
  source: "last_successful" | "last_confirmed" | "derived";
  config: ThreadLaunchConfig;
}

export interface AccountResourceLimit {
  resource: string;
  provider_name: string;
  label: string;
  limit: number;
  used: number;
  remaining: number;
  can_create: boolean;
  period?: string;
  unit?: string;
}

export interface UserLeaseSummary {
  lease_id: string;
  provider_name: string;
  recipe_id: string;
  recipe_name: string;
  recipe?: RecipeSnapshot;
  observed_state?: string | null;
  desired_state?: string | null;
  cwd?: string | null;
  thread_ids: string[];
  agents: Array<{
    /** Runtime actor identity for this visible lease participant. */
    thread_id: string;
    /** Display label resolved from the actor's backing agent user. */
    agent_name: string;
    avatar_url?: string | null;
  }>;
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

export type NotificationType = "steer" | "command" | "agent" | "chat" | "compact_start" | "compact" | "compact_breaker";

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

export function isTextSegment(segment: TurnSegment): segment is TextSegment {
  return segment.type === "text";
}

export function isToolSegment(segment: TurnSegment): segment is ToolSegment {
  return segment.type === "tool";
}

export function isNoticeSegment(segment: TurnSegment): segment is NoticeSegment {
  return segment.type === "notice";
}

export function isRetrySegment(segment: TurnSegment): segment is RetrySegment {
  return segment.type === "retry";
}

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
  ask_user_question_answered?: {
    questions: AskUserQuestionPrompt[];
    answers: AskUserAnswer[];
    annotations?: Record<string, unknown>;
  };
  senderName?: string;
  senderAvatarUrl?: string;
  attachments?: string[];
}

export interface NoticeMessage {
  id: string;
  role: "notice";
  content: string;
  notification_type?: NotificationType;
  timestamp: number;
}

export type ChatEntry = UserMessage | AssistantTurn | NoticeMessage;

export function isAssistantTurn(entry: ChatEntry): entry is AssistantTurn {
  return entry.role === "assistant";
}

export interface StreamStatus {
  state: { state: string; flags: Record<string, boolean> };
  tokens: { total_tokens: number; input_tokens: number; output_tokens: number; cost: number };
  context: { message_count: number; estimated_tokens: number; usage_percent: number; near_limit: boolean };
  model?: string;
  current_tool?: string;
  last_seq?: number;
  run_start_seq?: number;
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

export interface SandboxFileEntry {
  name: string;
  is_dir: boolean;
  size: number;
  children_count?: number | null;
}

export interface SandboxFilesListResult {
  thread_id: string;
  path: string;
  entries: SandboxFileEntry[];
}

export interface SandboxFileResult {
  thread_id: string;
  path: string;
  content: string;
  size: number;
}

// --- Chat types ---

export interface ChatMember {
  id: string;
  /** Current chat-facing display label for this participant. */
  name: string;
  type: string;
  avatar_url?: string;
  owner_name?: string | null;
  /** Template-facing auxiliary label when this chat member is thread-backed. */
  agent_name?: string | null;
  /** Actor thread backing this participant when applicable. */
  thread_id?: string | null;
  is_main?: boolean | null;
  branch_index?: number | null;
}

export interface ChatDetail {
  id: string;
  title: string | null;
  status: string;
  created_at: number;
  members: ChatMember[];
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  sender_id: string;
  sender_name: string;
  content: string;
  mentioned_ids: string[];
  created_at: number;
}

export interface SandboxUploadResult {
  thread_id: string;
  relative_path: string;
  absolute_path: string;
  size_bytes: number;
  sha256: string;
}
