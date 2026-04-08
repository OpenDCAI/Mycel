import { describe, expect, it, vi } from "vitest";

import { calculateDuration, formatDuration, formatStartedAtDuration } from "./duration";

describe("resource duration helpers", () => {
  it("formats positive durations for active sandboxes", () => {
    expect(formatDuration(65_000)).toBe("1分5秒");
  });

  it("treats future timestamps as invalid instead of negative elapsed time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-07T12:00:00Z"));

    expect(calculateDuration("2026-04-07T12:05:00Z")).toBeNull();
    expect(formatStartedAtDuration("2026-04-07T12:05:00Z")).toBe("时间异常");

    vi.useRealTimers();
  });

  it("treats malformed timestamps as invalid", () => {
    expect(calculateDuration("not-a-date")).toBeNull();
  });
});
