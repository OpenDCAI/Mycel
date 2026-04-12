import type { ChatEntry, ToolStep, SandboxFileEntry } from "../../api";
import { asRecord, recordString } from "../../lib/records";
import type { TreeNode } from "./types";

/* ── Flow types for message-flow panel ── */

export type FlowItem =
  | { type: "text"; content: string; turnId: string }
  | { type: "tool"; step: ToolStep; turnId: string };
function joinPath(base: string, name: string): string {
  if (base.endsWith("/")) return `${base}${name}`;
  return `${base}/${name}`;
}

function firstString(args: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = recordString(args, key);
    if (value !== undefined) return value;
  }
  return undefined;
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

export function parseAgentArgs(args: unknown): { description?: string; prompt?: string; subagent_type?: string } {
  const a = asRecord(args);
  if (!a) return {};
  const description = firstString(a, ["Description", "description"]);
  const prompt = firstString(a, ["Prompt", "prompt"]);
  const subagentType = firstString(a, ["SubagentType", "subagent_type"]);
  return {
    ...(description !== undefined ? { description } : {}),
    ...(prompt !== undefined ? { prompt } : {}),
    ...(subagentType !== undefined ? { subagent_type: subagentType } : {}),
  };
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
