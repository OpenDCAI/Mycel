// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import { router } from "./router";

function collectPaths(routes: readonly { path?: string; children?: readonly { path?: string; children?: readonly any[] }[] }[]): string[] {
  const paths: string[] = [];
  for (const route of routes) {
    if (route.path) paths.push(route.path);
    if (route.children) paths.push(...collectPaths(route.children));
  }
  return paths;
}

describe("router legacy contract", () => {
  it("does not keep removed legacy redirect routes alive", () => {
    const routePaths = new Set(collectPaths(router.routes));

    expect(routePaths.has("/members")).toBe(false);
    expect(routePaths.has("/members/*")).toBe(false);
    expect(routePaths.has("/threads")).toBe(false);
    expect(routePaths.has("/threads/*")).toBe(false);
    expect(routePaths.has("/chats")).toBe(false);
    expect(routePaths.has("/chats/*")).toBe(false);
    expect(routePaths.has("/tasks")).toBe(false);
    expect(routePaths.has("/resources")).toBe(false);
    expect(routePaths.has("/invite-codes")).toBe(false);
    expect(routePaths.has("hire/:memberId/:threadId")).toBe(false);
    expect(routePaths.has("contacts")).toBe(true);
  });
});
