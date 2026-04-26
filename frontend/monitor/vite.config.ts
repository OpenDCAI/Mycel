import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

import { loadMonitorPorts } from "./dev-ports";

const { backendPort, monitorBackendPort, devPort, previewPort } = loadMonitorPorts();

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: devPort,
    strictPort: true,
    proxy: {
      "/api/monitor": {
        target: `http://127.0.0.1:${monitorBackendPort}`,
        changeOrigin: true,
      },
      "/api": {
        target: `http://127.0.0.1:${backendPort}`,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: previewPort,
    strictPort: true,
  },
});
