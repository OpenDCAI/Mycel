import { execSync } from "child_process"
import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"
import { inspectAttr } from 'kimi-plugin-inspect-react'

function getWorktreePort(key: string, defaultPort: string): string {
  try {
    return execSync(`git config --worktree --get ${key}`, { encoding: "utf-8" }).trim()
  } catch {
    return defaultPort
  }
}

const backendPort = process.env.LEON_BACKEND_PORT || getWorktreePort("worktree.ports.backend", "8001")
const frontendPort = parseInt(process.env.LEON_FRONTEND_PORT || getWorktreePort("worktree.ports.frontend", "5173"))

// https://vite.dev/config/
export default defineConfig({
  base: '/',
  plugins: [inspectAttr(), react()],
  server: {
    host: "0.0.0.0",
    port: frontendPort,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
        configure: (proxy) => {
          // Disable buffering for SSE responses
          proxy.on("proxyRes", (proxyRes) => {
            if (proxyRes.headers["content-type"]?.includes("text/event-stream")) {
              // Ensure no compression/buffering on the proxy side
              proxyRes.headers["cache-control"] = "no-cache";
              proxyRes.headers["x-accel-buffering"] = "no";
            }
          });
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
