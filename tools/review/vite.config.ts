import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import fs from 'node:fs';
import { createApiMiddleware } from './src/server/middleware';

const repoRoot = path.resolve(__dirname, '../..');

const MIME: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
};

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'review-api',
      configureServer(server) {
        server.middlewares.use('/api', createApiMiddleware(repoRoot));
      },
    },
    {
      name: 'review-repo-assets',
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const url = req.url ?? '';
          if (!url.includes('/images/')) return next();
          const decoded = decodeURIComponent(url.split('?')[0]);
          const filePath = path.resolve(repoRoot, '.' + decoded);
          if (!filePath.startsWith(repoRoot + path.sep)) return next();
          if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) return next();
          const ext = path.extname(filePath).toLowerCase();
          res.setHeader('Content-Type', MIME[ext] ?? 'application/octet-stream');
          res.setHeader('Cache-Control', 'public, max-age=3600');
          fs.createReadStream(filePath).pipe(res);
        });
      },
    },
  ],
  server: {
    port: 5173,
    strictPort: true,
    open: true,
  },
});
