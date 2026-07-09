import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" so the built bundle works both at a server root (the observe
// server) and under a GitHub Pages project subpath (the M6 showcase), with no
// rebuild. The dev server proxies API/SSE calls to the local observe server.
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/events": "http://127.0.0.1:8765",
    },
  },
});
