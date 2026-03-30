import { describe, expect, it } from "vitest";

import type { ThreadSummary } from "@/api";
import type { ScheduledTask } from "@/store/types";

import {
  cronToHuman,
  formatEventTime,
  isValidCronExpression,
  matchesScheduledTaskQuery,
  normalizeCronExpression,
  schedulePresets,
  resolveThreadHref,
  resolveThreadLabel,
  resolveThreadMeta,
} from "./scheduled-task-display";

const thread: ThreadSummary = {
  thread_id: "thread-1",
  member_id: "member-1",
  member_name: "Scheduler Agent",
  entity_name: "Daily Brief",
  sidebar_label: "主线对话",
};

describe("scheduled task display", () => {
  it("resolves thread label and href from thread summary", () => {
    expect(resolveThreadLabel(thread.thread_id, [thread])).toBe("Daily Brief");
    expect(resolveThreadMeta(thread.thread_id, [thread])).toBe("主线对话 · thread-1");
    expect(resolveThreadHref(thread.thread_id, [thread])).toBe("/threads/member-1/thread-1");
  });

  it("falls back to raw thread id when summary is missing", () => {
    expect(resolveThreadLabel("thread-missing", [])).toBe("thread-missing");
    expect(resolveThreadMeta("thread-missing", [])).toBe("thread-missing");
    expect(resolveThreadHref("thread-missing", [])).toBeNull();
  });

  it("turns common cron expressions into human text", () => {
    expect(cronToHuman("0 9 * * *")).toBe("每天 9:00");
    expect(cronToHuman("0 9 * * 1-5")).toBe("工作日 9:00");
    expect(cronToHuman("30 14 * * 1,3")).toBe("每周一、三 14:30");
  });

  it("exposes the common schedule presets used by the editor", () => {
    expect(schedulePresets.map((preset) => preset.expression)).toEqual([
      "0 9 * * *",
      "0 9 * * 1-5",
      "0 9 * * 1",
      "0 * * * *",
    ]);
  });

  it("validates cron expressions with minimal field checks", () => {
    expect(isValidCronExpression("0 9 * * *")).toBe(true);
    expect(isValidCronExpression("0 25 * * *")).toBe(false);
    expect(isValidCronExpression("0 9 * * 8")).toBe(false);
    expect(isValidCronExpression("*/15 * * * *")).toBe(true);
    expect(isValidCronExpression("bad cron")).toBe(false);
  });

  it("normalizes whitespace in cron expressions before comparing presets", () => {
    expect(normalizeCronExpression("  0  9   * *   * ")).toBe("0 9 * * *");
  });

  it("matches scheduled task query against name and instruction", () => {
    const task = {
      id: "scheduled-1",
      thread_id: "thread-1",
      name: "Morning Review",
      instruction: "Summarize the thread and list blockers",
      cron_expression: "0 9 * * *",
      enabled: 1,
      created_at: 0,
      updated_at: 0,
      last_triggered_at: 0,
      next_trigger_at: 0,
    } satisfies ScheduledTask;

    expect(matchesScheduledTaskQuery(task, "")).toBe(true);
    expect(matchesScheduledTaskQuery(task, "review")).toBe(true);
    expect(matchesScheduledTaskQuery(task, "blockers")).toBe(true);
    expect(matchesScheduledTaskQuery(task, "nightly")).toBe(false);
  });

  it("formats event time with relative and absolute text", () => {
    const now = Date.now();
    const label = formatEventTime(now - 60_000);
    expect(label).toContain("前");
    expect(label).toContain("·");
  });

  it("formats next trigger summary for future timestamps", () => {
    const summary = formatEventTime(Date.now() + 60 * 60 * 1000);
    expect(summary).not.toBe("--");
    expect(summary).toContain("·");
  });
});
