
import { readFileSync, existsSync, writeFileSync, renameSync, mkdirSync, statSync } from 'node:fs';
import { resolve, dirname, basename } from 'node:path';
import { homedir } from 'node:os';

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

function writeJsonAtomic(path, data) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.tmp.${process.pid}.${Date.now()}`;
  writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  renameSync(tmp, path);
}

function parseArgs(argv) {
  const values = {};
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (!key.startsWith('--')) continue;
    values[key.slice(2)] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
  }
  return values;
}

async function getCookieHeader(port) {
  const resp = await fetch(`http://127.0.0.1:${port}/json/list`);
  const targets = await resp.json();
  const target = targets.find((t) => t.url && t.url.includes('pic/upload') && t.type === 'page');
  if (!target) throw new Error('未找到上传页面标签页');

  const wsUrl = target.webSocketDebuggerUrl;
  const cdp = { nextId: 1, pending: new Map(), socket: new WebSocket(wsUrl) };
  cdp.ready = new Promise((resolveReady, rejectReady) => {
    cdp.socket.addEventListener('open', resolveReady, { once: true });
    cdp.socket.addEventListener('error', () => rejectReady(new Error('CDP 连接失败')), { once: true });
  });
  cdp.socket.addEventListener('message', (event) => {
    const msg = JSON.parse(String(event.data));
    if (msg.id) {
      const entry = cdp.pending.get(msg.id);
      if (entry) {
        cdp.pending.delete(msg.id);
        msg.error ? entry.reject(new Error(msg.error.message)) : entry.resolve(msg.result);
      }
    }
  });
  cdp.send = async (method, params = {}) => {
    await cdp.ready;
    const id = cdp.nextId++;
    const result = new Promise((r, j) => cdp.pending.set(id, { resolve: r, reject: j }));
    cdp.socket.send(JSON.stringify({ id, method, params }));
    return result;
  };
  cdp.close = () => cdp.socket.close();

  await cdp.send('Runtime.enable');
  const cookiesResult = await cdp.send('Network.getCookies', {
    urls: ['https://tps.alibaba-inc.com', 'https://content.alibaba-inc.com'],
  });
  const cookies = cookiesResult.cookies || [];
  const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join('; ');
  cdp.close();
  return cookieHeader;
}

function buildMultipartBody(filename, fileBuffer, contentType = 'image/png') {
  const boundary = '----FormBoundary' + Math.random().toString(36).slice(2) + Date.now().toString(36);
  const parts = [
    `--${boundary}\r\n`,
    `Content-Disposition: form-data; name="images"; filename="${filename}"\r\n`,
    `Content-Type: ${contentType}\r\n\r\n`,
  ];
  const header = parts.join('');
  const footer = `\r\n--${boundary}--\r\n`;
  const body = new Uint8Array(header.length + fileBuffer.length + footer.length);
  body.set(new TextEncoder().encode(header), 0);
  body.set(fileBuffer, header.length);
  body.set(new TextEncoder().encode(footer), header.length + fileBuffer.length);
  return { body, contentType: `multipart/form-data; boundary=${boundary}` };
}

function wirelessUrl(url) {
  const u = new URL(url);
  if (u.hostname === 'img.alicdn.com') u.hostname = 'gw.alicdn.com';
  u.pathname = u.pathname.replace(/_\d+x\d+\.jpg$/i, '');
  return u.toString();
}

async function uploadOne(cookieHeader, uploadUrl, item, retries = 3) {
  const fileBuffer = readFileSync(item.path);
  const contentType = item.path.endsWith('.jpg') || item.path.endsWith('.jpeg') ? 'image/jpeg' : 'image/png';
  const { body, contentType: headerContentType } = buildMultipartBody(item.filename, fileBuffer, contentType);

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const resp = await fetch(uploadUrl, {
        method: 'POST',
        headers: {
          'Content-Type': headerContentType,
          'Cookie': cookieHeader,
          'Referer': 'https://content.alibaba-inc.com/work/internal-media-management/pic/upload?iframe=3',
          'Accept': '*/*',
        },
        body,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const cdnUrl = data.h5url || wirelessUrl(data.url);
      if (!cdnUrl) throw new Error('响应中没有 CDN URL');
      return { id: item.id, cdnUrl };
    } catch (err) {
      if (attempt === retries) return { id: item.id, error: err.message };
      await sleep(1000 * attempt);
    }
  }
}

async function runPool(items, concurrency, fn) {
  let index = 0;
  let completed = 0;
  const results = [];
  const workers = Array.from({ length: concurrency }, async () => {
    while (index < items.length) {
      const item = items[index++];
      try {
        const result = await fn(item);
        results.push(result);
      } catch (err) {
        results.push({ id: item.id, error: err.message });
      }
      completed++;
      if (completed % 50 === 0 || completed === items.length) {
        const ok = results.filter((r) => r.cdnUrl).length;
        console.log(`进度: ${completed}/${items.length} (成功 ${ok})`);
      }
    }
  });
  await Promise.all(workers);
  return results;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.manifest || !args.result) {
    throw new Error('用法: cdn-api-upload.mjs --manifest <json> --result <json> [--concurrency 8]');
  }

  const manifestPath = resolve(String(args.manifest));
  const resultPath = resolve(String(args.result));
  const concurrency = Math.max(1, Math.min(16, Number(args.concurrency) || 8));
  const uploadUrl = 'https://tps.alibaba-inc.com/internal-management/image/upload?uploadType=image&compressType=0&folder=&isPrivate=false&workId=224019&workName=' + encodeURIComponent('萤火');

  // 读取清单
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  if (manifest?.version !== 1 || !Array.isArray(manifest.items)) throw new Error('清单格式无效');

  // 断点续传：检查已有结果
  let existingResults = {};
  if (existsSync(resultPath)) {
    try {
      const prev = JSON.parse(readFileSync(resultPath, 'utf8'));
      for (const item of prev.items || []) {
        if (item.cdnUrl) existingResults[item.id] = item.cdnUrl;
      }
      console.log(`断点续传: 已有 ${Object.keys(existingResults).length} 个 CDN URL`);
    } catch {}
  }

  const pending = manifest.items.filter((item) => !existingResults[item.id]);
  console.log(`总清单: ${manifest.items.length}, 待上传: ${pending.length}, 并发: ${concurrency}`);

  // 获取 Chrome 端口
  const profile = resolve(homedir(), 'Library', 'Application Support', 'DingTalkDocsImageWorker');
  const activePort = resolve(profile, 'DevToolsActivePort');
  if (!existsSync(activePort)) throw new Error('Chrome 未启动，DevToolsActivePort 不存在');
  const port = Number(readFileSync(activePort, 'utf8').trim().split(/\r?\n/)[0]);

  // 获取 Cookie
  console.log('正在从 Chrome 获取认证 Cookie...');
  const cookieHeader = await getCookieHeader(port);
  console.log('Cookie 获取成功，开始上传...');

  // 初始化结果文件
  const allResults = new Map(Object.entries(existingResults).map(([id, cdnUrl]) => [id, cdnUrl]));
  writeJsonAtomic(resultPath, {
    ok: false,
    inProgress: true,
    total: manifest.items.length,
    completed: allResults.size,
    items: Array.from(allResults.entries()).map(([id, cdnUrl]) => ({ id, cdnUrl })),
  });

  // 分批处理（每批 concurrency * 5 个，中间写入结果）
  const batchSize = concurrency * 5;
  for (let i = 0; i < pending.length; i += batchSize) {
    const batch = pending.slice(i, i + batchSize);
    const results = await runPool(batch, concurrency, (item) => uploadOne(cookieHeader, uploadUrl, item));

    for (const result of results) {
      if (result.cdnUrl) allResults.set(result.id, result.cdnUrl);
      else console.log(`  失败: ${result.id} - ${result.error}`);
    }

    // 每批完成写入结果
    writeJsonAtomic(resultPath, {
      ok: false,
      inProgress: true,
      total: manifest.items.length,
      completed: allResults.size,
      items: Array.from(allResults.entries()).map(([id, cdnUrl]) => ({ id, cdnUrl })),
    });
  }

  // 最终结果
  const ok = allResults.size === manifest.items.length;
  writeJsonAtomic(resultPath, {
    ok,
    total: manifest.items.length,
    completed: allResults.size,
    failed: manifest.items.length - allResults.size,
    items: manifest.items.map((item) => {
      const cdnUrl = allResults.get(item.id);
      return cdnUrl ? { id: item.id, cdnUrl } : { id: item.id, error: 'upload failed' };
    }),
  });

  console.log(`\n完成! 成功 ${allResults.size}/${manifest.items.length}, 失败 ${manifest.items.length - allResults.size}`);
}

main().catch((err) => {
  console.error('致命错误:', err.message);
  process.exitCode = 1;
});
