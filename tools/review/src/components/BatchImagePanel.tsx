import { useEffect, useMemo, useRef, useState } from 'react';
import type {
  BatchApplyResult,
  BatchImageItem,
  BatchImageJob,
  BatchMappingInput,
} from '../shared/image-batch';
import type { ImageAutomationJob } from '../shared/image-automation';

const CDN_UPLOAD_STORAGE_KEY = 'review.cdnUploadPage';
const CDN_API_STORAGE_KEY = 'review.cdnUploadApi';
const MAX_RENDERED_ROWS = 500;
const CDN_UPLOAD_CONCURRENCY = 4;

interface BatchImagePanelProps {
  open: boolean;
  defaultScope: string;
  onClose: () => void;
  onApplied: (result: BatchApplyResult) => void;
}

type Filter = 'actionable' | 'all' | 'raster' | 'gif' | 'svg' | 'completed' | 'review';

const STATUS_LABEL: Record<BatchImageItem['status'], string> = {
  pending: '待处理',
  prepared: '已准备',
  generated: '已生成',
  mapped: '待回写',
  completed: '已完成',
  skipped: '已跳过',
  needs_review: '需复核',
};

function isActionable(item: BatchImageItem): boolean {
  return item.status !== 'completed' && item.status !== 'skipped' && item.mediaKind !== 'video';
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json() as T & { error?: string };
  if (!response.ok) throw new Error(data.error ?? `request failed: ${response.status}`);
  return data;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  const data = await response.json() as T & { error?: string };
  if (!response.ok) throw new Error(data.error ?? `request failed: ${response.status}`);
  return data;
}

const AUTOMATION_TERMINAL_STAGES = new Set<ImageAutomationJob['stage']>(['completed', 'failed', 'cancelled']);

function basename(pathOrUrl: string): string {
  const clean = pathOrUrl.split(/[?#]/, 1)[0];
  return clean.slice(clean.lastIndexOf('/') + 1);
}

function domainBoundary(hostname: string): string {
  const parts = hostname.toLowerCase().split('.').filter(Boolean);
  return parts.slice(-2).join('.');
}

function validateCdnConfiguration(uploadPage: string, uploadApi: string): URL {
  const page = new URL(uploadPage);
  const api = new URL(uploadApi);
  if (page.protocol !== 'https:' || api.protocol !== 'https:') throw new Error('CDN 页面和接口必须使用 HTTPS');
  if (!domainBoundary(page.hostname) || domainBoundary(page.hostname) !== domainBoundary(api.hostname)) {
    throw new Error('CDN 页面和上传接口必须属于同一组织域名');
  }
  return api;
}

async function uploadGeneratedItem(scope: string, item: BatchImageItem, uploadApi: URL): Promise<string> {
  const source = await fetch(`/api/image-batch/output?scope=${encodeURIComponent(scope)}&id=${encodeURIComponent(item.id)}`);
  if (!source.ok) {
    const detail = await source.json().catch(() => null) as { error?: string } | null;
    throw new Error(detail?.error ?? `无法读取生成文件：${item.id}`);
  }
  const blob = await source.blob();
  const filename = basename(item.localOutput ?? item.prepared?.outputPath ?? `${item.id}-en`);
  const form = new FormData();
  form.append('images', blob, filename);
  const endpoint = new URL(uploadApi);
  if (!endpoint.searchParams.has('uploadType')) endpoint.searchParams.set('uploadType', 'image');
  if (!endpoint.searchParams.has('compressType')) endpoint.searchParams.set('compressType', '0');
  if (!endpoint.searchParams.has('folder')) endpoint.searchParams.set('folder', '');
  if (!endpoint.searchParams.has('isPrivate')) endpoint.searchParams.set('isPrivate', '0');
  let response: Response;
  try {
    response = await fetch(endpoint, { method: 'POST', body: form, credentials: 'include' });
  } catch (cause) {
    if (cause instanceof TypeError) {
      throw new Error('上传请求已发出，但 CDN 的跨域响应不可读取；文件可能已经上传成功，请勿直接重试');
    }
    throw cause;
  }
  const raw = await response.text();
  let payload: { url?: unknown; data?: { url?: unknown }; error?: unknown } = {};
  try {
    payload = JSON.parse(raw) as typeof payload;
  } catch {
    throw new Error(response.ok ? 'CDN 返回了无法识别的结果' : `CDN 请求失败：${response.status}`);
  }
  const value = payload.url ?? payload.data?.url;
  if (!response.ok || typeof value !== 'string' || !/^https:\/\/\S+$/i.test(value)) {
    const detail = typeof payload.error === 'string' ? payload.error : `HTTP ${response.status}`;
    throw new Error(`CDN 上传失败：${detail}`);
  }
  return value;
}

function parseMapping(
  raw: string,
  selected: BatchImageItem[],
  allItems: BatchImageItem[],
): BatchMappingInput[] {
  const trimmed = raw.trim();
  if (!trimmed) return [];
  try {
    const json = JSON.parse(trimmed) as unknown;
    const list = Array.isArray(json) ? json : [json];
    return list.flatMap((entry) => {
      if (!entry || typeof entry !== 'object') return [];
      const value = entry as Record<string, unknown>;
      if (typeof value.id !== 'string') return [];
      return [{
        id: value.id,
        cdnUrl: typeof value.cdnUrl === 'string' ? value.cdnUrl : undefined,
        englishAlt: typeof value.englishAlt === 'string' ? value.englishAlt : undefined,
        localOutput: typeof value.localOutput === 'string' ? value.localOutput : undefined,
      }];
    });
  } catch {
    // Continue with line-oriented parsing.
  }

  const lines = trimmed.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const onlyUrls = lines.every((line) => /^https?:\/\/\S+$/i.test(line));
  if (onlyUrls) {
    if (lines.length !== selected.length) {
      throw new Error(`仅粘贴 URL 时，URL 数量（${lines.length}）必须等于已选任务数（${selected.length}）`);
    }
    return lines.map((cdnUrl, index) => ({ id: selected[index].id, cdnUrl }));
  }

  const byId = new Map(allItems.map((item) => [item.id, item]));
  const byFilename = new Map<string, BatchImageItem>();
  for (const item of allItems) {
    if (item.localOutput) byFilename.set(basename(item.localOutput), item);
    if (item.prepared?.outputPath) byFilename.set(basename(item.prepared.outputPath), item);
  }
  return lines.map((line) => {
    const parts = line.includes('\t') ? line.split('\t') : line.split(',');
    const key = parts[0]?.trim();
    const item = byId.get(key) ?? byFilename.get(key);
    if (!item) throw new Error(`无法匹配任务或文件名：${key}`);
    return {
      id: item.id,
      cdnUrl: parts[1]?.trim(),
      englishAlt: parts.slice(2).join(line.includes('\t') ? '\t' : ',').trim() || undefined,
    };
  });
}

function downloadJob(job: BatchImageJob, selected: BatchImageItem[]): void {
  const payload = {
    version: job.version,
    scope: job.scope,
    sourceLang: job.sourceLang,
    targetLang: job.targetLang,
    items: selected,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${job.key}-tasks.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function BatchImagePanel({ open, defaultScope, onClose, onApplied }: BatchImagePanelProps) {
  const [scope, setScope] = useState(defaultScope);
  const [job, setJob] = useState<BatchImageJob | null>(null);
  const [automationJob, setAutomationJob] = useState<ImageAutomationJob | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<Filter>('actionable');
  const [mapping, setMapping] = useState('');
  const [uploadPage, setUploadPage] = useState('');
  const [uploadApi, setUploadApi] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const uploadPageRef = useRef<HTMLInputElement>(null);
  const uploadApiRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setScope(defaultScope);
    setUploadPage(window.localStorage.getItem(CDN_UPLOAD_STORAGE_KEY) ?? '');
    setUploadApi(window.localStorage.getItem(CDN_API_STORAGE_KEY) ?? '');
    setError(null);
    setMessage(null);
  }, [open, defaultScope]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !scope.trim()) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getJson<ImageAutomationJob>(`/image-automation/status?scope=${encodeURIComponent(scope.trim())}`);
        if (stopped) return;
        setAutomationJob(next);
        if (!AUTOMATION_TERMINAL_STAGES.has(next.stage)) timer = window.setTimeout(poll, 1500);
      } catch {
        // A missing state file simply means this scope has not run automatically yet.
        if (!stopped) timer = window.setTimeout(poll, 2500);
      }
    };
    void poll();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [open, scope, automationJob?.id]);

  const filtered = useMemo(() => {
    if (!job) return [];
    switch (filter) {
      case 'all': return job.items;
      case 'raster': return job.items.filter((item) => item.mediaKind === 'raster');
      case 'gif': return job.items.filter((item) => item.mediaKind === 'gif');
      case 'svg': return job.items.filter((item) => item.mediaKind === 'svg');
      case 'completed': return job.items.filter((item) => item.status === 'completed');
      case 'review': return job.items.filter((item) => item.status === 'needs_review' || item.privacyReview);
      default: return job.items.filter(isActionable);
    }
  }, [filter, job]);

  const selected = useMemo(
    () => job?.items.filter((item) => selectedIds.has(item.id)) ?? [],
    [job, selectedIds],
  );

  if (!open) return null;

  const run = async (label: string, action: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    setMessage(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : `${label}失败`);
    } finally {
      setBusy(null);
    }
  };

  const scan = () => run('扫描', async () => {
    const next = await postJson<BatchImageJob>('/image-batch/scan', { scope });
    setJob(next);
    setSelectedIds(new Set(next.items.filter(isActionable).map((item) => item.id)));
    setMessage(`扫描完成：${next.stats.total} 个媒体，${next.stats.completed} 个已完成，${next.stats.duplicates} 个重复引用。`);
  });

  const startAutomation = () => run('启动全自动任务', async () => {
    if (!scope.trim()) throw new Error('请填写处理范围，例如 yida/intro 或 yida');
    if (!uploadPage.trim()) {
      uploadPageRef.current?.focus();
      throw new Error('请先填写 CDN 上传页；地址只保存在本机浏览器并在本次任务中使用。');
    }
    const page = new URL(uploadPage.trim());
    if (page.protocol !== 'https:') throw new Error('CDN 上传页必须使用 HTTPS');
    const next = await postJson<ImageAutomationJob>('/image-automation/start', {
      scope: scope.trim(),
      uploadPage: page.toString(),
    });
    setAutomationJob(next);
    setMessage('后台任务已启动；可以关闭面板，重新打开后会自动恢复进度。');
  });

  const cancelAutomation = () => run('取消后台任务', async () => {
    if (!automationJob) throw new Error('当前没有后台任务');
    const next = await postJson<ImageAutomationJob>('/image-automation/cancel', { scope: automationJob.scope });
    setAutomationJob(next);
    setMessage('已请求取消；当前图片处理结束后停止，已完成结果会保留。');
  });

  const prepare = () => run('准备资源', async () => {
    if (!job || selected.length === 0) throw new Error('请先选择任务');
    const next = await postJson<BatchImageJob>('/image-batch/prepare', { scope: job.scope, ids: selected.map((item) => item.id) });
    setJob(next);
    setMessage(`已准备 ${selected.length} 个任务；GIF 已抽取代表帧，SVG 已提取文本节点。`);
  });

  const copyTasks = () => run('复制任务', async () => {
    if (selected.length === 0) throw new Error('请先选择任务');
    const text = selected.map((item, index) => [
      `## TASK ${index + 1}/${selected.length} · ${item.id}`,
      `slug: ${item.slug}`,
      `kind: ${item.mediaKind}`,
      item.prepared?.sourcePath ? `local_source: ${item.prepared.sourcePath}` : '',
      item.prepared?.outputPath ? `expected_output: ${item.prepared.outputPath}` : '',
      item.prepared?.framePaths?.length ? `frames: ${item.prepared.framePaths.join(', ')}` : '',
      item.prepared?.svgTexts?.length ? `svg_texts: ${JSON.stringify(item.prepared.svgTexts)}` : '',
      item.prompt,
    ].filter(Boolean).join('\n')).join('\n\n');
    await navigator.clipboard.writeText(text);
    setMessage(`已复制 ${selected.length} 个任务为一个批次，可直接发送给 Codex。`);
  });

  const saveMapping = () => run('导入映射', async () => {
    if (!job) throw new Error('请先扫描');
    const updates = parseMapping(mapping, selected, job.items);
    if (updates.length === 0) throw new Error('没有识别到映射');
    const next = await postJson<BatchImageJob>('/image-batch/update', { scope: job.scope, updates });
    setJob(next);
    setMapping('');
    setMessage(`已保存 ${updates.length} 条 CDN 映射，支持关闭页面后继续。`);
  });

  const apply = (dryRun: boolean) => run(dryRun ? '预检回写' : '回写 MDX', async () => {
    if (!job) throw new Error('请先扫描');
    const ready = selected.filter((item) => item.cdnUrl);
    if (ready.length === 0) throw new Error('已选任务中没有 CDN 地址');
    const result = await postJson<BatchApplyResult>('/image-batch/apply', {
      scope: job.scope,
      ids: ready.map((item) => item.id),
      dryRun,
    });
    if (dryRun) {
      setMessage(`预检通过：将回写 ${result.appliedIds.length} 个媒体，影响 ${result.changedFiles.length} 个英文 MDX；磁盘未修改。`);
      return;
    }
    const next = await postJson<BatchImageJob>('/image-batch/scan', { scope: job.scope });
    setJob(next);
    setMessage(`已回写 ${result.appliedIds.length} 个媒体，修改 ${result.changedFiles.length} 个英文 MDX。`);
    onApplied(result);
  });

  const autoFinalize = () => run('一键上传并回写', async () => {
    if (!job) throw new Error('请先扫描');
    if (selected.length === 0) throw new Error('请先选择任务');
    if (!uploadPage.trim()) {
      uploadPageRef.current?.focus();
      throw new Error('请先填写 CDN 上传页；该配置只保存在本机浏览器。');
    }
    if (!uploadApi.trim()) {
      uploadApiRef.current?.focus();
      throw new Error('请先填写 CDN 上传接口；按钮此前因缺少该配置而被静默禁用。');
    }
    const endpoint = validateCdnConfiguration(uploadPage, uploadApi);
    const safe = selected.filter((item) => (
      item.status !== 'needs_review'
      && item.mediaKind !== 'video'
      && !item.privacyFindings?.length
      && (item.cdnUrl || item.localOutput || item.prepared?.outputPath)
    ));
    const blocked = selected.length - safe.length;
    if (safe.length === 0) throw new Error('所选任务均未生成或仍需复核，不能自动上传');
    const pendingUploads = safe.filter((item) => !item.cdnUrl);
    const uploaded: BatchMappingInput[] = [];
    const failures: Array<{ id: string; error: string }> = [];
    let cursor = 0;
    let finished = 0;
    const worker = async () => {
      while (cursor < pendingUploads.length) {
        const item = pendingUploads[cursor++];
        try {
          const cdnUrl = await uploadGeneratedItem(job.scope, item, endpoint);
          uploaded.push({ id: item.id, cdnUrl });
        } catch (cause) {
          failures.push({ id: item.id, error: cause instanceof Error ? cause.message : '上传失败' });
        } finally {
          finished += 1;
          setMessage(`正在上传 CDN：${finished}/${pendingUploads.length}`);
        }
      }
    };
    await Promise.all(Array.from(
      { length: Math.min(CDN_UPLOAD_CONCURRENCY, pendingUploads.length) },
      () => worker(),
    ));
    let next = job;
    if (uploaded.length) {
      next = await postJson<BatchImageJob>('/image-batch/update', { scope: job.scope, updates: uploaded });
      setJob(next);
    }
    if (failures.length) {
      const first = failures[0];
      const outcomeUnknown = failures.some((entry) => entry.error.includes('跨域响应不可读取'));
      throw new Error(outcomeUnknown
        ? `已确认映射 ${uploaded.length} 个，另有 ${failures.length} 个上传结果未知；首个 ${first.id}：${first.error}。请先在上传页按任务文件名恢复链接，避免重复上传。`
        : `已上传 ${uploaded.length} 个，失败 ${failures.length} 个；首个失败 ${first.id}：${first.error}。成功映射已保存，可修复失败原因后重试。`);
    }
    const readyIds = safe.map((item) => item.id);
    const preview = await postJson<BatchApplyResult>('/image-batch/apply', {
      scope: job.scope,
      ids: readyIds,
      dryRun: true,
    });
    if (preview.skipped.length) {
      throw new Error(`回写预检未通过：${preview.skipped.map((entry) => `${entry.id} ${entry.reason}`).join('；')}`);
    }
    const result = await postJson<BatchApplyResult>('/image-batch/apply', {
      scope: job.scope,
      ids: readyIds,
      dryRun: false,
    });
    next = await postJson<BatchImageJob>('/image-batch/scan', { scope: job.scope });
    setJob(next);
    setMessage(`全流程完成：上传 ${uploaded.length} 个、回写 ${result.appliedIds.length} 个媒体、修改 ${result.changedFiles.length} 个 MDX${blocked ? `；另有 ${blocked} 个需复核任务未处理` : ''}。`);
    onApplied(result);
  });

  const rememberUploadPage = (value: string) => {
    setUploadPage(value);
    if (value.trim()) window.localStorage.setItem(CDN_UPLOAD_STORAGE_KEY, value.trim());
    else window.localStorage.removeItem(CDN_UPLOAD_STORAGE_KEY);
  };

  const rememberUploadApi = (value: string) => {
    setUploadApi(value);
    if (value.trim()) window.localStorage.setItem(CDN_API_STORAGE_KEY, value.trim());
    else window.localStorage.removeItem(CDN_API_STORAGE_KEY);
  };

  const toggle = (id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="dialog-mask batch-image-mask" onClick={onClose}>
      <section className="batch-image-panel" role="dialog" onClick={(event) => event.stopPropagation()}>
        <header className="batch-image-header">
          <div>
            <h2>英文图片批处理 V3</h2>
            <p>扫描 → 脱敏生成 → 浏览器登录态批量上传 → 自动映射 → 预检并回写 MDX</p>
          </div>
          <button type="button" className="btn btn-ghost" onClick={onClose}>关闭</button>
        </header>

        <div className="batch-image-toolbar">
          <label>
            <span>处理范围</span>
            <input value={scope} onChange={(event) => setScope(event.target.value)} placeholder="yida/intro" />
          </label>
          <label>
            <span>CDN 上传页（本机保存）</span>
            <input ref={uploadPageRef} value={uploadPage} onChange={(event) => rememberUploadPage(event.target.value)} placeholder="https://..." />
          </label>
          <button type="button" className="btn btn-primary" onClick={scan} disabled={!!busy}>扫描/恢复</button>
          <button type="button" className="btn btn-primary" onClick={startAutomation} disabled={!!busy}>全自动处理普通截图</button>
          <button type="button" className="btn btn-ghost" onClick={prepare} disabled={!!busy || selected.length === 0}>准备资源</button>
          <button type="button" className="btn btn-ghost" onClick={copyTasks} disabled={!!busy || selected.length === 0}>复制批量生成任务</button>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => job && downloadJob(job, selected.length ? selected : job.items)}
            disabled={!job}
          >
            导出 JSON
          </button>
        </div>

        {automationJob && (
          <div className={`batch-automation-status batch-automation-${automationJob.stage}`}>
            <div>
              <strong>{automationJob.stage === 'completed' ? '全自动任务已完成' : '全自动后台任务'}</strong>
              <span>{automationJob.message}</span>
            </div>
            <div className="batch-automation-metrics">
              <span>发现 {automationJob.stats.discovered}</span>
              <span>普通截图 {automationJob.stats.eligible}</span>
              <span>已生成 {automationJob.stats.generated}</span>
              <span>已验收 {automationJob.stats.qualityPassed}</span>
              <span>已回写 {automationJob.stats.applied}</span>
              <span>延后 {automationJob.stats.deferred}</span>
              <span>失败 {automationJob.stats.failed}</span>
            </div>
            {!AUTOMATION_TERMINAL_STAGES.has(automationJob.stage) && (
              <button type="button" className="btn btn-ghost" onClick={cancelAutomation} disabled={!!busy}>取消任务</button>
            )}
          </div>
        )}

        {job && (
          <div className="batch-image-stats">
            <span>共 {job.stats.total}</span>
            <span>图片 {job.stats.byKind.raster}</span>
            <span>GIF {job.stats.byKind.gif}</span>
            <span>SVG {job.stats.byKind.svg}</span>
            <span>视频 {job.stats.byKind.video}</span>
            <span>已准备 {job.stats.prepared}</span>
            <span>已生成 {job.stats.generated}</span>
            <span>已完成 {job.stats.completed}</span>
            <span>待回写 {job.stats.mapped}</span>
            <span>需复核 {job.stats.needsReview}</span>
            <span>重复 {job.stats.duplicates}</span>
          </div>
        )}

        {(error || message || busy) && (
          <div className={`batch-image-message${error ? ' is-error' : ''}`}>
            {error ?? message ?? (busy ? `${busy}中…` : null)}
          </div>
        )}

        {job && (
          <>
            <div className="batch-image-filters">
              {([
                ['actionable', '待处理'], ['all', '全部'], ['raster', '静态图'], ['gif', 'GIF'],
                ['svg', 'SVG'], ['review', '隐私/复核'], ['completed', '已完成'],
              ] as Array<[Filter, string]>).map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={filter === value ? 'is-active' : ''}
                  onClick={() => setFilter(value)}
                >
                  {label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setSelectedIds(new Set(filtered.map((item) => item.id)))}
              >
                全选筛选结果
              </button>
              <button type="button" onClick={() => setSelectedIds(new Set())}>清空选择</button>
              <span>已选 {selected.length}</span>
            </div>

            <div className="batch-image-table-wrap">
              <table className="batch-image-table">
                <thead>
                  <tr><th></th><th>状态</th><th>类型</th><th>文档</th><th>源媒体</th><th>风险/准备结果</th></tr>
                </thead>
                <tbody>
                  {filtered.slice(0, MAX_RENDERED_ROWS).map((item) => (
                    <tr key={item.id} className={selectedIds.has(item.id) ? 'is-selected' : ''}>
                      <td><input type="checkbox" checked={selectedIds.has(item.id)} onChange={() => toggle(item.id)} /></td>
                      <td><span className={`batch-status batch-status-${item.status}`}>{STATUS_LABEL[item.status]}</span></td>
                      <td>{item.mediaKind.toUpperCase()}{item.duplicateOf ? ' · 复用' : ''}</td>
                      <td><code>{item.slug}</code></td>
                      <td>
                        <a href={item.sourceUrl} target="_blank" rel="noreferrer">{basename(item.sourceUrl)}</a>
                        {item.cdnUrl && <small>CDN 已映射</small>}
                      </td>
                      <td>
                        {item.privacyReview && <span className="batch-risk">隐私检查</span>}
                        {item.complexityReasons.map((reason) => <span className="batch-risk" key={reason}>{reason}</span>)}
                        {item.privacyFindings?.map((finding) => <span className="batch-risk" key={finding}>{finding}</span>)}
                        {item.prepared?.framePaths?.length ? <small>{item.prepared.framePaths.length} 帧</small> : null}
                        {item.prepared?.svgTexts?.length ? <small>{item.prepared.svgTexts.length} 个文本节点</small> : null}
                        {item.note && <small className="batch-note">{item.note}</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length > MAX_RENDERED_ROWS && <p className="batch-image-limit">仅渲染前 {MAX_RENDERED_ROWS} 条，筛选和全选仍作用于全部 {filtered.length} 条。</p>}
            </div>

            <div className="batch-image-cdn">
              <div className="batch-image-cdn-column">
                <h3>全自动任务配置</h3>
                <p>后台使用本机专用 Chrome 登录态批量上传；不会读取或导出 Cookie，也不会把登录态写入仓库。</p>
                <label>
                  <span>旧版直连接口（仅保留为手动恢复通道）</span>
                  <input ref={uploadApiRef} value={uploadApi} onChange={(event) => rememberUploadApi(event.target.value)} placeholder="https://.../image/upload" />
                </label>
                <p>
                  当前已选 {selected.length} 个；点击后会自动跳过需复核、视频及尚未生成的任务，并明确报告原因。
                </p>
                <div className="batch-inline-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!!busy}
                    onClick={autoFinalize}
                  >一键上传、映射并回写 MDX</button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={!/^https?:\/\//i.test(uploadPage)}
                    onClick={() => window.open(uploadPage, '_blank', 'noopener,noreferrer')}
                  >打开上传页</button>
                </div>
              </div>
              <div className="batch-image-cdn-column">
                <h3>手动恢复通道</h3>
                <p>仅在自动上传不可用时使用。支持 URL 列表、<code>任务ID,URL,alt</code>、<code>文件名,URL</code> 或 JSON。</p>
                <textarea value={mapping} onChange={(event) => setMapping(event.target.value)} placeholder="https://...\nhttps://..." />
                <div className="batch-inline-actions">
                  <button type="button" className="btn btn-ghost" onClick={saveMapping} disabled={!!busy || !mapping.trim()}>保存映射</button>
                  <button type="button" className="btn btn-ghost" onClick={() => apply(true)} disabled={!!busy || selected.every((item) => !item.cdnUrl)}>预检回写</button>
                  <button type="button" className="btn btn-primary" onClick={() => apply(false)} disabled={!!busy || selected.every((item) => !item.cdnUrl)}>批量回写 MDX</button>
                </div>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
