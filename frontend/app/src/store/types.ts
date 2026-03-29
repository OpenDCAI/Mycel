export type MemberStatus = "active" | "draft" | "inactive";

export interface CrudItem {
  id?: string;
  name: string;
  desc: string;
  enabled: boolean;
  group?: string;
}

export interface SubAgent {
  name: string;
  desc: string;
  tools: CrudItem[];
  system_prompt: string;
  builtin?: boolean;
}

export interface RuleItem {
  name: string;
  content: string;
}

export interface McpItem {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  disabled: boolean;
}

export interface MemberConfig {
  prompt: string;
  rules: RuleItem[];
  tools: CrudItem[];
  mcps: McpItem[];
  skills: CrudItem[];
  subAgents: SubAgent[];
}

export interface Member {
  id: string;
  name: string;
  description: string;
  status: MemberStatus;
  version: string;
  avatar_url?: string;
  config: MemberConfig;
  created_at: number;
  updated_at: number;
  builtin?: boolean;
}

export type TaskStatus = "pending" | "running" | "completed" | "failed";
export type Priority = "high" | "medium" | "low";
export type TaskSource = "manual" | "cron" | "agent" | "queue";

export interface Task {
  id: string;
  title: string;
  description: string;
  assignee_id: string;
  status: TaskStatus;
  priority: Priority;
  progress: number;
  deadline: string;
  created_at: number;
  // New fields
  thread_id: string;
  source: TaskSource;
  cron_job_id: string;
  result: string;
  started_at: number;
  completed_at: number;
  tags: string[];
}

export interface CronJob {
  id: string;
  name: string;
  description: string;
  cron_expression: string;
  task_template: string;
  enabled: number;
  last_run_at: number;
  next_run_at: number;
  created_at: number;
}

export interface ScheduledTask {
  id: string;
  thread_id: string;
  name: string;
  instruction: string;
  cron_expression: string;
  enabled: number;
  last_triggered_at: number;
  next_trigger_at: number;
  created_at: number;
  updated_at: number;
}

export interface ScheduledTaskRun {
  id: string;
  scheduled_task_id: string;
  thread_id: string;
  status: "queued" | "dispatched" | "completed" | "failed";
  triggered_at: number;
  started_at: number;
  completed_at: number;
  thread_run_id: string;
  error: string;
  dispatch_result?: Record<string, unknown> | null;
}

export interface ResourceItem {
  id: string;
  name: string;
  desc: string;
  type: string;
  created_at: number;
  updated_at: number;
}

export interface UserProfile {
  name: string;
  initials: string;
  email: string;
}

// Backward compatibility aliases
export type StaffStatus = MemberStatus;
export type StaffConfig = MemberConfig;
export type Staff = Member;
