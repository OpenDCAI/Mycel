import type { ToolStep } from "../../api";

export type AgentVisualStatus = "running" | "completed" | "error";

interface ResolveAgentVisualStatusOptions {
  childDisplayRunning?: boolean;
  childRuntimeState?: string | null;
  statusOverride?: AgentVisualStatus | null;
}

export function resolveAgentVisualStatus(
  step: ToolStep,
  options: ResolveAgentVisualStatusOptions = {},
): AgentVisualStatus {
  const { childDisplayRunning = false, childRuntimeState = null, statusOverride = null } = options;
  const stream = step.subagent_stream;

  if (statusOverride) return statusOverride;
  if (step.status === "error" || stream?.status === "error") return "error";
  if (childRuntimeState === "idle" && !childDisplayRunning) return "completed";
  if (childDisplayRunning) return "running";
  if (stream?.status === "running") return "running";
  if (step.status === "done" || stream?.status === "completed") return "completed";
  return "running";
}
