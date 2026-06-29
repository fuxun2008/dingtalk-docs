import type { Connect } from 'vite';
import {
  handleNav,
  handleGetPage,
  handlePostPage,
  handleAlignment,
  handleProducts,
  handleDeletePage,
} from './routes';

export function createApiMiddleware(repoRoot: string): Connect.NextHandleFunction {
  return async (req, res, next) => {
    try {
      const url = new URL(req.url ?? '', 'http://localhost');
      const path = url.pathname;
      const method = req.method ?? 'GET';

      if (path === '/health' && method === 'GET') {
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ ok: true }));
        return;
      }
      if (path === '/products' && method === 'GET') return handleProducts(repoRoot, res);
      if (path === '/nav' && method === 'GET') return handleNav(repoRoot, req, res);
      if (path === '/alignment' && method === 'GET') return handleAlignment(repoRoot, req, res);
      if (path === '/page' && method === 'GET') return handleGetPage(repoRoot, req, res);
      if (path === '/page' && method === 'POST') return handlePostPage(repoRoot, req, res);
      if (path === '/page' && method === 'DELETE') return handleDeletePage(repoRoot, req, res);

      next();
    } catch (err) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ error: err instanceof Error ? err.message : 'unknown error' }));
    }
  };
}
