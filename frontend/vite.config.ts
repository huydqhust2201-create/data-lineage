import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Backend chạy ở 127.0.0.1:8001 (không phải 8000 — cổng đó hay bị chiếm bởi
// service khác trên máy dev; không phải localhost — Windows resolve ra ::1
// trước). Proxy /api và /health để tránh phải cấu hình CORS lúc dev.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8001", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
});
