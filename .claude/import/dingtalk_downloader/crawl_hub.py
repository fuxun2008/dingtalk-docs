#!/usr/bin/env python3
"""从钉钉文档 hub URL → manifest.json（API 优先 + DOM 兜底 + EN 抽样校验）。

用途：替代 build_manifest.py，处理"团队已把一个产品的所有文档放在一个 hub 节点下"的场景，
不需要预先导出 .url 快捷方式包。

用法:
    python3 crawl_hub.py \\
        --hub-url 'https://alidocs.dingtalk.com/i/nodes/<id>' \\
        --lang en-US \\
        --output-dir ~/Downloads/2026-06-07_DingTalk_Mail/

抽取策略（API 优先，DOM 兜底）：
    A) 钉钉文档官方 API：/box/api/v2/dentry/list?dentryUuid=<uuid>&pageSize=100
       返回 children 数组（dentryUuid/name/dentryType: file|folder）。
       folder 自动递归展开（最大 5 层）。这条路径不依赖前端 UI 渲染，最稳。
    B) DOM 爬取：API 失败时回退；展开侧边栏 + 抽 a[href*="/i/nodes/"]。
       仅适用于左侧有标准 tree sidebar 的产品；Catalog 视图（React 包装）不工作。

流程:
    1. 启动 chromium + 加载 storage_state.json
    2. 打开 hub URL（?lang=en_US）+ EN 切换确认（CJK < 5%）
    3. **优先**调 API 递归抓 children；失败则 fallback DOM
    4. 抽样校验 N 个叶子（导航 + 检 CJK 比例 < 5%）
    5. 写 manifest.json（13 字段，与 build_manifest.py 同 schema）

退出码：
    0 成功；1 一般错误；2 EN 切换失败；3 抽样校验失败
"""
from __future__ import annotations
import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError as PWTimeout

# 复用 build_manifest 的工具
sys.path.insert(0, str(Path(__file__).parent))
from build_manifest import extract_node_id, sanitize_name  # noqa: E402

HERE = Path(__file__).parent
STATE_PATH = HERE / 'storage_state.json'
MANIFEST_PATH = HERE / 'manifest.json'

# CJK 字符范围（汉字 + 假名）— 用于"是否英文"判定
CJK_RE = re.compile(r'[぀-ヿ㐀-䶿一-鿿豈-﫿]')
MAX_CJK_RATIO = 0.05         # 抽样校验阈值：正文 CJK 占比超过 5% 即视为未切到 EN
FILENAME_BAD_CHARS_RE = re.compile(r'[\\/:*?"<>|]')

PAGE_TIMEOUT_MS = 30_000
SAMPLE_PAGE_TIMEOUT_MS = 20_000
EXPAND_INTERVAL_MS = 250
EXPAND_MAX_ROUNDS = 12

API_BASE = 'https://alidocs.dingtalk.com/box/api/v2/dentry/list'
API_TIMEOUT_MS = 15_000
API_MAX_DEPTH = 5    # 防御性递归深度上限


# ===== 语言判定 =====

def cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(CJK_RE.findall(text)) / max(len(text), 1)


def url_lang_param(lang_hyphen: str) -> str:
    """en-US → en_US（URL 参数风格）。"""
    return lang_hyphen.replace('-', '_')


def with_lang(url: str, lang_hyphen: str) -> str:
    """给 URL 拼 ?lang=<lang> 参数（保留其他参数）。"""
    p = urlparse(url)
    qs = dict(parse_qsl(p.query))
    qs['lang'] = url_lang_param(lang_hyphen)
    return urlunparse(p._replace(query=urlencode(qs)))


async def detect_language(page: Page) -> dict:
    info = await page.evaluate(
        """() => ({
            html_lang: document.documentElement.lang || '',
            url: location.href,
            title: document.title || '',
            body_text_sample: (document.body ? document.body.innerText : '').slice(0, 1000),
        })"""
    )
    info['cjk_ratio'] = cjk_ratio(info.get('body_text_sample', ''))
    return info


async def try_switch_to_english(page: Page) -> tuple[bool, str]:
    """尝试在 UI 上点语言切换按钮到 EN。返回 (是否成功, 描述)。"""
    # 第 1 步：找语言切换控件并点开
    trigger_candidates = [
        '[data-testid*="language"]',
        '[data-role*="language"]',
        'button[aria-label*="anguage"]',
        '[class*="language-switch"]',
        '[class*="LanguageSwitch"]',
        '[class*="language-selector"]',
    ]
    for sel in trigger_candidates:
        try:
            el = page.locator(sel).first
            await el.wait_for(state='visible', timeout=1_500)
            await el.click()
            await page.wait_for_timeout(600)
            # 第 2 步：在弹出菜单中点 English / EN
            option_candidates = [
                '[role="menuitem"]:has-text("English")',
                '[role="option"]:has-text("English")',
                'li:has-text("English")',
                'div.wd3-listitem:has-text("English")',
                'div:has-text("English"):not(:has(div))',
            ]
            for opt in option_candidates:
                try:
                    o = page.locator(opt).first
                    await o.wait_for(state='visible', timeout=1_500)
                    await o.click()
                    await page.wait_for_load_state('domcontentloaded', timeout=10_000)
                    await page.wait_for_timeout(800)
                    return True, f'{sel} → {opt}'
                except Exception:
                    continue
            # 切换按钮本身就是 toggle（直接生效）也算
            return True, f'{sel} (toggle)'
        except Exception:
            continue
    return False, 'no language switch UI matched'


async def ensure_english(page: Page) -> None:
    """多阶段把页面切到英文；失败则抛错（main 翻成 exit code 2）。"""
    info = await detect_language(page)
    print(f'  html lang={info["html_lang"]!r}, CJK ratio={info["cjk_ratio"]:.1%}')

    if info['cjk_ratio'] < MAX_CJK_RATIO:
        print('  ✓ 已是英文')
        return

    print('  尝试 UI 切换 ...')
    ok, msg = await try_switch_to_english(page)
    if ok:
        await page.wait_for_timeout(1_500)
        info2 = await detect_language(page)
        if info2['cjk_ratio'] < MAX_CJK_RATIO:
            print(f'  ✓ UI 切换成功 ({msg}, CJK={info2["cjk_ratio"]:.1%})')
            return
        print(f'  ⚠️ UI 切换未生效 ({msg}, CJK 仍={info2["cjk_ratio"]:.1%})')
    else:
        print(f'  ⚠️ {msg}')

    print('  请在浏览器中手动切到 English，完成后回到终端按 Enter')
    await asyncio.to_thread(input, '  >>> 切换完毕按 Enter: ')
    info3 = await detect_language(page)
    if info3['cjk_ratio'] >= MAX_CJK_RATIO:
        raise RuntimeError(
            f'切换后仍非英文 (CJK={info3["cjk_ratio"]:.1%}); 确认 hub 是否有 EN 版本'
        )
    print(f'  ✓ 手动切换成功 (CJK={info3["cjk_ratio"]:.1%})')


# ===== API 路径（优先） =====

async def fetch_children_api(
    ctx,
    dentry_uuid: str,
    parent_names: list[str] | None = None,
    depth: int = 0,
) -> list[dict] | None:
    """递归调钉钉文档 dentry/list API 抓 children。

    返回 list[dict]（含 href/title/parents 字段，与 DOM extract_tree 输出同 shape）。
    若 API 调用失败（HTTP error / isSuccess=false）返回 None，让上层 fallback DOM。
    folder 节点递归展开，file 节点作为 leaf 收集。
    """
    if depth >= API_MAX_DEPTH:
        print(f'  ⚠️ 递归达到上限 {API_MAX_DEPTH} 层，停止: {" / ".join(parent_names or [])}')
        return []

    parent_names = parent_names or []
    api_url = (
        f'{API_BASE}?dentryUuid={dentry_uuid}'
        f'&orderType=SORT_KEY&sortType=desc&listDentrySource=2&pageSize=100'
    )

    try:
        resp = await ctx.request.get(api_url, timeout=API_TIMEOUT_MS)
        if not resp.ok:
            print(f'  ⚠️ API HTTP {resp.status}: {dentry_uuid[:12]}...', file=sys.stderr)
            return None
        data = await resp.json()
        if not data.get('isSuccess'):
            print(f'  ⚠️ API isSuccess=false: {dentry_uuid[:12]}...', file=sys.stderr)
            return None
    except Exception as e:
        print(f'  ⚠️ API 调用异常 ({dentry_uuid[:12]}...): {type(e).__name__}: {e}', file=sys.stderr)
        return None

    children = (data.get('data') or {}).get('children', [])
    results: list[dict] = []
    for c in children:
        uuid = c.get('dentryUuid')
        name = (c.get('name') or '').strip()
        dtype = c.get('dentryType')
        if not uuid or not name:
            continue
        href = f'https://alidocs.dingtalk.com/i/nodes/{uuid}'
        if dtype == 'file':
            results.append({'href': href, 'title': name, 'parents': list(parent_names)})
        elif dtype == 'folder':
            sub = await fetch_children_api(ctx, uuid, parent_names + [name], depth + 1)
            if sub is None:
                # 子调用失败 → 把 folder 自身作为 leaf 保留（download.py 对非文档节点会优雅跳过）
                results.append({'href': href, 'title': name, 'parents': list(parent_names)})
            else:
                results.extend(sub)
        # 忽略其他类型（如 shortcut / external link）
    return results


# ===== 侧边栏展开 + 节点抽取 =====

async def expand_all_sidebar(page: Page) -> int:
    """循环点开所有可见的折叠节点。返回累计点开次数。"""
    total = 0
    for _round in range(EXPAND_MAX_ROUNDS):
        clicked = await page.evaluate(
            """() => {
                // 优先 aria-expanded=false；兜底各种 collapsed 类
                const sels = [
                    '[aria-expanded="false"]',
                    '[class*="collapsed-icon"]',
                    '[class*="collapse-icon"]',
                    '[class*="tree-switcher_close"]',
                ];
                let n = 0;
                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        if (el.offsetParent === null) continue;
                        try { el.click(); n++; } catch (e) {}
                    }
                }
                return n;
            }"""
        )
        if clicked == 0:
            break
        total += clicked
        await page.wait_for_timeout(EXPAND_INTERVAL_MS)
    return total


async def extract_tree(page: Page) -> list[dict]:
    """从 DOM 抽所有叶子节点 + 父链路（启发式：DOM 上溯找 li / [role=treeitem]）。"""
    items = await page.evaluate(
        """() => {
            const links = document.querySelectorAll(
                'a[href*="/i/nodes/"], a[href*="/docs/"]'
            );
            const out = [];
            const seen = new Set();
            for (const a of links) {
                if (a.offsetParent === null) continue;
                const href = a.href;
                const title = ((a.innerText || a.title || '') + '').trim();
                if (!title) continue;
                const key = href + '|' + title;
                if (seen.has(key)) continue;
                seen.add(key);

                // 父链路启发式：上溯祖先，遇到 li / [role=treeitem] 时取其首个文本节点作为父名
                const parents = [];
                let cur = a;
                for (let depth = 0; depth < 8 && cur; depth++) {
                    cur = cur.parentElement;
                    if (!cur) break;
                    if (cur.matches('li, [role="treeitem"], [class*="tree-node"], [class*="TreeNode"]')) {
                        // 找该容器自己的"标签"（不是子节点 a）
                        const ownLabel = cur.querySelector(
                            ':scope > a, :scope > div > a, :scope > div > span, :scope > span'
                        );
                        if (ownLabel && ownLabel !== a && !ownLabel.contains(a)) {
                            const t = (ownLabel.innerText || '').trim();
                            if (t && t !== title) parents.unshift(t);
                        }
                    }
                }
                out.push({ href, title, parents });
            }
            return out;
        }"""
    )
    return items


# ===== 抽样校验 =====

async def sample_verify(ctx: BrowserContext, items: list[dict], lang: str, sample_n: int) -> None:
    """随机抽 N 个叶子，导航过去确认 CJK < MAX_CJK_RATIO；任一失败即抛错。"""
    if not items:
        raise RuntimeError('没有任何叶子节点可抽样')
    samples = items if len(items) <= sample_n else random.sample(items, sample_n)
    print(f'  抽样校验 {len(samples)} / {len(items)} 个叶子是英文 (阈值 CJK < {MAX_CJK_RATIO:.0%}) ...')
    for s in samples:
        url = with_lang(s['href'], lang)
        p = await ctx.new_page()
        try:
            await p.goto(url, wait_until='domcontentloaded', timeout=SAMPLE_PAGE_TIMEOUT_MS)
            try:
                await p.wait_for_load_state('networkidle', timeout=8_000)
            except PWTimeout:
                pass
            await p.wait_for_timeout(1_200)
            info = await detect_language(p)
            if info['cjk_ratio'] >= MAX_CJK_RATIO:
                raise RuntimeError(
                    f'抽样页 CJK 比例 {info["cjk_ratio"]:.1%} ≥ {MAX_CJK_RATIO:.0%}; '
                    f'title="{s["title"]}", url={url}'
                )
            print(f'    ✓ {s["title"][:48]:<48} CJK={info["cjk_ratio"]:.1%}')
        finally:
            try:
                await p.close()
            except Exception:
                pass


# ===== Manifest 组装 =====

def sanitize_filename(name: str) -> str:
    """文件系统安全的文件名：先 sanitize_name 去不可见字符，再替换非法字符。"""
    s = sanitize_name(name)
    s = FILENAME_BAD_CHARS_RE.sub('_', s)
    return s.strip(' .') or '_unnamed'


def build_manifest_entries(
    items: list[dict],
    hub_url: str,
    output_dir: Path,
) -> list[dict]:
    """DOM 抽出 → 13 字段 manifest。2 级 cap：3+ 级 group 把深路径并进 title。"""
    entries: list[dict] = []
    seen_node_ids: set[str] = set()
    skipped = {'no_node_id': 0, 'duplicate': 0, 'empty_title': 0}

    for item in items:
        # 规范化 URL（剥查询参数，与 build_manifest 一致）
        href = item['href']
        p = urlparse(href)
        clean_url = f'{p.scheme}://{p.netloc}{p.path}'

        node_id, kind = extract_node_id(clean_url)
        if not node_id:
            skipped['no_node_id'] += 1
            continue
        if node_id in seen_node_ids:
            skipped['duplicate'] += 1
            continue

        title_raw = sanitize_name(item['title'])
        if not title_raw:
            skipped['empty_title'] += 1
            continue

        parents = [sanitize_name(x) for x in item.get('parents', [])]
        parents = [x for x in parents if x]

        # 2 级 cap（遵守 /docs-import-archive 陷阱 4）
        if not parents:
            category = '_root'
            display_title = title_raw
            rel_path = title_raw
            output_path = output_dir / f'{sanitize_filename(title_raw)}.md'
        elif len(parents) == 1:
            category = parents[0]
            display_title = title_raw
            rel_path = f'{sanitize_filename(category)}/{sanitize_filename(title_raw)}'
            output_path = output_dir / sanitize_filename(category) / f'{sanitize_filename(title_raw)}.md'
        else:
            # 3+ 级：第一段当 category；中间段 + title 用 " / " 拼成 display_title，文件名转 " - "
            category = parents[0]
            display_title = ' / '.join(parents[1:] + [title_raw])
            filename_title = ' - '.join(parents[1:] + [title_raw])
            rel_path = f'{sanitize_filename(category)}/{sanitize_filename(filename_title)}'
            output_path = output_dir / sanitize_filename(category) / f'{sanitize_filename(filename_title)}.md'

        seen_node_ids.add(node_id)
        entries.append({
            'rel_path': rel_path,
            'title': display_title,
            'category': category,
            'node_id': node_id,
            'id_kind': kind,
            'url': clean_url,
            'source_url_file': f'hub:{hub_url}',
            'output_path': str(output_path),
            'status': 'pending',
            'attempts': 0,
            'error': None,
            'downloaded_at': None,
            'size_bytes': None,
        })

    if any(skipped.values()):
        print(f'  跳过: {skipped}')
    return entries


# ===== 主流程 =====

async def main(args: argparse.Namespace) -> int:
    if not STATE_PATH.exists():
        print(f'❌ {STATE_PATH} 不存在；先跑 auth_bootstrap.py', file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    if not args.lang or '-' not in args.lang:
        print(f'❌ --lang 必须形如 en-US / zh-CN（带连字符），收到 {args.lang!r}', file=sys.stderr)
        return 1

    hub_node_id, hub_kind = extract_node_id(args.hub_url)
    if not hub_node_id:
        print(f'❌ 无法从 hub-url 解析 node id: {args.hub_url}', file=sys.stderr)
        return 1

    print('=' * 60)
    print(f'crawl_hub: {args.hub_url}')
    print(f'  语言: {args.lang}    输出目录: {output_dir}')
    print('=' * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        ctx = await browser.new_context(
            storage_state=str(STATE_PATH),
            viewport={'width': 1440, 'height': 900},
            locale=args.lang,
            extra_http_headers={'Accept-Language': f'{args.lang},en;q=0.9'},
            accept_downloads=True,
        )
        page = await ctx.new_page()

        hub_url_lang = with_lang(args.hub_url, args.lang)
        print(f'\n[1/5] 打开 hub: {hub_url_lang}')
        await page.goto(hub_url_lang, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT_MS)
        try:
            await page.wait_for_load_state('networkidle', timeout=10_000)
        except PWTimeout:
            pass
        await page.wait_for_timeout(1_500)

        print('\n[2/5] 确认页面为英文')
        try:
            await ensure_english(page)
        except RuntimeError as e:
            print(f'❌ {e}', file=sys.stderr)
            await browser.close()
            return 2

        print('\n[3/5] 抽取节点（API 优先）')
        raw_items: list[dict] | None = None
        if not args.dom_only:
            api_items = await fetch_children_api(ctx, hub_node_id)
            if api_items is not None:
                raw_items = api_items
                print(f'  ✓ API 拿到 {len(raw_items)} 条 leaf')
            else:
                print(f'  ⚠️ API 路径失败，回退 DOM 爬取')

        if raw_items is None:
            print('  展开侧边栏 ...')
            n_expanded = await expand_all_sidebar(page)
            print(f'  累计点开 {n_expanded} 个折叠节点')
            await page.wait_for_timeout(1_500)
            raw_items = await extract_tree(page)
            print(f'  DOM 抽到 {len(raw_items)} 条')

        print(f'\n[4/5] 节点规范化')
        if not raw_items:
            print('❌ 一条节点都没抽到（API 与 DOM 均失败）；'
                  '检查：1) hub URL 是否正确 2) 登录态是否过期 3) DOM 是否 Catalog 视图', file=sys.stderr)
            await browser.close()
            return 1

        entries = build_manifest_entries(raw_items, args.hub_url, output_dir)
        print(f'  规范化后 {len(entries)} 条 (按 node_id 去重)')
        if not entries:
            print('❌ 抽到了节点但规范化后 0 条；检查 build_manifest_entries 跳过原因', file=sys.stderr)
            await browser.close()
            return 1

        # 加入 hub 本身作为 _root 节点（download.py 对非文档节点会优雅跳过）
        if args.include_hub and not any(e['node_id'] == hub_node_id for e in entries):
            hub_title = sanitize_name((await page.title()) or 'Overview')
            entries.insert(0, {
                'rel_path': hub_title,
                'title': hub_title,
                'category': '_root',
                'node_id': hub_node_id,
                'id_kind': hub_kind,
                'url': args.hub_url,
                'source_url_file': f'hub:{args.hub_url}',
                'output_path': str(output_dir / f'{sanitize_filename(hub_title)}.md'),
                'status': 'pending',
                'attempts': 0,
                'error': None,
                'downloaded_at': None,
                'size_bytes': None,
            })
            print(f'  + 已包含 hub 节点本身: "{hub_title}"')

        if args.sample_n > 0:
            print(f'\n[5/5] 抽样校验')
            try:
                await sample_verify(ctx, raw_items, args.lang, args.sample_n)
            except RuntimeError as e:
                print(f'❌ {e}', file=sys.stderr)
                await browser.close()
                return 3
        else:
            print(f'\n[5/5] 抽样校验：跳过 (sample-n=0)')

        await browser.close()

    # 写 manifest
    MANIFEST_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    # 统计
    by_cat: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for e in entries:
        by_cat[e['category']] = by_cat.get(e['category'], 0) + 1
        by_kind[e['id_kind']] = by_kind.get(e['id_kind'], 0) + 1

    print('\n' + '=' * 60)
    print(f'✅ manifest.json 写入 {len(entries)} 条')
    print(f'   {MANIFEST_PATH}')
    print(f'\n按 id_kind:')
    for k, v in sorted(by_kind.items()):
        print(f'   {k}: {v}')
    print(f'\n按 category（前 15）:')
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1])[:15]:
        print(f'   {n:>3}  {cat}')
    print(f'\n下一步: python3 download.py --locale {args.lang}')
    return 0


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description='钉钉文档 hub URL → manifest.json（EN 抽样校验）')
    ap.add_argument('--hub-url', required=True, help='hub 节点 URL（必填）')
    ap.add_argument('--lang', default='en-US', help='目标语言（默认 en-US；同时用作浏览器 locale 与 URL ?lang 参数）')
    ap.add_argument('--output-dir', required=True, help='下载产物根目录（baked 进每条 entry 的 output_path）')
    ap.add_argument('--sample-n', type=int, default=3, help='抽样校验的叶子数（默认 3；设 0 跳过）')
    ap.add_argument('--include-hub', action=argparse.BooleanOptionalAction, default=True, help='是否把 hub 节点本身也加入 manifest（默认 yes）')
    ap.add_argument('--headless', action=argparse.BooleanOptionalAction, default=False, help='是否 headless（默认 no，便于人工兜底切语言）')
    ap.add_argument('--dom-only', action='store_true', help='跳过 API 直接走 DOM 爬取（调试用）')
    return ap.parse_args()


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main(parse_args())))
    except KeyboardInterrupt:
        print('\n已取消')
        sys.exit(130)
