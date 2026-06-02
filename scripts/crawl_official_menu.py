"""crawl_official_menu.py — 爬取 alidocs 钉钉文档项目左侧菜单的官方顺序

用法:
  python scripts/crawl_official_menu.py [--headed] [--out <path>]

输出:
  scripts/output/fix/official-menu-full.json
    [{docKey, depth, title, hasChildren, captureOrder}, ...]
    depth 是相对「钉钉文档」根的深度: 钉钉文档=0, group=1, page=2, nested=3, leaf=4

策略 (基于 React fiber 直接读 dataList，比 DOM 扫描可靠):
  1. 打开钉钉文档根 docKey URL
  2. 等 sidebar 出现，从 .ReactVirtualized__List 的父 fiber 找到 dataList
     dataList 节点形如 {id, name, hasChildren, depth, type}
  3. 循环展开「钉钉文档」子树内的 collapsed 节点:
     - 找 hasChildren=true 但下一个节点 depth 没增加的节点 (= 未展开)
     - 滚到其位置 → 点击 [data-testid="tree-expand-icon"]
     - 等待 React 更新 dataList
     - 直到无新 collapsed
  4. 输出钉钉文档子树（保持 dataList 原序，depth 减偏移）

依赖: playwright (sync_api) + chromium
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "fix"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUT = OUTPUT_DIR / "official-menu-full.json"

ROOT_URL = "https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/od245kZmnOeW4D4L73YEWYbzxL6R0wMQ"
DINGTALK_DOC_ROOT_ID = "od245kZmnOeW4D4L73YEWYbzxL6R0wMQ"

ROW_HEIGHT = 36
MAX_EXPAND_ROUNDS = 200    # 单次扫一个 collapsed 一次，总共 ~100 个节点
EXPAND_WAIT_MS = 250       # 点击展开后等待 React rerender + 数据加载


# ---------------------------------------------------------------------------
# JS: 读取当前 dataList
# ---------------------------------------------------------------------------

JS_READ_DATALIST = r"""
() => {
  const list = document.querySelector('.ReactVirtualized__List');
  if (!list) return { error: 'no virtualized list' };
  const fiberKey = Object.keys(list).find(k => k.startsWith('__reactFiber'));
  if (!fiberKey) return { error: 'no react fiber' };
  let fiber = list[fiberKey];
  let depth = 0;
  while (fiber && depth < 40) {
    const arr = fiber.memoizedProps && fiber.memoizedProps.dataList;
    if (Array.isArray(arr)) {
      return {
        items: arr.map(n => ({
          id: n.id,
          name: n.name,
          hasChildren: !!n.hasChildren,
          depth: n.depth,
        })),
      };
    }
    fiber = fiber.return;
    depth++;
  }
  return { error: 'dataList not found in fiber chain' };
}
"""

# 找钉钉文档子树内第一个 collapsed 节点，返回 {id, globalIdx, name, depth}
JS_FIND_FIRST_COLLAPSED = r"""
(rootId) => {
  const list = document.querySelector('.ReactVirtualized__List');
  const fiberKey = Object.keys(list).find(k => k.startsWith('__reactFiber'));
  let fiber = list[fiberKey];
  while (fiber && !(fiber.memoizedProps && Array.isArray(fiber.memoizedProps.dataList))) {
    fiber = fiber.return;
  }
  const arr = fiber.memoizedProps.dataList;
  const rootIdx = arr.findIndex(n => n.id === rootId);
  if (rootIdx < 0) return { error: 'root not in dataList' };
  const rootDepth = arr[rootIdx].depth;
  let endIdx = rootIdx + 1;
  while (endIdx < arr.length && arr[endIdx].depth > rootDepth) endIdx++;
  // 子树内 collapsed
  for (let i = rootIdx + 1; i < endIdx; i++) {
    const n = arr[i];
    if (!n.hasChildren) continue;
    const next = arr[i + 1];
    if (!next || next.depth <= n.depth) {
      return { id: n.id, globalIdx: i, name: n.name, depth: n.depth, subtreeSize: endIdx - rootIdx };
    }
  }
  return { done: true, subtreeSize: endIdx - rootIdx };
}
"""

JS_SCROLL_AND_CLICK = r"""
({ targetId, targetIdx, rowHeight }) => {
  const list = document.querySelector('.ReactVirtualized__List');
  if (!list) return { error: 'no list' };
  // 滚到目标行中部
  const wanted = Math.max(0, targetIdx * rowHeight - 200);
  list.scrollTop = wanted;
  // 等下一帧
  return new Promise(resolve => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const row = document.querySelector(`[data-rbd-draggable-id="${targetId}"]`);
        if (!row) return resolve({ error: 'row not rendered after scroll', wanted, scrollTop: list.scrollTop });
        const icon = row.querySelector('[data-testid="tree-expand-icon"]');
        if (!icon) return resolve({ error: 'no expand icon' });
        icon.click();
        resolve({ ok: true, scrollTop: list.scrollTop });
      });
    });
  });
}
"""


# ---------------------------------------------------------------------------
# main crawler
# ---------------------------------------------------------------------------

def crawl(headed: bool) -> list[dict]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        print(f"[crawl] loading {ROOT_URL}")
        page.goto(ROOT_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".portal-tree-selection-target", timeout=30000)
        page.wait_for_timeout(2000)

        # 验证可读 dataList
        initial = page.evaluate(JS_READ_DATALIST)
        if "error" in initial:
            raise RuntimeError(f"dataList read failed: {initial}")
        print(f"[crawl] initial dataList size: {len(initial['items'])}")

        # 循环展开钉钉文档子树
        prev_subtree = -1
        no_progress_rounds = 0
        for rnd in range(MAX_EXPAND_ROUNDS):
            result = page.evaluate(JS_FIND_FIRST_COLLAPSED, DINGTALK_DOC_ROOT_ID)
            if result.get("error"):
                print(f"  round {rnd}: {result}")
                break
            if result.get("done"):
                print(f"  round {rnd}: all expanded, subtree size = {result['subtreeSize']}")
                break
            tgt_id = result["id"]
            tgt_idx = result["globalIdx"]
            tgt_name = result["name"]
            tgt_depth = result["depth"]
            subtree = result["subtreeSize"]
            if rnd % 10 == 0 or subtree != prev_subtree:
                print(f"  round {rnd}: subtree={subtree}, expanding depth={tgt_depth} idx={tgt_idx} '{tgt_name[:30]}'")
            # 检测停滞
            if subtree == prev_subtree:
                no_progress_rounds += 1
                if no_progress_rounds > 5:
                    print(f"  round {rnd}: NO PROGRESS for 5 rounds, breaking")
                    break
            else:
                no_progress_rounds = 0
            prev_subtree = subtree

            click_res = page.evaluate(
                JS_SCROLL_AND_CLICK,
                {"targetId": tgt_id, "targetIdx": tgt_idx, "rowHeight": ROW_HEIGHT},
            )
            if click_res.get("error"):
                print(f"    click error: {click_res}; skipping")
                # 即使点击失败也继续，跳过该节点
                # 通过插入个 sentinel：强制把这个 node 标记为不可展开
                # 但简单点：直接 break
                break
            page.wait_for_timeout(EXPAND_WAIT_MS)

        # 最终读 dataList
        final = page.evaluate(JS_READ_DATALIST)
        items = final["items"]
        print(f"[crawl] final dataList size: {len(items)}")

        # 提取钉钉文档子树（含根本身）
        root_idx = next((i for i, n in enumerate(items) if n["id"] == DINGTALK_DOC_ROOT_ID), -1)
        if root_idx < 0:
            raise RuntimeError("root node missing from final dataList")
        root_depth = items[root_idx]["depth"]
        end_idx = root_idx + 1
        while end_idx < len(items) and items[end_idx]["depth"] > root_depth:
            end_idx += 1
        subtree = items[root_idx:end_idx]
        print(f"[crawl] dingtalk-docs subtree size: {len(subtree)}")

        # 转换 depth 为相对深度（根=0）
        out = []
        for i, n in enumerate(subtree):
            out.append({
                "docKey": n["id"],
                "title": n["name"],
                "depth": n["depth"] - root_depth,
                "hasChildren": n["hasChildren"],
                "captureOrder": i,
            })

        browser.close()
        return out


def print_ascii_tree(items: list[dict], limit: int = 200) -> None:
    for it in items[:limit]:
        indent = "  " * it["depth"]
        marker = "" if it["hasChildren"] else " ·"
        print(f'{indent}- [{it["docKey"][:8]}] {it["title"]}{marker}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headed", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出文件")
    args = parser.parse_args()

    items = crawl(headed=args.headed)
    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[crawl] wrote {args.out} ({len(items)} rows)")

    from collections import Counter
    histo = Counter(it["depth"] for it in items)
    print("[crawl] depth histogram:")
    for d in sorted(histo):
        print(f"  depth {d}: {histo[d]} rows")

    print("\n[crawl] ASCII tree (first 200 rows):")
    print_ascii_tree(items, 200)
    if len(items) > 200:
        print(f"  ... and {len(items) - 200} more (see {args.out})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
