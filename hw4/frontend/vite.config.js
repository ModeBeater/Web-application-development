import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Where the Django API runs when the frontend is served by Vite (dev server / preview).
// Inside Docker the nginx config (nginx.conf) does the same proxying, so the browser
// always talks to one origin and CORS is not involved. VITE_API_URL switches the app
// to direct cross-origin calls instead (then CORS_ALLOWED_ORIGINS on the backend matters).
const API = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";

// Paths that belong to the backend and are forwarded as-is
const proxy = Object.fromEntries(
  ["/api", "/health", "/docs", "/openapi.yaml", "/static"].map((path) => [path, { target: API, changeOrigin: false }]),
);

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: true, proxy },
  preview: { port: 3000, host: true, proxy },
  build: { outDir: "dist", sourcemap: false },
});
