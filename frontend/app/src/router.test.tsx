// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import { router } from "./router";

interface RouteNode {
  path?: string;
  children?: readonly RouteNode[];
}

function collectPaths(routes: readonly RouteNode[]): string[] {
  const paths: string[] = [];
  for (const route of routes) {
    if (route.path) paths.push(route.path);
    if (route.children) paths.push(...collectPaths(route.children));
  }
  return paths;
}

describe("router removed route contract", () => {
  it("does not keep removed redirect routes alive", () => {
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
    expect(routePaths.has("hire/:memberId")).toBe(false);
    expect(routePaths.has("hire/new/:agentId")).toBe(true);
    expect(routePaths.has("hire/:agentId")).toBe(true);
    expect(routePaths.has("contacts")).toBe(true);
  });
});
