import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backendPort = process.env.LEON_BACKEND_PORT || "8001";

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
