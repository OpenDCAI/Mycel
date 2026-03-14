/**
 * Security boundary e2e tests — verifies owner vs contact UI separation.
 *
 * Setup: registers fresh users, creates cross-user conversation,
 * then verifies UI behavior for owner vs contact.
 */
import { test, expect, type Page } from "@playwright/test";

const API = "http://localhost:8005";
const APP = "http://localhost:5177";

interface UserSetup {
  token: string;
  memberId: string;
  agentId?: string;
  agentName?: string;
  convId: string;
}

async function registerUser(username: string, password: string): Promise<UserSetup> {
  const res = await fetch(`${API}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const loginRes = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await loginRes.json();
    return {
      token: data.token,
      memberId: data.member.id,
      agentId: data.agent?.id,
      agentName: data.agent?.name,
      convId: data.conversation_id,
    };
  }
  const data = await res.json();
  return {
    token: data.token,
    memberId: data.member.id,
    agentId: data.agent?.id,
    agentName: data.agent?.name,
    convId: data.conversation_id,
  };
}

async function createConversation(
  token: string,
  members: string[],
): Promise<string> {
  const res = await fetch(`${API}/api/conversations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ members }),
  });
  const data = await res.json();
  return data.id;
}

/** Inject auth state into localStorage so the app loads as authenticated. */
async function loginViaLocalStorage(page: Page, user: UserSetup, username: string) {
  await page.goto(APP);
  await page.evaluate(
    ({ token, member, agent, agentName, convId, username }) => {
      const state = {
        state: {
          token,
          member: { id: member, name: username, type: "human" },
          agent: agent
            ? { id: agent, name: agentName || `${username}'s Leon`, type: "mycel_agent" }
            : null,
          defaultConversationId: convId,
        },
        version: 0,
      };
      localStorage.setItem("leon-auth", JSON.stringify(state));
    },
    {
      token: user.token,
      member: user.memberId,
      agent: user.agentId ?? null,
      agentName: user.agentName ?? null,
      convId: user.convId,
      username,
    },
  );
  await page.reload();
}

test.describe("Owner/Contact Security Boundary", () => {
  let turing: UserSetup;
  let alice: UserSetup;
  let aliceConvWithTuringAgent: string;

  test.beforeAll(async () => {
    turing = await registerUser("turing_e2e", "test1234");
    alice = await registerUser("alice_e2e", "test1234");
    aliceConvWithTuringAgent = await createConversation(alice.token, [
      alice.memberId,
      turing.agentId!,
    ]);
  });

  test("V3: Contact (alice) sees no owner UI components", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    const threadRequests: string[] = [];
    page.on("request", (req) => {
      if (req.url().includes("/api/threads/")) {
        threadRequests.push(req.url());
      }
    });

    await loginViaLocalStorage(page, alice, "alice_e2e");

    // Navigate using sidebar link (click the conversation) — use correct URL format
    // Route: /chat/:memberId/:threadId
    const agentName = turing.agentName || "turing_e2e's Leon";
    await page.goto(`${APP}/chat/${encodeURIComponent(agentName)}/${aliceConvWithTuringAgent}`);
    // Wait for conversations to load and page to settle
    await page.waitForTimeout(3000);

    // V3.1: InputBox should be visible
    const inputBox = page.locator('textarea, input[type="text"]').first();
    await expect(inputBox).toBeVisible({ timeout: 5000 });

    // V3.2: No view toggle button (完整/消息)
    const viewToggle = page.locator('button:has-text("完整"), button:has-text("消息")');
    await expect(viewToggle).toHaveCount(0);

    // V3.3: No ModelSelector
    const modelSelector = page.locator('button:has-text("leon:")');
    await expect(modelSelector).toHaveCount(0);

    // V3.4: No queue/stop buttons (contact InputBox is simpler)
    const queueBtn = page.locator('button:has-text("排队")');
    await expect(queueBtn).toHaveCount(0);

    // V3.6: Zero requests to /api/threads/*
    expect(threadRequests).toHaveLength(0);

    await context.close();
  });

  test("V4: Owner (turing) sees full UI with view toggle", async ({ browser }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    await loginViaLocalStorage(page, turing, "turing_e2e");

    // Navigate to turing's own conversation with their agent
    const agentName = turing.agentName || "turing_e2e's Leon";
    await page.goto(`${APP}/chat/${encodeURIComponent(agentName)}/${turing.convId}`);
    await page.waitForTimeout(3000);

    // V4.1: InputBox visible
    const inputBox = page.locator('textarea, input[type="text"]').first();
    await expect(inputBox).toBeVisible({ timeout: 5000 });

    // V4.2: View toggle exists (完整/消息 button)
    const viewToggle = page.locator('button:has-text("完整"), button:has-text("消息")');
    await expect(viewToggle).toHaveCount(1);

    // V4.2: Click the toggle — should switch mode text
    const toggleText = await viewToggle.textContent();
    await viewToggle.click();
    await page.waitForTimeout(500);
    const newToggle = page.locator('button:has-text("完整"), button:has-text("消息")');
    const newText = await newToggle.textContent();
    expect(newText).not.toBe(toggleText);

    await context.close();
  });

  test("V3.6: Contact network capture — zero thread/monitor requests", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    const allRequests: string[] = [];
    page.on("request", (req) => allRequests.push(req.url()));

    await loginViaLocalStorage(page, alice, "alice_e2e");
    const agentName = turing.agentName || "turing_e2e's Leon";
    await page.goto(`${APP}/chat/${encodeURIComponent(agentName)}/${aliceConvWithTuringAgent}`);
    await page.waitForTimeout(4000);

    const threadHits = allRequests.filter((u) => u.includes("/api/threads/"));
    const monitorHits = allRequests.filter((u) => u.includes("/api/monitor/"));

    expect(threadHits).toHaveLength(0);
    expect(monitorHits).toHaveLength(0);

    await context.close();
  });

  test("V7.2: Contact conversation response — brain_thread_id null for non-owned agent", async ({
    browser,
  }) => {
    const context = await browser.newContext();
    const page = await context.newPage();

    // Intercept the conversations API response
    let conversationsData: any[] = [];
    page.on("response", async (res) => {
      // Match GET /api/conversations (list endpoint, not sub-routes)
      const url = new URL(res.url());
      if (url.pathname === "/api/conversations" && res.request().method() === "GET") {
        try {
          conversationsData = await res.json();
        } catch {}
      }
    });

    await loginViaLocalStorage(page, alice, "alice_e2e");
    await page.goto(`${APP}/chat`);
    await page.waitForTimeout(3000);

    // alice has 2 conversations: one with her own agent (brain_thread_id set),
    // one with turing's agent (brain_thread_id null)
    expect(conversationsData.length).toBeGreaterThanOrEqual(2);

    const convWithTuringAgent = conversationsData.find(
      (c: any) => c.id === aliceConvWithTuringAgent,
    );
    expect(convWithTuringAgent).toBeDefined();
    expect(convWithTuringAgent.brain_thread_id).toBeNull();

    // alice's OWN agent conversation should have brain_thread_id set
    // Filter by brain_thread_id directly — duplicate turing-agent convs from
    // repeated test runs all have null, only alice's own has a value.
    const ownConv = conversationsData.find(
      (c: any) => c.brain_thread_id != null,
    );
    expect(ownConv).toBeDefined();
    expect(ownConv.brain_thread_id).not.toBeNull();

    await context.close();
  });
});
