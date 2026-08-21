import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND_URL || "http://app:8000",
        changeOrigin: true,
        secure: false,
      },
      "/health": {
        target: process.env.VITE_BACKEND_URL || "http://app:8000",
        changeOrigin: true,
        secure: false,
      },
      "/docs": {
        target: process.env.VITE_BACKEND_URL || "http://app:8000",
        changeOrigin: true,
        secure: false,
      },
      "/metrics": {
        target: process.env.VITE_BACKEND_URL || "http://app:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
