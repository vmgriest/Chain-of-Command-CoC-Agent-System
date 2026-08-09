import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Dev server proxy so the frontend can use same-origin paths and avoid CORS
// entirely in development: /api and /ws both forward to the backend on :8000.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirrors tsconfig.json's "paths" — tsc only checks types against that
    // mapping, it doesn't make Rollup resolve the alias at build time.
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
