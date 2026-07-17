import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    preserveSymlinks: true,
    dedupe: ["react", "react-dom"],
  },
  server: {
    host: "0.0.0.0",
    port: 7505,
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8505",
        changeOrigin: true,
      },
      "/identity-api": {
        target: process.env.VITE_IDENTITY_PROXY_TARGET || "http://localhost:8500",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/identity-api/, "/api/v1"),
      },
      "/docs": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8505",
        changeOrigin: true,
      },
    },
  },
});
