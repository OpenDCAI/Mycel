import type { ChatEntry, ToolStep, SandboxFileEntry } from "../../api";
import type { TreeNode } from "./types";

/* ── Flow types for message-flow panel ── */

export type FlowItem =
  | { type: "text"; content: string; turnId: string }
  | { type: "tool"; step: ToolStep; turnId: string };

/** Extract a chronological message flow (text + tool) from chat entries.
 *  The last non-empty text segment per turn is excluded (already shown in chat area). */
export function extractMessageFlow(entries: ChatEntry[]): FlowItem[] {
  const items: FlowItem[] = [];
  for (const entry of entries) {
    if (entry.role !== "assistant") continue;
    const segs = entry.segments;
    // Find last non-empty text index — exclude it (displayed in chat area)
    let lastTextIdx = -1;
    for (let i = segs.length - 1; i >= 0; i--) {
      const seg = segs[i];
      if (seg.type === "text" && seg.content.trim()) {
        lastTextIdx = i;
        break;
      }
    }
    for (let i = 0; i < segs.length; i++) {
      const seg = segs[i];
      if (seg.type === "tool") {
        items.push({ type: "tool", step: seg.step, turnId: entry.id });
      } else if (seg.type === "text" && i !== lastTextIdx && seg.content.trim()) {
        items.push({ type: "text", content: seg.content, turnId: entry.id });
      }
    }
  }
  return items;
}

export function joinPath(base: string, name: string): string {
  if (base.endsWith("/")) return `${base}${name}`;
  return `${base}/${name}`;
}

/** Extract all run_command tool steps from chat entries */
export function extractCommandSteps(entries: ChatEntry[]): ToolStep[] {
  const steps: ToolStep[] = [];
  for (const entry of entries) {
    if (entry.role !== "assistant") continue;
    for (const seg of entry.segments) {
      if (seg.type === "tool" && seg.step.name === "run_command") {
        steps.push(seg.step);
      }
    }
  }
  return steps;
}

/** Extract all Agent tool steps from chat entries */
export function extractAgentSteps(entries: ChatEntry[]): ToolStep[] {
  const steps: ToolStep[] = [];
  for (const entry of entries) {
    if (entry.role !== "assistant") continue;
    for (const seg of entry.segments) {
      if (seg.type === "tool" && seg.step.name === "Agent") {
        steps.push(seg.step);
      }
    }
  }
  return steps;
}

/** Extract all tool steps from chat entries */
export function extractAllToolSteps(entries: ChatEntry[]): ToolStep[] {
  const steps: ToolStep[] = [];
  for (const entry of entries) {
    if (entry.role !== "assistant") continue;
    for (const seg of entry.segments) {
      if (seg.type === "tool") {
        steps.push(seg.step);
      }
    }
  }
  return steps;
}

export function parseCommandArgs(args: unknown): { command?: string; cwd?: string; description?: string } {
  if (args && typeof args === "object") {
    const a = args as Record<string, unknown>;
    return {
      command: (a.CommandLine ?? a.command ?? a.cmd) as string | undefined,
      cwd: (a.Cwd ?? a.cwd ?? a.working_directory) as string | undefined,
      description: a.description as string | undefined,
    };
  }
  return {};
}

export function parseAgentArgs(args: unknown): { description?: string; prompt?: string; subagent_type?: string } {
  if (args && typeof args === "object") {
    const a = args as Record<string, unknown>;
    return {
      description: (a.Description ?? a.description) as string | undefined,
      prompt: (a.Prompt ?? a.prompt) as string | undefined,
      subagent_type: (a.SubagentType ?? a.subagent_type) as string | undefined,
    };
  }
  return {};
}

export function buildTreeNodes(entries: SandboxFileEntry[], parentPath: string): TreeNode[] {
  return entries.map((e) => ({
    ...e,
    fullPath: joinPath(parentPath, e.name),
    children: undefined,
    expanded: false,
    loading: false,
  }));
}

export function updateNodeAtPath(
  nodes: TreeNode[],
  targetPath: string,
  updater: (node: TreeNode) => TreeNode,
): TreeNode[] {
  return nodes.map((node) => {
    if (node.fullPath === targetPath) return updater(node);
    if (node.children && targetPath.startsWith(node.fullPath + "/")) {
      return { ...node, children: updateNodeAtPath(node.children, targetPath, updater) };
    }
    return node;
  });
}
