import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is proxied in development so the browser only ever talks to one
// origin — no CORS preflight on every keystroke, and the production build
// (served by FastAPI itself) uses the identical relative paths.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // Recharts is by far the heaviest dependency and changes only when the
        // lockfile does. Splitting it out means an edit to the app ships a
        // small chunk and leaves the vendor bundle cached.
        manualChunks: {
          charts: ["recharts"],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
});
