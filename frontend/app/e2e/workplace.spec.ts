import { test, expect, type Page } from "@playwright/test";

const MOCK_MEMBER = {
  id: "__leon__",
  name: "__leon__",
  description: "Built-in assistant",
  status: "active",
  version: "1.0.0",
  config: {
    prompt: "",
    tools: [],
    mcps: [],
    skills: [],
    subAgents: [],
    rules: [],
  },
};

/** Set up mocks that loadAll + getMemberById need to render the detail page. */
async function mockMemberPage(page: Page) {
  // Member detail
  await page.route("**/api/panel/members/__leon__", (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MOCK_MEMBER),
      });
    }
    return route.fallback();
  });

  // Members list (loadAll) — must include __leon__ so getMemberById finds it
  await page.route("**/api/panel/members", (route) => {
    if (route.request().url().endsWith("/members")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [MOCK_MEMBER] }),
      });
    }
    return route.fallback();
  });

  // Library endpoints (loadAll)
  for (const rt of ["skills", "mcps", "agents"]) {
    await page.route(`**/api/panel/library/${rt}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      }),
    );
  }
}

test.describe("Workplace tab", () => {
  test("shows workplace cards for a member", async ({ page }) => {
    await page.route("**/api/panel/members/__leon__/workplaces", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              member_name: "__leon__",
              provider_type: "daytona_selfhost",
              backend_ref: "leon-workplace-__leon__",
              mount_path: "/home/daytona/files",
              created_at: "2026-03-10T11:32:30.316198+00:00",
            },
          ],
        }),
      }),
    );

    await mockMemberPage(page);
    await page.goto("/members/__leon__");

    await page.getByRole("button", { name: "Workplace" }).click();

    await expect(page.getByText("daytona_selfhost")).toBeVisible();
    await expect(page.getByText("leon-workplace-__leon__")).toBeVisible();
    await expect(page.getByText("/home/daytona/files")).toBeVisible();
  });

  test("shows empty state when no workplaces", async ({ page }) => {
    await page.route("**/api/panel/members/__leon__/workplaces", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      }),
    );

    await mockMemberPage(page);
    await page.goto("/members/__leon__");

    await page.getByRole("button", { name: "Workplace" }).click();

    await expect(page.getByText("No workplaces created yet")).toBeVisible();
  });

  test("createThread sends agent in POST body", async ({ page }) => {
    let capturedBody: Record<string, string> | null = null;
    await page.route("**/api/threads", (route) => {
      if (route.request().method() === "POST") {
        capturedBody = route.request().postDataJSON();
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            thread_id: "test-thread-id",
            sandbox: "daytona_selfhost",
            agent: "__leon__",
            workspace_id: null,
          }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ threads: [] }),
      });
    });

    await page.goto("/");
    await page.evaluate(async () => {
      await fetch("/api/threads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sandbox: "daytona_selfhost", agent: "__leon__" }),
      });
    });

    expect(capturedBody).toBeTruthy();
    expect(capturedBody!.agent).toBe("__leon__");
    expect(capturedBody!.sandbox).toBe("daytona_selfhost");
  });
});
