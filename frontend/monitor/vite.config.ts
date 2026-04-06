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

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4174,
    strictPort: true,
  },
});
