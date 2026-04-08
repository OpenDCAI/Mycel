export type AgentStatus = "active" | "draft" | "inactive";

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

export interface AgentConfig {
  prompt: string;
  rules: RuleItem[];
  tools: CrudItem[];
  mcps: McpItem[];
  skills: CrudItem[];
  subAgents: SubAgent[];
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: AgentStatus;
  version: string;
  avatar_url?: string;
  config: AgentConfig;
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

export interface ResourceItem {
  id: string;
  name: string;
  desc: string;
  type: string;
  created_at: number;
  updated_at: number;
  provider_name?: string;
  provider_type?: string;
  available?: boolean;
  builtin?: boolean;
  features?: Record<string, boolean>;
  configurable_features?: Record<string, boolean>;
  feature_options?: Array<{
    key: string;
    name: string;
    description: string;
    icon?: string;
  }>;
}

export interface UserProfile {
  name: string;
  initials: string;
  email: string;
}
