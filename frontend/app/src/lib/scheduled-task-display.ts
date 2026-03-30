import { format, formatDistanceToNow } from "date-fns";
import { zhCN } from "date-fns/locale";

import type { ThreadSummary } from "@/api";
import type { ScheduledTask } from "@/store/types";

export const schedulePresets = [
  { label: "每天 9:00", expression: "0 9 * * *" },
  { label: "工作日 9:00", expression: "0 9 * * 1-5" },
  { label: "每周一 9:00", expression: "0 9 * * 1" },
  { label: "每小时", expression: "0 * * * *" },
] as const;

export function findThreadSummary(threadId: string, threads: ThreadSummary[]): ThreadSummary | null {
  return threads.find((thread) => thread.thread_id === threadId) ?? null;
}

export function resolveThreadLabel(threadId: string, threads: ThreadSummary[]): string {
  const thread = findThreadSummary(threadId, threads);
  return thread?.entity_name || thread?.member_name || threadId;
}

export function resolveThreadMeta(threadId: string, threads: ThreadSummary[]): string {
  const thread = findThreadSummary(threadId, threads);
  if (!thread) return threadId;
  return [thread.sidebar_label, thread.thread_id].filter(Boolean).join(" · ");
}

export function resolveThreadHref(threadId: string, threads: ThreadSummary[]): string | null {
  const thread = findThreadSummary(threadId, threads);
  if (!thread?.member_id) return null;
  return `/threads/${encodeURIComponent(thread.member_id)}/${encodeURIComponent(thread.thread_id)}`;
}

export function cronToHuman(expr: string): string {
  const normalized = normalizeCronExpression(expr);
  const parts = normalized.split(" ");
  if (parts.length !== 5) return expr;
  const [min, hour, dom, , dow] = parts;
  if (dow === "1-5" && dom === "*") return `工作日 ${hour}:${min.padStart(2, "0")}`;
  if (min === "0" && hour !== "*" && dom === "*" && dow === "*") return `每天 ${hour}:00`;
  if (hour !== "*" && dom === "*" && dow === "*") return `每天 ${hour}:${min.padStart(2, "0")}`;
  if (dom === "*" && dow !== "*") {
    const labels = ["日", "一", "二", "三", "四", "五", "六"];
    const days = dow.split(",").map((day) => labels[parseInt(day, 10)] || day).join("、");
    return `每周${days} ${hour}:${min.padStart(2, "0")}`;
  }
  if (dom !== "*" && dow === "*") return `每月 ${dom} 日 ${hour}:${min.padStart(2, "0")}`;
  return expr;
}

export function normalizeCronExpression(expr: string): string {
  return expr.trim().split(/\s+/).filter(Boolean).join(" ");
}

function isValidCronToken(token: string, min: number, max: number): boolean {
  if (token === "*") return true;
  if (/^\*\/\d+$/.test(token)) {
    return Number(token.slice(2)) > 0;
  }
  const segments = token.split(",");
  return segments.every((segment) => {
    if (/^\d+$/.test(segment)) {
      const value = Number(segment);
      return value >= min && value <= max;
    }
    if (/^\d+-\d+$/.test(segment)) {
      const [start, end] = segment.split("-").map(Number);
      return start >= min && end <= max && start <= end;
    }
    return false;
  });
}

export function isValidCronExpression(expr: string): boolean {
  const parts = normalizeCronExpression(expr).split(" ");
  if (parts.length !== 5) return false;
  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;
  return [
    isValidCronToken(minute, 0, 59),
    isValidCronToken(hour, 0, 23),
    isValidCronToken(dayOfMonth, 1, 31),
    isValidCronToken(month, 1, 12),
    isValidCronToken(dayOfWeek, 0, 7),
  ].every(Boolean);
}

export function matchesScheduledTaskQuery(task: Pick<ScheduledTask, "name" | "instruction">, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return [task.name, task.instruction].join(" ").toLowerCase().includes(needle);
}

function formatAbsoluteTime(value: number): string {
  return format(new Date(value), "MM-dd HH:mm", { locale: zhCN });
}

export function formatEventTime(value?: number): string {
  if (!value) return "--";
  return `${formatDistanceToNow(new Date(value), { addSuffix: true, locale: zhCN })} · ${formatAbsoluteTime(value)}`;
}
