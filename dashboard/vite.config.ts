import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" so the built bundle works both at a server root (the observe
// server) and under a GitHub Pages project subpath (the M6 showcase), with no
// rebuild. The dev server proxies API/SSE calls to the local observe server.
//
// Two HTML entries, one build:
//   index.html    -> the live observe console (what the observe server serves)
//   showcase.html -> the M6 GitHub Pages landing page (zero-backend replay)
// The showcase imports model.ts / types.ts / Timeline.tsx directly from the
// shared src/ tree, so there is exactly one replay engine — no divergence
// between the console and the landing page.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        console: resolve(__dirname, "index.html"),
        showcase: resolve(__dirname, "showcase.html"),
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/events": "http://127.0.0.1:8765",
    },
  },
});
