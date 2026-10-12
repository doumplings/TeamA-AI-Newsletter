import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In live mode the browser calls /api/... and Vite forwards it to the FastAPI
// server. Same origin means the session cookie just works, with no CORS setup.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
