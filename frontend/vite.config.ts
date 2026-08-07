import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// TODO(M1): dev server proxy so the frontend can use same-origin paths and
//   avoid CORS entirely in development:
//     /api -> http://localhost:8000
//     /ws  -> ws://localhost:8000  (ws: true — WebSocket proxying is opt-in)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
