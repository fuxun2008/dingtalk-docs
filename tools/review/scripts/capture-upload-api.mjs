import { readFileSync, existsSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { homedir } from 'node:os';

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

const profile = resolve(homedir(), 'Library', 'Application Support', 'DingTalkDocsImageWorker');
const activePortPath = resolve(profile, 'DevToolsActivePort');
if (!existsSync(activePortPath)) {
  console.error('DevToolsActivePort not found');
  process.exit(1);
}
const port = Number(readFileSync(activePortPath, 'utf8').trim().split(/\r?\n/)[0]);
console.log('Chrome DevTools port:', port);

// 获取上传页面 target
const resp = await fetch(`http://127.0.0.1:${port}/json/list`);
const targets = await resp.json();
// 找一个上传页面的 target
const uploadTarget = targets.find((t) => t.url && t.url.includes('pic/upload'));
if (!uploadTarget) {
  console.error('No upload page target found');
  console.log('Available targets:', targets.map((t) => t.url?.slice(0, 80)));
  process.exit(1);
}
console.log('Upload target:', uploadTarget.url.slice(0, 100));

// 创建新标签页用于捕获
const newTargetResp = await fetch(`http://127.0.0.1:${port}/json/new?https://content.alibaba-inc.com/work/internal-media-management/pic/upload?iframe=3`, { method: 'PUT' });
const newTarget = await newTargetResp.json();
console.log('New target:', newTarget.url?.slice(0, 100));

class Cdp {
  constructor(url) {
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
    this.socket = new WebSocket(url);
    this.ready = new Promise((resolveReady, rejectReady) => {
      this.socket.addEventListener('open', resolveReady, { once: true });
      this.socket.addEventListener('error', () => rejectReady(new Error('CDP connect failed')), { once: true });
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data));
      if (message.id) {
        const entry = this.pending.get(message.id);
        if (entry) {
          this.pending.delete(message.id);
          if (message.error) entry.reject(new Error(message.error.message));
          else entry.resolve(message.result);
        }
      } else if (message.method) {
        this.events.push(message);
      }
    });
  }
  async send(method, params = {}) {
    await this.ready;
    const id = this.nextId++;
    const result = new Promise((resolveResult, rejectResult) => this.pending.set(id, { resolve: resolveResult, reject: rejectResult }));
    this.socket.send(JSON.stringify({ id, method, params }));
    return result;
  }
  close() { this.socket.close(); }
}

const cdp = new Cdp(newTarget.webSocketDebuggerUrl);
await cdp.send('Runtime.enable');
await cdp.send('Network.enable');
await cdp.send('DOM.enable');

// 等待页面加载
console.log('Waiting for page to load...');
await sleep(5000);

// 检查页面状态
const state = await cdp.send('Runtime.evaluate', {
  expression: `(() => ({ ready: Boolean(document.querySelector('input[type="file"]')), url: location.href, text: (document.body?.innerText||'').slice(0,500) }))()`,
  returnByValue: true,
});
console.log('Page state:', JSON.stringify(state.result?.value, null, 2));

if (!state.result?.value?.ready) {
  console.log('Page not ready, waiting more...');
  await sleep(10000);
}

// 找到 file input 并上传一张测试图片
const testFile = '/Users/huangjian/Documents/ChatGPT/yida帮助中心手册/tools/review/output/image-batch/yida-zh-en/generated/31a8cf4efbb452-en.png';
console.log('Uploading test file:', testFile);

const document = await cdp.send('DOM.getDocument', { depth: 2, pierce: true });
const match = await cdp.send('DOM.querySelector', {
  nodeId: document.root.nodeId,
  selector: 'input[type="file"]',
});
console.log('File input nodeId:', match.nodeId);

// 清空之前捕获的事件
cdp.events = [];

// 设置文件
await cdp.send('DOM.setFileInputFiles', { nodeId: match.nodeId, files: [testFile] });
console.log('File set! Waiting for network requests...');

// 等待网络请求
await sleep(15000);

// 分析捕获的网络请求
const requests = cdp.events.filter((e) => e.method === 'Network.requestWillBeSent');
console.log(`\n=== 捕获到 ${requests.length} 个网络请求 ===`);
for (const req of requests) {
  const params = req.params;
  const url = params.request?.url || '';
  const method = params.request?.method || '';
  const type = params.type || '';
  // 只显示非静态资源请求
  if (url.includes('alicdn.com') || url.includes('.js') || url.includes('.css') || url.includes('.png') && !url.includes('upload')) continue;
  if (url.includes('content.alibaba') || url.includes('upload') || method === 'POST' || type === 'XHR' || type === 'Fetch') {
    console.log(`\n[${method}] ${type} ${url.slice(0, 200)}`);
    const headers = params.request?.headers || {};
    const contentType = headers['Content-Type'] || headers['content-type'] || '';
    if (contentType) console.log('  Content-Type:', contentType);
    const hasPostData = params.request?.hasPostData;
    if (hasPostData) console.log('  Has POST data:', hasPostData);
    // 请求头中的关键信息
    const relevantHeaders = {};
    for (const [k, v] of Object.entries(headers)) {
      if (/auth|cookie|token|x-|content/i.test(k)) relevantHeaders[k] = typeof v === 'string' ? v.slice(0, 100) : v;
    }
    if (Object.keys(relevantHeaders).length) console.log('  Key headers:', JSON.stringify(relevantHeaders, null, 2));
  }
}

// 也检查响应
const responses = cdp.events.filter((e) => e.method === 'Network.responseReceived');
console.log(`\n=== 捕获到 ${responses.length} 个响应 ===`);
for (const resp of responses) {
  const params = resp.params;
  const url = params.response?.url || '';
  const status = params.response?.status || '';
  const type = params.type || '';
  if (url.includes('content.alibaba') || url.includes('upload') || type === 'XHR' || type === 'Fetch') {
    console.log(`[${status}] ${type} ${url.slice(0, 200)}`);
    const headers = params.response?.headers || {};
    const relevantHeaders = {};
    for (const [k, v] of Object.entries(headers)) {
      if (/content|location|x-|access/i.test(k)) relevantHeaders[k] = typeof v === 'string' ? v.slice(0, 150) : v;
    }
    if (Object.keys(relevantHeaders).length) console.log('  Headers:', JSON.stringify(relevantHeaders, null, 2));
  }
}

// 获取 Cookies
const cookiesResult = await cdp.send('Network.getCookies', { urls: ['https://content.alibaba-inc.com'] });
const cookies = cookiesResult.cookies || [];
console.log(`\n=== Cookies (${cookies.length}) ===`);
console.log('Cookie names:', cookies.map((c) => c.name).join(', '));
// 不输出 cookie 值，只输出名称

// 尝试获取上传请求的详细信息
const uploadRequests = requests.filter((r) => {
  const url = r.params.request?.url || '';
  const method = r.params.request?.method || '';
  return (url.includes('upload') || url.includes('pic') || url.includes('file')) && method === 'POST';
});
if (uploadRequests.length) {
  console.log(`\n=== 上传请求 (${uploadRequests.length}) ===`);
  for (const req of uploadRequests) {
    const params = req.params;
    console.log('URL:', params.request.url);
    console.log('Method:', params.request.method);
    const headers = params.request.headers || {};
    console.log('Headers keys:', Object.keys(headers).join(', '));
    // 获取请求体
    const requestId = params.requestId;
    try {
      const postData = await cdp.send('Network.getRequestPostData', { requestId });
      if (postData.postData) {
        console.log('Post data (first 500 chars):', postData.postData.slice(0, 500));
      }
    } catch (e) {
      console.log('Could not get post data:', e.message);
    }
  }
}

cdp.close();
console.log('\nDone!');
