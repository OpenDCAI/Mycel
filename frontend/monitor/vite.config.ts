import { execSync } from "child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function getWorktreePort(key: string, fallback: string): string {
  try {
    return execSync(`git config --worktree --get ${key}`, { encoding: "utf-8" }).trim();
  } catch {
    return fallback;
  }
}

const backendPort = process.env.LEON_BACKEND_PORT || getWorktreePort("worktree.ports.backend", "8001");
const monitorPort = parseInt(process.env.LEON_MONITOR_PORT || "5174", 10);
const monitorPreviewPort = parseInt(process.env.LEON_MONITOR_PREVIEW_PORT || "4174", 10);

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: monitorPort,
    strictPort: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "0.0.0.0",
    port: monitorPreviewPort,
    strictPort: true,
  },
});
