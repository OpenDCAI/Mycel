import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.LEON_BACKEND_PORT || "8001";
const monitorPort = parseInt(process.env.LEON_MONITOR_PORT || "15154", 10);
const monitorPreviewPort = parseInt(process.env.LEON_MONITOR_PREVIEW_PORT || "14154", 10);

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
