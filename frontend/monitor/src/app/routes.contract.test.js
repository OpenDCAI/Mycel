import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("standalone monitor routes contract", () => {
  it("does not expose stale thread workbench routes or links", () => {
    const routeSource = readFileSync(resolve(import.meta.dirname, "routes.tsx"), "utf8");
    const navSource = readFileSync(resolve(import.meta.dirname, "monitor-nav.ts"), "utf8");
    const pageSources = [
      "../ResourcesPage.tsx",
      "../pages/SandboxesPage.tsx",
      "../pages/SandboxDetailPage.tsx",
      "../pages/RuntimeDetailPage.tsx",
      "../pages/EvaluationPage.tsx",
      "../pages/EvaluationBatchDetailPage.tsx",
      "../pages/EvaluationRunDetailPage.tsx",
    ].map((relativePath) => readFileSync(resolve(import.meta.dirname, relativePath), "utf8"));

    expect(routeSource).not.toContain('path="/threads"');
    expect(routeSource).not.toContain('path="/threads/:threadId"');
    expect(routeSource).not.toContain("ThreadsPage");
    expect(routeSource).not.toContain("ThreadDetailPage");
    expect(navSource).not.toContain('{ to: "/threads"');

    for (const source of pageSources) {
      expect(source).not.toContain("to={`/threads/");
      expect(source).not.toContain('to="/threads"');
    }
  });

  it("redirects unmatched standalone monitor paths back to dashboard", () => {
    const routeSource = readFileSync(resolve(import.meta.dirname, "routes.tsx"), "utf8");

    expect(routeSource).toContain('path="*"');
    expect(routeSource).toContain('to="/dashboard"');
  });
});
