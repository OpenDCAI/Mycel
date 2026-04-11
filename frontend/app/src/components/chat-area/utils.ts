import type { ToolStep } from "../../api";
import { asRecord } from "../../lib/records";

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
    const description = (args.Description ?? args.description) as string;
    if (description) return description.length > 60 ? description.slice(0, 57) + "..." : description;
    const prompt = (args.Prompt ?? args.prompt) as string;
    if (prompt) return prompt.length > 60 ? prompt.slice(0, 57) + "..." : prompt;
  }

  // TaskOutput tool
  if (step.name === "TaskOutput") {
    return "查看任务输出";
  }

  const filePath =
    (args.FilePath as string) ??
    (args.file_path as string) ??
    (args.path as string);
  if (filePath) {
    const parts = filePath.split("/");
    return parts[parts.length - 1] || filePath;
  }

  const cmd = args.command as string;
  if (cmd) {
    return cmd.length > 60 ? cmd.slice(0, 57) + "..." : cmd;
  }

  const pattern =
    (args.Pattern as string) ??
    (args.pattern as string) ??
    (args.query as string) ??
    (args.SearchPath as string);
  if (pattern) {
    return pattern.length > 60 ? pattern.slice(0, 57) + "..." : pattern;
  }

  const desc = (args.Description ?? args.description ?? args.Prompt ?? args.prompt) as string;
  if (desc) {
    return desc.length > 60 ? desc.slice(0, 57) + "..." : desc;
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
      const content = (args.Content ?? args.content) as string;
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
      const oldString = (args.OldString ?? args.old_string) as string;
      const newString = (args.NewString ?? args.new_string) as string;
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
      return firstLine.length > 60 ? firstLine.slice(0, 57) + "..." : firstLine;
    }
    return "Done";
  }

  // WebFetch/WebSearch: extract summary or "Done"
  if (step.name === "WebFetch" || step.name === "WebSearch") {
    return "Done";
  }

  // Agent/TaskCreate/...: first 60 chars of result
  if (step.name === "Agent" || step.name === "TaskCreate" || step.name === "TaskOutput") {
    return result.length > 60 ? result.slice(0, 57) + "..." : result;
  }

  return null;
}
