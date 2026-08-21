#!/usr/bin/env node

import { spawn, spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, resolve } from 'node:path';

const sleep = (milliseconds) => new Promise((done) => setTimeout(done, milliseconds));

function parseArgs(argv) {
  const values = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith('--')) continue;
    values[key.slice(2)] = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
  }
  return values;
}

function assertHttps(value, label) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error(`${label} 不是有效 URL`);
  }
  if (url.protocol !== 'https:') throw new Error(`${label} 必须使用 HTTPS`);
  return url.toString();
}

function writeJsonAtomic(path, data) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp.${process.pid}.${Date.now()}`;
  writeFileSync(temporary, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

function readManifest(path) {
  const manifest = JSON.parse(readFileSync(path, 'utf8'));
  if (manifest?.version !== 1 || !Array.isArray(manifest.items)) throw new Error('上传清单格式无效');
  const names = new Set();
  const ids = new Set();
  const items = manifest.items.map((item) => {
    const file = resolve(String(item.path ?? ''));
    const filename = String(item.filename || basename(file));
    if (!item.id || !existsSync(file) || !statSync(file).isFile()) throw new Error(`上传文件不存在：${file}`);
    if (ids.has(String(item.id))) throw new Error(`上传 ID 重复：${item.id}`);
    if (names.has(filename)) throw new Error(`上传文件名重复：${filename}`);
    ids.add(String(item.id));
    names.add(filename);
    return { id: String(item.id), path: file, filename };
  });
  return { items };
}

function chromeExecutable() {
  const configured = process.env.YIDA_CDN_CHROME_PATH;
  const candidates = [
    configured,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
  ].filter(Boolean);
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) throw new Error('未找到 Google Chrome，可通过 YIDA_CDN_CHROME_PATH 指定');
  return found;
}

async function readDevTools(profile) {
  const activePort = resolve(profile, 'DevToolsActivePort');
  if (!existsSync(activePort)) return null;
  const [portText] = readFileSync(activePort, 'utf8').trim().split(/\r?\n/);
  const port = Number(portText);
  if (!port) return null;
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/version`);
    if (!response.ok) return null;
    return { port, version: await response.json() };
  } catch {
    return null;
  }
}

async function ensureChrome(uploadPage) {
  const profile = process.env.YIDA_CDN_CHROME_PROFILE
    || resolve(homedir(), 'Library', 'Application Support', 'DingTalkDocsImageWorker');
  mkdirSync(profile, { recursive: true, mode: 0o700 });
  const existing = await readDevTools(profile);
  if (existing) return { ...existing, profile };

  const activePort = resolve(profile, 'DevToolsActivePort');
  if (existsSync(activePort)) rmSync(activePort, { force: true });
  const chromeArgs = [
    `--user-data-dir=${profile}`,
    '--remote-debugging-address=127.0.0.1',
    '--remote-debugging-port=0',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-default-apps',
  ];
  if (process.env.YIDA_CDN_HEADLESS === '1') chromeArgs.push('--headless=new');
  chromeArgs.push(uploadPage);
  const child = spawn(chromeExecutable(), chromeArgs, { detached: true, stdio: 'ignore' });
  child.unref();
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const endpoint = await readDevTools(profile);
    if (endpoint) return { ...endpoint, profile };
    await sleep(250);
  }
  throw new Error('Chrome 调试端口启动超时');
}

async function createPage(port, uploadPage) {
  const endpoint = `http://127.0.0.1:${port}/json/new?${encodeURIComponent(uploadPage)}`;
  const response = await fetch(endpoint, { method: 'PUT' });
  if (!response.ok) throw new Error(`无法创建 CDN 上传标签页：HTTP ${response.status}`);
  const target = await response.json();
  if (!target.webSocketDebuggerUrl) throw new Error('Chrome 没有返回页面调试地址');
  return target;
}

class Cdp {
  constructor(url) {
    this.nextId = 1;
    this.pending = new Map();
    this.socket = new WebSocket(url);
    this.ready = new Promise((resolveReady, rejectReady) => {
      this.socket.addEventListener('open', resolveReady, { once: true });
      this.socket.addEventListener('error', () => rejectReady(new Error('Chrome CDP 连接失败')), { once: true });
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (!message.id) return;
      const entry = this.pending.get(message.id);
      if (!entry) return;
      this.pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message));
      else entry.resolve(message.result);
    });
    this.socket.addEventListener('close', () => {
      for (const entry of this.pending.values()) entry.reject(new Error('Chrome CDP 页面连接已关闭'));
      this.pending.clear();
    });
  }

  async send(method, params = {}) {
    await this.ready;
    const id = this.nextId++;
    const result = new Promise((resolveResult, rejectResult) => this.pending.set(id, {
      resolve: resolveResult,
      reject: rejectResult,
    }));
    this.socket.send(JSON.stringify({ id, method, params }));
    return result;
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(cdp, expression) {
  const response = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text || '页面脚本执行失败');
  return response.result?.value;
}

async function waitForUploadPage(cdp) {
  const timeout = Math.max(10_000, Number(process.env.YIDA_CDN_AUTH_TIMEOUT_MS) || 5 * 60_000);
  const started = Date.now();
  let sawLogin = false;
  while (Date.now() - started < timeout) {
    const state = await evaluate(cdp, `(() => ({
      ready: Boolean(document.querySelector('input[type="file"]')),
      text: (document.body?.innerText || '').slice(0, 4000),
      url: location.href
    }))()`);
    if (state?.ready) return { ready: true, sawLogin };
    if (/登录|扫码|sign[ -]?in|login/i.test(`${state?.text || ''} ${state?.url || ''}`)) sawLogin = true;
    await sleep(1000);
  }
  return { ready: false, sawLogin };
}

function wirelessUrl(source) {
  const url = new URL(source);
  if (url.hostname === 'img.alicdn.com') url.hostname = 'gw.alicdn.com';
  url.pathname = url.pathname.replace(/_\d+x\d+\.jpg$/i, '');
  return url.toString();
}

async function pageRecords(cdp) {
  const records = await evaluate(cdp, `(() => Array.from(document.querySelectorAll('.image-card-container')).map((card) => {
    const image = card.querySelector('img.image-card-show');
    if (!image?.src) return null;
    var text = (card.innerText || '').slice(0, 800);
    var match = text.match(/([A-Za-z0-9_\-]+\.(png|jpg|jpeg|gif|webp|bmp|svg|apng))/i);
    var filename = match ? match[1] : '';
    return { filename, src: image.src, text };
  }).filter(Boolean).slice(0, 200))()`);
  return Array.isArray(records) ? records : [];
}

async function setFiles(cdp, paths) {
  const document = await cdp.send('DOM.getDocument', { depth: 2, pierce: true });
  const match = await cdp.send('DOM.querySelector', {
    nodeId: document.root.nodeId,
    selector: 'input[type="file"]',
  });
  if (!match.nodeId) throw new Error('上传页未找到文件选择控件');
  await cdp.send('DOM.setFileInputFiles', { nodeId: match.nodeId, files: paths });
}

async function waitForFilenames(cdp, filenames, previousSources) {
  const wanted = new Set(filenames);
  for (let attempt = 0; attempt < 180; attempt += 1) {
    const records = await pageRecords(cdp);
    const freshRecords = records.filter((record) => !previousSources.has(record.src));
    const direct = new Set(freshRecords.filter((record) => wanted.has(record.filename)).map((record) => record.filename));
    if (direct.size === wanted.size) return { records, freshRecords };
    await sleep(1000);
  }
  throw new Error(`等待上传完成超时：${filenames.join(', ')}`);
}

function clipboardText() {
  return spawnSync('pbpaste', [], { encoding: 'utf8' }).stdout?.trim() || '';
}

async function clickWireless(cdp, source) {
  const sentinel = `YIDA_CDN_PENDING_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  spawnSync('pbcopy', [], { input: sentinel, encoding: 'utf8' });
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const clicked = await evaluate(cdp, `(() => {
      const source = ${JSON.stringify(source)};
      const cards = Array.from(document.querySelectorAll('.image-card-container'));
      const card = cards.find((candidate) => candidate.querySelector('img.image-card-show')?.src === source);
      const button = card && Array.from(card.querySelectorAll('button,a,span')).find((node) => node.textContent?.trim() === '无线链接');
      if (!button) return false;
      button.click();
      return true;
    })()`);
    if (clicked) {
      for (let clipboardAttempt = 0; clipboardAttempt < 5; clipboardAttempt += 1) {
        await sleep(200);
        const copied = clipboardText();
        if (copied !== sentinel && /^https:\/\//.test(copied)) return copied;
      }
    }
    await sleep(250);
  }
  return '';
}

async function validateFirstWireless(cdp, record) {
  const expected = wirelessUrl(record.src);
  const copied = await clickWireless(cdp, record.src);
  if (!copied) return { useDomConversion: false, expected };
  return { useDomConversion: copied === expected, expected, copied };
}

async function verifyFirst(url) {
  try {
    const response = await fetch(url, { method: 'GET', headers: { Range: 'bytes=0-0' }, redirect: 'follow' });
    return response.ok && /^image\//i.test(response.headers.get('content-type') || '');
  } catch {
    return false;
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.manifest || !args.result || !args['upload-page']) {
    throw new Error('用法：cdn-browser-upload.mjs --manifest <json> --result <json> --upload-page <https-url> [--batch-size 20]');
  }
  const uploadPage = assertHttps(String(args['upload-page']), 'CDN 上传页');
  const manifest = readManifest(resolve(String(args.manifest)));
  const resultPath = resolve(String(args.result));
  const manifestIds = new Set(manifest.items.map((item) => item.id));
  let previousResult = {};
  if (existsSync(resultPath)) {
    try {
      previousResult = JSON.parse(readFileSync(resultPath, 'utf8'));
    } catch {}
  }
  const existingResults = new Map((Array.isArray(previousResult.items) ? previousResult.items : [])
    .filter((item) => manifestIds.has(item.id) && /^https:\/\//.test(item.cdnUrl || ''))
    .map((item) => [item.id, item.cdnUrl]));
  writeJsonAtomic(resultPath, {
    ok: false,
    inProgress: true,
    resumed: existingResults.size,
    validation: previousResult.validation ?? null,
    items: manifest.items.flatMap((item) => existingResults.has(item.id)
      ? [{ id: item.id, cdnUrl: existingResults.get(item.id) }]
      : []),
  });
  if (args['validate-manifest']) {
    writeJsonAtomic(resultPath, { ok: true, validated: manifest.items.length, items: [] });
    return;
  }

  const batchSize = Math.max(1, Math.min(20, Number(args['batch-size']) || 20));
  const endpoint = await ensureChrome(uploadPage);
  const target = await createPage(endpoint.port, uploadPage);
  const cdp = new Cdp(target.webSocketDebuggerUrl);
  try {
    await cdp.send('Runtime.enable');
    await cdp.send('DOM.enable');
    const readiness = await waitForUploadPage(cdp);
    if (!readiness.ready) {
      writeJsonAtomic(resultPath, {
        ok: false,
        authRequired: readiness.sawLogin,
        error: readiness.sawLogin ? 'CDN SSO 登录超时' : 'CDN 上传页加载超时',
        items: [],
      });
      process.exitCode = readiness.sawLogin ? 42 : 1;
      return;
    }

    let records = await pageRecords(cdp);
    const resolvedUrls = new Map(existingResults);
    let validation = previousResult.validation ?? null;
    const pendingAll = manifest.items.filter((item) => !resolvedUrls.has(item.id));
    const maxItems = args['max-items'] === undefined
      ? pendingAll.length
      : Math.max(1, Math.min(pendingAll.length, Number(args['max-items']) || 1));
    const pending = pendingAll.slice(0, maxItems);
    for (let index = 0; index < pending.length; index += batchSize) {
      const batch = pending.slice(index, index + batchSize);
      const previousSources = new Set(records.map((record) => record.src));
      await setFiles(cdp, batch.map((item) => item.path));
      const uploadState = await waitForFilenames(cdp, batch.map((item) => item.filename), previousSources);
      records = uploadState.records;
      const fresh = new Map(uploadState.freshRecords.map((record) => [record.filename, record]));
      const batchRecords = batch.flatMap((item) => fresh.has(item.filename)
        ? [{ item, record: fresh.get(item.filename) }]
        : []);
      if (batchRecords.length !== batch.length) {
        const found = new Set(batchRecords.map(({ item }) => item.filename));
        throw new Error(`上传后未找到本批新图片卡片：${batch.filter((item) => !found.has(item.filename)).map((item) => item.filename).join(', ')}`);
      }
      if (!validation) {
        validation = await validateFirstWireless(cdp, batchRecords[0].record);
      }
      for (const { item, record } of batchRecords) {
        const cdnUrl = validation.useDomConversion ? wirelessUrl(record.src) : await clickWireless(cdp, record.src);
        if (!cdnUrl) throw new Error(`未能读取无线链接：${item.filename}`);
        resolvedUrls.set(item.id, cdnUrl);
        writeJsonAtomic(resultPath, {
          ok: false,
          inProgress: true,
          completed: resolvedUrls.size,
          total: manifest.items.length,
          validation,
          items: manifest.items.flatMap((candidate) => resolvedUrls.has(candidate.id)
            ? [{ id: candidate.id, cdnUrl: resolvedUrls.get(candidate.id) }]
            : []),
        });
      }
      writeJsonAtomic(resultPath, {
        ok: false,
        inProgress: true,
        validation,
        items: manifest.items.flatMap((item) => resolvedUrls.has(item.id) ? [{ id: item.id, cdnUrl: resolvedUrls.get(item.id) }] : []),
      });
    }

    const items = manifest.items.map((item) => resolvedUrls.has(item.id)
      ? { id: item.id, cdnUrl: resolvedUrls.get(item.id) }
      : { id: item.id, error: '上传结果缺失' });
    const firstUrl = items.find((item) => item.cdnUrl)?.cdnUrl;
    if (!firstUrl || !await verifyFirst(firstUrl)) throw new Error('首个 CDN 无线链接不可访问或不是图片');
    const complete = items.every((item) => item.cdnUrl);
    writeJsonAtomic(resultPath, {
      ok: complete,
      inProgress: !complete,
      paused: !complete && pending.length < pendingAll.length,
      completed: resolvedUrls.size,
      total: manifest.items.length,
      validation,
      items,
    });
  } finally {
    cdp.close();
  }
}

main().catch((error) => {
  const args = parseArgs(process.argv.slice(2));
  if (args.result) {
    const resultPath = resolve(String(args.result));
    let previous = {};
    try {
      if (existsSync(resultPath)) previous = JSON.parse(readFileSync(resultPath, 'utf8'));
    } catch {}
    writeJsonAtomic(resultPath, {
      ...previous,
      ok: false,
      error: error instanceof Error ? error.message : String(error),
      items: Array.isArray(previous.items) ? previous.items : [],
    });
  }
  process.exitCode = 1;
});
