/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_TARGET || "http://127.0.0.1:5000";

  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_DEV_PORT || 5173),
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          secure: false
        }
      }
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test-setup.ts",
    },
  };
});
