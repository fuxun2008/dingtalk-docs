#!/usr/bin/env python3
"""宜搭 en/ja/id 三语：移除嵌入图片 + 迭代删除安全空标题（保留有内容的父容器）。
- 图片：删 markdown ![]() 与移图后变空的 <Frame></Frame> 壳
- 空标题：迭代删「无正文且无子标题」的叶子空标题；父容器（子标题有内容）永不变空故不删
- 代码围栏内的 # 不当标题；frontmatter 不动
用法: script.py --apply <files...>  |  script.py <files...>(dry-run 打印会删的标题)
"""
import re, sys

H = re.compile(r'^(#{1,6})\s+\S')
IMG = re.compile(r'!\[[^\]]*\]\([^)]*\)')
FRAME_EMPTY = re.compile(r'<Frame[^>]*>\s*</Frame>', re.S)

def split_fm(text):
    if text.startswith('---\n'):
        end = text.find('\n---', 4)
        if end != -1:
            e2 = text.find('\n', end+1)
            return text[:e2+1], text[e2+1:]
    return '', text

def code_fence_mask(lines):
    """返回每行是否在 ``` 代码围栏内"""
    inside=False; mask=[]
    for l in lines:
        if re.match(r'\s*```', l):
            mask.append(True)  # fence 行本身算块内
            inside = not inside
        else:
            mask.append(inside)
    return mask

def strip_images(body):
    body = IMG.sub('', body)
    # 反复清空壳 Frame（可能多行）
    prev=None
    while prev!=body:
        prev=body
        body = FRAME_EMPTY.sub('', body)
    return body

def remove_empty_headings(body):
    removed=[]
    while True:
        lines = body.split('\n')
        mask = code_fence_mask(lines)
        heads=[(i,len(re.match(r'^(#{1,6})',lines[i]).group(1)))
               for i in range(len(lines))
               if not mask[i] and H.match(lines[i])]
        to_del=set()
        for k,(i,lvl) in enumerate(heads):
            nxt = heads[k+1][0] if k+1<len(heads) else len(lines)
            btext='\n'.join(lines[i+1:nxt]).strip()
            is_leaf = (k+1>=len(heads)) or (heads[k+1][1] <= lvl)
            if btext=='' and is_leaf:
                to_del.add(i)
                # 连带删该标题到下个标题间的空白 body 行
                for j in range(i+1,nxt): to_del.add(j)
        if not to_del: break
        for i in sorted(to_del):
            if H.match(lines[i]): removed.append(lines[i].strip())
        body='\n'.join(l for j,l in enumerate(lines) if j not in to_del)
    return body, removed

def process(text):
    fm, body = split_fm(text)
    body = strip_images(body)
    body, removed = remove_empty_headings(body)
    # 收敛 3+ 连续空行为 2
    body = re.sub(r'\n{3,}', '\n\n', body)
    return fm+body, removed

def main():
    args=sys.argv[1:]
    apply='--apply' in args
    files=[a for a in args if a!='--apply']
    tot_h=0; tot_f=0
    for f in files:
        t=open(f,encoding='utf-8').read()
        out,removed=process(t)
        if out!=t:
            tot_f+=1; tot_h+=len(removed)
            if apply: open(f,'w',encoding='utf-8').write(out)
            else:
                for h in removed: print(f"  [{f}] del: {h}")
    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: {tot_f} 文件, {tot_h} 个空标题")

if __name__=='__main__': main()
