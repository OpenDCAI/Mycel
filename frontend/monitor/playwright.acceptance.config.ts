import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "playwright/test";
const configDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(configDir, "../..");
const harnessPort = Number(process.env.LEON_MONITOR_ACCEPTANCE_BACKEND_PORT || 8766);
const monitorPort = Number(process.env.LEON_MONITOR_ACCEPTANCE_FRONTEND_PORT || 4175);

export default defineConfig({
  testDir: "./playwright",
  testMatch: /.*acceptance\.e2e\.ts/,
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: `http://127.0.0.1:${monitorPort}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `${path.join(repoRoot, ".venv", "bin", "python")} -m eval.benchmarks.swe_verified.acceptance serve --port ${harnessPort}`,
      cwd: repoRoot,
      port: harnessPort,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: `LEON_BACKEND_PORT=${harnessPort} LEON_MONITOR_BACKEND_PORT=${harnessPort} npm run dev -- --host 127.0.0.1 --port ${monitorPort}`,
      cwd: path.join(repoRoot, "frontend", "monitor"),
      port: monitorPort,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
});
