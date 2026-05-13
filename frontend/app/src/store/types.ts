type AgentStatus = "active" | "draft" | "inactive";

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

interface McpItem {
  name: string;
  command: string;
  args: string[];
  env: Record<string, string>;
  enabled: boolean;
}

export interface AgentConfig {
  prompt: string;
  rules: RuleItem[];
  tools: CrudItem[];
  mcpServers: McpItem[];
  skills: CrudItem[];
  subAgents: SubAgent[];
  compact?: {
    trigger_tokens?: number | null;
  };
}

export interface SkillPatchItem {
  id: string;
  enabled?: boolean;
}

export type AgentConfigPatch = Partial<Omit<AgentConfig, "skills">> & {
  skills?: SkillPatchItem[];
};

export interface Agent {
  id: string;
  name: string;
  description: string;
  status: AgentStatus;
  version: string;
  source?: {
    marketplace_item_id?: string;
    source_version?: string;
  };
  avatar_url?: string;
  config: AgentConfig;
  config_loaded?: boolean;
  created_at: number;
  updated_at: number;
  builtin?: boolean;
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
