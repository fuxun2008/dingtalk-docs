#!/usr/bin/env python3
"""
align_images_heuristic.py — 用段落字符相似度把新 md 的图同步到 mdx，保留所有 mdx 文本。

策略（不依赖 LLM）：
- mdx 和新 md 都是中文文档，段落文本应高度相似（钉钉中文文档 vs 仓库中文翻译）
- 按段落 + 图片块解析两侧
- 对新 md 每个「段落 + 后续图」组，找 mdx 中相似度最高的段落
- 用新图替换 mdx 该段落后面的旧图（保留段落文本不动）
- 新 md 中没有 mdx 对应段落的图，插入到上一个匹配段落之后（保证不丢图）

用法：
  python3 scripts/refetch_images/align_images_heuristic.py --product mail [--slug X] [--dry-run]
  python3 scripts/refetch_images/align_images_heuristic.py --product mail --apply

输出 staging mdx 与 LLM 版同路径，便于 --apply 复用。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

IMG_RE = re.compile(r'!\[[^\]]*\]\((https?://[^)\s]+)\)')
FRONTMATTER_RE = re.compile(r'^---\n(.*?)\n---\n', re.DOTALL)


def parse_blocks(text: str) -> list[dict]:
    """把文本解析为 [{type: 'text'|'image', content: str}] 顺序序列。
    'text' 块是一段连续的非图片文本（含空行/标题/列表/段落）。
    'image' 块是单个 ![](url) 图。"""
    blocks = []
    # 找到所有图片位置
    matches = list(IMG_RE.finditer(text))
    cursor = 0
    for m in matches:
        if m.start() > cursor:
            t = text[cursor:m.start()]
            if t.strip():
                blocks.append({'type': 'text', 'content': t})
        blocks.append({'type': 'image', 'content': m.group(0), 'url': m.group(1)})
        cursor = m.end()
    if cursor < len(text):
        t = text[cursor:]
        if t.strip():
            blocks.append({'type': 'text', 'content': t})
    return blocks


def text_for_match(s: str) -> str:
    """提取文本用于相似度匹配：去 markdown 修饰、空白、frontmatter 等噪音。"""
    # 去 frontmatter（如果是首块）
    s = FRONTMATTER_RE.sub('', s, count=1)
    # 去 markdown 修饰
    s = re.sub(r'\*\*([^*]+)\*\*', r'\1', s)       # 粗体
    s = re.sub(r'\*([^*]+)\*', r'\1', s)             # 斜体
    s = re.sub(r'#+\s*', '', s)                       # 标题井号
    s = re.sub(r'^\s*[-*]\s*', '', s, flags=re.M)    # 列表前缀
    s = re.sub(r'^\s*\d+\.\s*', '', s, flags=re.M)   # 有序列表前缀
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)   # 链接：保留 label
    s = re.sub(r'`([^`]+)`', r'\1', s)               # inline code
    s = re.sub(r'\s+', '', s)                         # 去全部空白（汉字密度匹配）
    return s


def similarity(a: str, b: str) -> float:
    a, b = text_for_match(a), text_for_match(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def split_into_sections(blocks: list[dict]) -> list[dict]:
    """把 blocks 拆成 [{text: 段文本, images: [block, ...]}] 序列。
    每个 section 是「一段文本」+「紧随其后的若干图片」。
    首个图片前的所有文本归首 section。"""
    sections = []
    cur_text = ''
    cur_imgs: list[dict] = []
    for b in blocks:
        if b['type'] == 'text':
            # 如果前面有图，先 flush 上一段
            if cur_imgs:
                sections.append({'text': cur_text, 'images': cur_imgs})
                cur_text = ''
                cur_imgs = []
            cur_text += b['content']
        else:
            cur_imgs.append(b)
    sections.append({'text': cur_text, 'images': cur_imgs})
    return sections


def split_text_into_sections(text: str) -> list[dict]:
    """按图片 anchor 把文本切成 sections：每个 section = 一段连续的非图片文本（含 frontmatter / 空行）。
    返回 [{'start': char_idx, 'end': char_idx, 'text': '...', 'image_urls': [url, ...]}]
    image_urls 是该 section 文本内的 inline 图 URL 顺序列表（同一 section 内可能多张）。

    section 边界：图片不切断 section（image 是 section 内部的 anchor），section 由 H2/H3/H4 标题切分。
    """
    # 用 H1-H6 标题 + 粗体子标题 作为 section 切分点（粗体子标题：「xxx」开头 + 整行加粗）
    # H1-H6 覆盖新源 md 用 H1 但 mdx 用 H2 的情况
    # 粗体行触发：处理 ai-minutes.mdx "亮点功能" 这种「6 个粗体子标题 + 6 张图交替」结构
    HEADER_RE = re.compile(r'^(?:(?:#{1,6})\s+.+|\*\*[^*]+\*\*\s*)$', re.M)
    boundaries = [0]
    for m in HEADER_RE.finditer(text):
        if m.start() > 0:
            boundaries.append(m.start())
    boundaries.append(len(text))
    # 去重 + 排序（粗体行可能与标题行重合）
    boundaries = sorted(set(boundaries))

    sections = []
    for k in range(len(boundaries) - 1):
        a, b = boundaries[k], boundaries[k + 1]
        chunk = text[a:b]
        img_urls = [m.group(1) for m in IMG_RE.finditer(chunk)]
        sections.append({'start': a, 'end': b, 'text': chunk, 'image_urls': img_urls})
    return sections


def align_one(mdx_text: str, new_md_text: str) -> tuple[str, dict]:
    """返回 (new_mdx_text, stats)。
    策略：保留 mdx 文本原格式（含 inline 图位置），仅对图 URL 做 string-level 替换 + 末尾追加多出的新图。"""
    mdx_secs = split_text_into_sections(mdx_text)
    new_secs = split_text_into_sections(new_md_text)

    # 段落贪心匹配
    used: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for i, ms in enumerate(mdx_secs):
        best_j, best_s = -1, -1.0
        for j, ns in enumerate(new_secs):
            if j in used:
                continue
            s = similarity(ms['text'], ns['text'])
            if s > best_s:
                best_j, best_s = j, s
        if best_j >= 0 and best_s >= 0.3:
            matches.append((i, best_j, best_s))
            used.add(best_j)

    matched_mdx_to_new: dict[int, int] = {i: j for i, j, _ in matches}
    matched_new_to_mdx: dict[int, int] = {j: i for i, j, _ in matches}

    # 对每个 mdx section 做 string-level 处理：
    # 1) 若有匹配 new section：按 inline 顺序替换 URL（min N）；多出的新图加到该 section 末尾
    # 2) 若无匹配：删除该 section 所有图 URL（清旧图）
    new_section_texts: list[str] = []
    for i, ms in enumerate(mdx_secs):
        sec_text = ms['text']
        if i in matched_mdx_to_new:
            ns = new_secs[matched_mdx_to_new[i]]
            old_urls = ms['image_urls']
            new_urls = ns['image_urls']
            n = min(len(old_urls), len(new_urls))
            # 按出现顺序 string 替换前 n 个 old → new
            for k in range(n):
                # 用 image markdown 完整匹配再替换（保留 alt 文本）
                pattern = re.escape(old_urls[k])
                sec_text = re.sub(pattern, new_urls[k], sec_text, count=1)
            # 若 mdx 多出的旧图（old > new）→ 删除多余 inline 图引用
            for k in range(n, len(old_urls)):
                pattern = re.compile(r'!\[[^\]]*\]\(' + re.escape(old_urls[k]) + r'\)\s*')
                sec_text = pattern.sub('', sec_text, count=1)
            # 若 new 多出的新图（new > old）→ 在 section 末尾追加
            extra_new = new_urls[n:]
            if extra_new:
                if not sec_text.endswith('\n'):
                    sec_text += '\n'
                for u in extra_new:
                    sec_text += f'\n![image.png]({u})\n'
        else:
            # 未匹配的 mdx section：删除所有 inline 图引用
            for u in ms['image_urls']:
                pattern = re.compile(r'!\[[^\]]*\]\(' + re.escape(u) + r'\)\s*')
                sec_text = pattern.sub('', sec_text, count=1)
        new_section_texts.append(sec_text)

    # 处理 new 中未被匹配的 section：把其中的图按位置插入到 mdx 对应位置（anchor 到前一个已匹配 new section 的 mdx section）
    unmatched_new_idx = sorted([j for j in range(len(new_secs)) if j not in used])
    for j in unmatched_new_idx:
        imgs = new_secs[j]['image_urls']
        if not imgs:
            continue
        # 找 new 中位置 < j 的最大已匹配 j'，把它对应的 mdx section 末尾追加这些图
        anchor_j = max((jj for jj in matched_new_to_mdx if jj < j), default=None)
        if anchor_j is None:
            anchor_i = 0
        else:
            anchor_i = matched_new_to_mdx[anchor_j]
        if not new_section_texts[anchor_i].endswith('\n'):
            new_section_texts[anchor_i] += '\n'
        for u in imgs:
            new_section_texts[anchor_i] += f'\n![image.png]({u})\n'

    out = ''.join(new_section_texts)
    out = re.sub(r'\n{3,}', '\n\n', out)

    # 统计
    mdx_img_count = len(IMG_RE.findall(mdx_text))
    new_img_count = len(IMG_RE.findall(new_md_text))
    out_img_count = len(IMG_RE.findall(out))

    stats = {
        'mdx_secs': len(mdx_secs),
        'new_secs': len(new_secs),
        'matched_secs': len(matches),
        'avg_match_score': round(sum(s for _, _, s in matches) / len(matches), 3) if matches else 0,
        'min_match_score': round(min((s for _, _, s in matches), default=0), 3),
        'mdx_img_count': mdx_img_count,
        'new_img_count': new_img_count,
        'out_img_count': out_img_count,
        'all_new_images_kept': out_img_count == new_img_count,
    }
    return out, stats


def process(product: str, slug_filter: str | None) -> list[dict]:
    out_dir = ROOT / 'scripts' / 'output' / 'refetch-images' / product
    with (out_dir / 'slug-mapping.json').open('r', encoding='utf-8') as f:
        smap = json.load(f)
    staging = out_dir / 'staging'
    staging.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in smap['mapping']:
        slug = entry['slug']
        if slug_filter and slug != slug_filter:
            continue
        mdx_path = ROOT / 'zh' / product / f'{slug}.mdx'
        new_md_path = Path(entry['output_path'])
        if not mdx_path.exists() or not new_md_path.exists():
            results.append({'slug': slug, 'status': 'skip', 'reason': f'mdx={mdx_path.exists()} new_md={new_md_path.exists()}'})
            continue
        mdx_text = mdx_path.read_text(encoding='utf-8')
        new_md_text = new_md_path.read_text(encoding='utf-8')
        try:
            new_mdx, stats = align_one(mdx_text, new_md_text)
        except Exception as e:
            results.append({'slug': slug, 'status': 'fail', 'reason': str(e)})
            continue
        (staging / f'{slug}.mdx').write_text(new_mdx, encoding='utf-8')
        results.append({'slug': slug, 'status': 'ok', **stats})
    return results


def write_report(product: str, results: list[dict]) -> None:
    out_dir = ROOT / 'scripts' / 'output' / 'refetch-images' / product
    ok = [r for r in results if r['status'] == 'ok']
    fail = [r for r in results if r['status'] != 'ok']
    img_kept = sum(1 for r in ok if r.get('all_new_images_kept'))
    lines = [
        f'# 启发式对齐报告 — {product}',
        '',
        f'- 总篇数: **{len(results)}**',
        f'- 成功: **{len(ok)}**',
        f'- 失败/跳过: **{len(fail)}**',
        f'- 图片完整保留（出图数 == 新源图数）: **{img_kept}/{len(ok)}**',
        '',
        '| slug | mdx段 | new段 | 匹配 | 平均得分 | 最低得分 | 旧图→新图→出图 | 完整 |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for r in results:
        if r['status'] != 'ok':
            lines.append(f'| `{r["slug"]}` | - | - | - | - | - | - | ❌ {r.get("reason","?")[:40]} |')
            continue
        kept = '✅' if r['all_new_images_kept'] else '⚠️'
        lines.append(f'| `{r["slug"]}` | {r["mdx_secs"]} | {r["new_secs"]} | {r["matched_secs"]} | {r["avg_match_score"]} | {r["min_match_score"]} | {r["mdx_img_count"]}→{r["new_img_count"]}→{r["out_img_count"]} | {kept} |')
    (out_dir / 'heuristic-report.md').write_text('\n'.join(lines), encoding='utf-8')


def apply(product: str) -> int:
    staging = ROOT / 'scripts' / 'output' / 'refetch-images' / product / 'staging'
    if not staging.exists():
        print(f'❌ staging 不存在: {staging}')
        return 0
    applied = 0
    for sp in sorted(staging.glob('*.mdx')):
        slug = sp.stem
        dst = ROOT / 'zh' / product / f'{slug}.mdx'
        if not dst.exists():
            continue
        shutil.copy(sp, dst)
        applied += 1
    return applied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--product', required=True, choices=['mail', 'ai-minutes', 'meetings'])
    ap.add_argument('--slug', default=None)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    if args.apply:
        n = apply(args.product)
        print(f'✅ apply: 覆盖 {n} 个 mdx')
        return

    results = process(args.product, args.slug)
    write_report(args.product, results)
    ok = [r for r in results if r['status'] == 'ok']
    img_kept = sum(1 for r in ok if r.get('all_new_images_kept'))
    img_lost = sum(1 for r in ok if not r.get('all_new_images_kept'))
    print(f'\n=== heuristic align: {args.product} ===')
    print(f'  ok={len(ok)} fail={len(results) - len(ok)}')
    print(f'  完整保留新图: {img_kept}/{len(ok)}')
    print(f'  ⚠️ 图数差异: {img_lost}（需 review）')
    print(f'  → scripts/output/refetch-images/{args.product}/staging/')
    print(f'  → scripts/output/refetch-images/{args.product}/heuristic-report.md')


if __name__ == '__main__':
    main()
