import type { ToolStep } from "../../api";
import { asRecord, recordString } from "../../lib/records";

function firstString(args: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = recordString(args, key);
    if (value) return value;
  }
  return undefined;
}

function summarize(value: string): string {
  return value.length > 60 ? value.slice(0, 57) + "..." : value;
}

export function formatTime(ts?: number): string {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

export function getStepSummary(step: ToolStep): string {
  const args = asRecord(step.args);
  if (!args) return step.name;

  // Agent tool: show description (PascalCase from backend)
  if (step.name === "Agent") {
    const description = firstString(args, ["Description", "description"]);
    if (description) return summarize(description);
    const prompt = firstString(args, ["Prompt", "prompt"]);
    if (prompt) return summarize(prompt);
  }

  // TaskOutput tool
  if (step.name === "TaskOutput") {
    return "查看任务输出";
  }

  const filePath = firstString(args, ["FilePath", "file_path", "path"]);
  if (filePath) {
    const parts = filePath.split("/");
    return parts[parts.length - 1] || filePath;
  }

  const cmd = recordString(args, "command");
  if (cmd) {
    return summarize(cmd);
  }

  const pattern = firstString(args, ["Pattern", "pattern", "query", "SearchPath"]);
  if (pattern) {
    return summarize(pattern);
  }

  const desc = firstString(args, ["Description", "description", "Prompt", "prompt"]);
  if (desc) {
    return summarize(desc);
  }

  return step.name;
}

export function getStepResultSummary(step: ToolStep): string | null {
  if (!step.result) return null;

  const args = asRecord(step.args);
  const result = step.result.trim();

  // Read: count lines
  if (step.name === "Read") {
    const lines = result.split("\n").length;
    return `Read ${lines} lines`;
  }

  // Write: count lines from result or args.content
  if (step.name === "Write") {
    const lines = result.split("\n").length;
    if (lines > 1) return `Wrote ${lines} lines`;
    if (args) {
      const content = firstString(args, ["Content", "content"]);
      if (content) {
        const contentLines = content.split("\n").length;
        return `Wrote ${contentLines} lines`;
      }
    }
    return "Wrote file";
  }

  // Edit: calculate added/removed from args
  if (step.name === "Edit") {
    if (args) {
      const oldString = firstString(args, ["OldString", "old_string"]);
      const newString = firstString(args, ["NewString", "new_string"]);
      if (oldString && newString) {
        const removed = oldString.split("\n").length;
        const added = newString.split("\n").length;
        return `Added ${added}, removed ${removed}`;
      }
    }
    return "Edited file";
  }

  // Grep/Glob: count non-empty lines
  if (step.name === "Grep" || step.name === "Glob") {
    const matches = result.split("\n").filter(line => line.trim()).length;
    return `Found ${matches} matches`;
  }

  // Bash: first line (truncate 60 chars) or exit code
  if (step.name === "Bash") {
    const firstLine = result.split("\n")[0];
    if (firstLine) {
      return summarize(firstLine);
    }
    return "Done";
  }

  // WebFetch/WebSearch: extract summary or "Done"
  if (step.name === "WebFetch" || step.name === "WebSearch") {
    return "Done";
  }

  // Agent/TaskCreate/...: first 60 chars of result
  if (step.name === "Agent" || step.name === "TaskCreate" || step.name === "TaskOutput") {
    return summarize(result);
  }

  return null;
}
