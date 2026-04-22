import { expect, test, type Page } from "playwright/test";

const MONITOR_TOKEN_KEY = "leon-monitor-token";

test.beforeEach(async ({ page }) => {
  await page.addInitScript((tokenKey) => {
    window.localStorage.setItem(tokenKey, "token-1");
  }, MONITOR_TOKEN_KEY);
});

function field(page: Page, label: string) {
  return page.locator(".evaluation-create-form__field").filter({ hasText: label });
}

test("creates and starts a benchmark batch against the acceptance harness", async ({ page }) => {
  await page.goto("/evaluation");

  await expect(page.getByRole("heading", { level: 1, name: "Evaluation" })).toBeVisible();
  await field(page, "Agent user id").locator("input").fill("agent-1");
  await field(page, "Family").locator("select").selectOption("SWE-bench Verified");
  await field(page, "Judge profile").locator("select").selectOption("command");
  await field(page, "Export profile").locator("select").selectOption("predictions_json");
  await page.getByRole("button", { name: /swe_verified_pytest_7521/i }).click();
  await page.getByRole("button", { name: /swe_verified_pytest_7571/i }).click();
  await page.getByRole("button", { name: "Create batch" }).click();

  await expect(page).toHaveURL(/\/evaluation\/batches\/eval-batch-/);
  await expect(page.getByRole("heading", { name: /Evaluation Batch eval-batch-/ })).toBeVisible();

  await page.getByRole("button", { name: "Start evaluation batch" }).click();
  await expect(page.getByText("Batch execution scheduled.")).toBeVisible();
  await page.waitForTimeout(1000);
  await page.reload();

  const runLink = page.locator("table tbody a").first();
  await expect(runLink).toBeVisible();
  await runLink.click();

  await expect(page.getByRole("heading", { name: /Evaluation Run/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Artifact Viewer" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Raw Trace" })).toBeVisible();
  await expect(page.getByText("Conversation", { exact: true })).toBeVisible();
  await expect(page.getByText("Events", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "model_patch.diff", exact: true })).toBeVisible();
  await expect(page.getByText("SWE-bench Verified", { exact: true })).toBeVisible();
});

test("renders the backend 404 boundary for a missing evaluation run", async ({ page }) => {
  await page.goto("/evaluation/runs/missing-run");

  await expect(page.getByRole("heading", { name: "Evaluation run missing-run: Request failed" })).toBeVisible();
  await expect(page.getByText(/Evaluation run not found: missing-run/)).toBeVisible();
});
