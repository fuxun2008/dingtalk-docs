import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import { createApiMiddleware } from './src/server/middleware';

const repoRoot = path.resolve(__dirname, '../..');

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'review-api',
      configureServer(server) {
        server.middlewares.use('/api', createApiMiddleware(repoRoot));
      },
    },
  ],
  server: {
    port: 5173,
    strictPort: true,
    open: true,
  },
});
