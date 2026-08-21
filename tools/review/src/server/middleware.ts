import type { Connect } from 'vite';
import {
  handleNav,
  handleGetPage,
  handlePostPage,
  handleAlignment,
  handleProducts,
  handleDeletePage,
  handleImageBatchApply,
  handleImageBatchOutput,
  handleImageBatchPreflight,
  handleImageBatchPrepare,
  handleImageBatchScan,
  handleImageBatchUpdate,
  handleImageAutomationCancel,
  handleImageAutomationImportMappings,
  handleImageAutomationStart,
  handleImageAutomationStatus,
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
      if (path === '/image-batch/scan' && method === 'POST') return handleImageBatchScan(repoRoot, req, res);
      if (path === '/image-batch/output' && method === 'GET') return handleImageBatchOutput(repoRoot, req, res);
      if (path === '/image-batch/preflight' && method === 'POST') return handleImageBatchPreflight(repoRoot, req, res);
      if (path === '/image-batch/update' && method === 'POST') return handleImageBatchUpdate(repoRoot, req, res);
      if (path === '/image-batch/prepare' && method === 'POST') return handleImageBatchPrepare(repoRoot, req, res);
      if (path === '/image-batch/apply' && method === 'POST') return handleImageBatchApply(repoRoot, req, res);
      if (path === '/image-automation/start' && method === 'POST') return handleImageAutomationStart(repoRoot, req, res);
      if (path === '/image-automation/status' && method === 'GET') return handleImageAutomationStatus(repoRoot, req, res);
      if (path === '/image-automation/cancel' && method === 'POST') return handleImageAutomationCancel(repoRoot, req, res);
      if (path === '/image-automation/import-mappings' && method === 'POST') return handleImageAutomationImportMappings(repoRoot, req, res);

      next();
    } catch (err) {
      res.statusCode = 500;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ error: err instanceof Error ? err.message : 'unknown error' }));
    }
  };
}
