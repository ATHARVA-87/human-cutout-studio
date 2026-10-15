import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Useful on systems that have reached their Linux inotify watcher limit.
    // Enable with VITE_USE_POLLING=true npm run dev.
    watch: process.env.VITE_USE_POLLING === "true" ? { usePolling: true, interval: 500 } : undefined,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
    },
  },
});
