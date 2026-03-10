import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:5175",
  },
  webServer: {
    command: "npm run dev -- --port 5175",
    port: 5175,
    reuseExistingServer: true,
  },
});
