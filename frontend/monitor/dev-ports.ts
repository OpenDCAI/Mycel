import { execSync } from "child_process";

import { resolveMonitorPorts } from "./src/monitor-ports";

export function getWorktreePort(key: string, fallback: string): string {
  try {
    return execSync(`git config --worktree --get ${key}`, { encoding: "utf-8" }).trim();
  } catch {
    return fallback;
  }
}

export function loadMonitorPorts() {
  return resolveMonitorPorts({
    env: process.env,
    getWorktreePort,
  });
}
