import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: "http://localhost:5177",
    headless: true,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
