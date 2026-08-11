import path from 'node:path';

// Vite's official React plugin — adds JSX transform + Fast Refresh (hot
// reload that preserves component state across edits).
import react from '@vitejs/plugin-react';
// `defineConfig` is just an identity function that gives this object
// TypeScript autocomplete/type-checking; it doesn't transform anything.
import { defineConfig } from 'vite';

// Dev server proxy so the frontend can use same-origin paths and avoid CORS
// entirely in development: /api and /ws both forward to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirrors tsconfig.json's "paths" — tsc only checks types against that
    // mapping, it doesn't make Rollup resolve the alias at build time. This
    // is the piece that actually makes `@/foo` imports resolve when the app
    // runs (dev server or production build).
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // The port `npm run dev` serves on — matches what backend/api/main.py's
    // CORS config expects the frontend origin to be.
    port: 5173,
    proxy: {
      // Any fetch() to a same-origin "/api/..." path gets forwarded to the
      // real FastAPI backend on :8000. changeOrigin rewrites the Host
      // header so the backend sees the request as if it came from itself.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Same idea for the WebSocket chat connection ("/ws/chat/{id}"), with
      // ws:true telling Vite's proxy to upgrade the connection instead of
      // treating it as a plain HTTP request.
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
