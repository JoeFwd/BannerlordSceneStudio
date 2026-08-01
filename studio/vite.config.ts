import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The FastAPI server (server/web.py) serves the built SPA from server/static/dist
// at the site root, so assets are referenced with absolute '/assets/...' paths.
// In dev, `npm run dev` proxies /api to the user's live studio server on :8770.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../server/static/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8770',
    },
  },
});
