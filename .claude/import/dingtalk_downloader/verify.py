#!/usr/bin/env python3
"""下载产物校验。

用法:
    python3 verify.py

检查:
  1. 数量：manifest entries vs 实际 .md 文件
  2. 空文件 / 过小文件（< 200 bytes）
  3. 登录页污染（含"请登录"/"扫码登录"等关键词）
  4. H1 一致性（首行 # title 是否与 manifest.title 高度相似）
  5. 输出 verify_report.md
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
MANIFEST_PATH = HERE / 'manifest.json'
DEST_ROOT = Path.home() / 'Downloads' / 'dingtalk-docs-archive'
REPORT_PATH = DEST_ROOT / 'verify_report.md'

MIN_BYTES = 200
LOGIN_KEYWORDS = ('请登录', '扫码登录', 'login-form', 'dt-login', 'Please log in', '账号登录')
H1_RE = re.compile(r'^\s*#\s+(.+?)\s*$', re.MULTILINE)


def normalize(s: str) -> str:
    """去空格、标点、转小写做模糊比对。"""
    return re.sub(r'[\s\W_]+', '', s).lower()


def check_one(entry: dict) -> dict:
    """返回 issues 列表 + 元数据。"""
    out_path = Path(entry['output_path'])
    result = {
        'rel_path': entry['rel_path'],
        'manifest_status': entry.get('status'),
        'file_exists': out_path.exists(),
        'size_bytes': 0,
        'h1': None,
        'h1_match': None,
        'issues': [],
    }

    if not out_path.exists():
        if entry.get('status') == 'success':
            result['issues'].append('file_missing_but_status_success')
        return result

    data = out_path.read_bytes()
    result['size_bytes'] = len(data)
    if len(data) < MIN_BYTES:
        result['issues'].append(f'file_too_small ({len(data)} bytes)')

    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        result['issues'].append('not_utf8')
        return result

    if any(k in text for k in LOGIN_KEYWORDS):
        result['issues'].append('contains_login_keywords')

    m = H1_RE.search(text)
    if m:
        h1 = m.group(1).strip()
        result['h1'] = h1
        manifest_title = entry['title']
        # fuzzy match: H1 包含 manifest title 关键部分 或反过来
        n_h1 = normalize(h1)
        n_title = normalize(manifest_title)
        if not n_h1 or not n_title:
            result['h1_match'] = False
            result['issues'].append('h1_or_title_empty')
        elif n_h1 in n_title or n_title in n_h1:
            result['h1_match'] = True
        else:
            # 计算最长公共子串占比
            shorter = min(n_h1, n_title, key=len)
            longer = max(n_h1, n_title, key=len)
            common_chars = sum(1 for c in shorter if c in longer)
            ratio = common_chars / max(len(shorter), 1)
            result['h1_match'] = ratio >= 0.7
            if not result['h1_match']:
                result['issues'].append(f'h1_title_mismatch (h1="{h1[:30]}" vs title="{manifest_title[:30]}")')
    else:
        result['issues'].append('no_h1')

    return result


def main() -> int:
    if not MANIFEST_PATH.exists():
        print(f'❌ {MANIFEST_PATH} 不存在', file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    results = [check_one(e) for e in manifest]

    total = len(results)
    files_present = sum(1 for r in results if r['file_exists'])
    healthy = sum(1 for r in results if r['file_exists'] and not r['issues'])
    with_issues = [r for r in results if r['issues']]
    missing = [r for r in results if not r['file_exists']]

    # 按状态统计
    by_status: dict[str, int] = {}
    for e in manifest:
        s = e.get('status') or 'unknown'
        by_status[s] = by_status.get(s, 0) + 1

    # 写报告
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append('# Verify Report\n')
    lines.append(f'- manifest 总数: **{total}**')
    lines.append(f'- 实际文件存在: **{files_present}**')
    lines.append(f'- 完全健康（无 issue）: **{healthy}**')
    lines.append(f'- 缺失文件: **{len(missing)}**')
    lines.append(f'- 有 issue 的文件: **{len(with_issues)}**')
    lines.append('')
    lines.append('## 按 manifest.status')
    for s, n in sorted(by_status.items(), key=lambda x: -x[1]):
        lines.append(f'- {s}: {n}')
    lines.append('')

    if missing:
        lines.append('## 缺失的文件（manifest 有但磁盘无）')
        for r in missing[:50]:
            lines.append(f'- `{r["rel_path"]}` (status={r["manifest_status"]})')
        if len(missing) > 50:
            lines.append(f'- ... 还有 {len(missing) - 50} 条')
        lines.append('')

    if with_issues:
        lines.append('## 有 issue 的文件')
        # 按 issue 类型分组
        by_issue: dict[str, list] = {}
        for r in with_issues:
            for issue in r['issues']:
                key = issue.split(' ')[0]
                by_issue.setdefault(key, []).append(r)
        for issue_key in sorted(by_issue.keys(), key=lambda k: -len(by_issue[k])):
            samples = by_issue[issue_key]
            lines.append(f'### {issue_key} ({len(samples)})')
            for r in samples[:10]:
                lines.append(f'- `{r["rel_path"]}` size={r["size_bytes"]} issues={r["issues"]}')
            if len(samples) > 10:
                lines.append(f'- ... 还有 {len(samples) - 10} 条')
            lines.append('')

    REPORT_PATH.write_text('\n'.join(lines), encoding='utf-8')

    # 终端汇总
    print('=' * 60)
    print(f'总数: {total}')
    print(f'文件存在: {files_present}')
    print(f'完全健康: {healthy}')
    print(f'有 issue: {len(with_issues)}')
    print(f'缺失: {len(missing)}')
    print('=' * 60)
    print(f'报告: {REPORT_PATH}')

    return 0 if not missing and not with_issues else 1


if __name__ == '__main__':
    sys.exit(main())
