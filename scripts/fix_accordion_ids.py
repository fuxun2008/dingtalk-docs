#!/usr/bin/env python3
"""为 <Accordion> 补唯一 id，消除 Mintlify CJK slug 锚点碰撞告警。
只加属性、不改任何可见标题；已带 id 的跳过；按页顺序编号 q1/q2/...
用法: fix_accordion_ids.py <file...>  (无参则 dry-run 全仓统计)
"""
import re, sys, glob

# 匹配 <Accordion 开标签（可能带若干属性），捕获属性区
OPEN = re.compile(r'<Accordion(?P<attrs>\s[^>]*)?>')

def has_id(attrs: str) -> bool:
    return bool(re.search(r'\bid\s*=', attrs or ''))

def fix_text(txt: str):
    n = [0]
    changed = [0]
    def repl(m):
        attrs = m.group('attrs') or ''
        if has_id(attrs):
            return m.group(0)
        n[0] += 1
        changed[0] += 1
        # 在 <Accordion 之后立即插入 id，保留原属性顺序
        return f'<Accordion id="q{n[0]}"{attrs}>'
    # 需要对所有 Accordion（含已有 id 的）都递增计数以保证与页面问答序号一致？
    # 采用：仅对无 id 的编号，但用运行序号避免与潜在已存在 id 冲突用前缀 q
    out = OPEN.sub(repl, txt)
    return out, changed[0]

def main():
    files = sys.argv[1:]
    if not files:
        files = glob.glob('**/*.mdx', recursive=True)
        total = 0
        for f in files:
            txt = open(f, encoding='utf-8').read()
            cnt = len(OPEN.findall(txt))
            noid = sum(1 for m in OPEN.finditer(txt) if not has_id(m.group('attrs') or ''))
            if noid:
                total += noid
        print(f"[dry-run] 全仓待补 id 的 Accordion 总数: {total}")
        return
    for f in files:
        txt = open(f, encoding='utf-8').read()
        out, c = fix_text(txt)
        if c:
            open(f, 'w', encoding='utf-8').write(out)
        print(f"{f}: +{c} id")

if __name__ == '__main__':
    main()
