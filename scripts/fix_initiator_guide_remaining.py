#!/usr/bin/env python3
"""
修复 initiator-guide.mdx 的剩余问题：
1. 第 6、7、8 节的表格转为双列布局
2. 为所有 Frame 添加 margin-bottom 间隙
"""

import re
from pathlib import Path


def fix_remaining_tables(content: str) -> str:
    """修复剩余的「电脑端 | 手机端」表格"""
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测「电脑端 | 手机端」表格（第6、7、8节）
        if line.strip() == '| 电脑端 | 手机端 |':
            # 收集表格后的图片
            images = []
            i += 1  # 跳过分隔行
            if i < len(lines) and '| --- |' in lines[i]:
                i += 1

            # 收集所有图片
            while i < len(lines) and lines[i].strip().startswith('!['):
                images.append(lines[i].strip())
                i += 1

            if images:
                # 生成双列布局
                result.append('<div className="flex gap-4">')

                # 电脑端
                result.append('<div className="flex-1">')
                result.append('<p className="text-center font-semibold mb-2">电脑端</p>')

                # 电脑端的图片（偶数索引：0, 2, 4...）
                for idx in range(0, len(images), 2):
                    result.append('<Frame className="mb-4">')
                    result.append('')
                    result.append(images[idx])
                    result.append('</Frame>')
                    result.append('')

                result.append('</div>')
                result.append('')

                # 手机端
                result.append('<div className="flex-1">')
                result.append('<p className="text-center font-semibold mb-2">手机端</p>')

                # 手机端的图片（奇数索引：1, 3, 5...）
                for idx in range(1, len(images), 2):
                    result.append('<Frame className="mb-4">')
                    result.append('')
                    result.append(images[idx])
                    result.append('</Frame>')
                    result.append('')

                result.append('</div>')
                result.append('</div>')

                continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def add_frame_margins(content: str) -> str:
    """为现有的 Frame 添加底部间隙"""
    # 在双列布局中的 Frame 添加 mb-4
    # 匹配模式：<Frame> 后面跟着空行和图片，且在 flex-1 div 内

    lines = content.split('\n')
    result = []
    i = 0
    in_flex_column = False

    while i < len(lines):
        line = lines[i]

        # 检测进入 flex-1 div
        if '<div className="flex-1">' in line:
            in_flex_column = True

        # 检测退出 flex-1 div
        if in_flex_column and '</div>' in line:
            in_flex_column = False

        # 在 flex-1 内的 Frame 标签后添加间隙
        if in_flex_column and line.strip() == '<Frame>':
            # 检查下一个 Frame 是否已经有 className
            if '<Frame className=' not in line:
                result.append('<Frame className="mb-4">')
            else:
                result.append(line)
        else:
            result.append(line)

        i += 1

    return '\n'.join(result)


def main():
    """主函数"""
    file_path = Path(__file__).parent.parent / 'zh' / 'approval' / 'initiator-guide.mdx'

    if not file_path.exists():
        print(f"错误：文件不存在 {file_path}")
        return

    print(f"处理文件: {file_path}")

    content = file_path.read_text(encoding='utf-8')
    original = content

    # 1. 修复剩余的表格
    content = fix_remaining_tables(content)

    # 2. 为现有 Frame 添加间隙
    content = add_frame_margins(content)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ 已修复剩余表格并添加 Frame 间隙")
    else:
        print(f"- 无需修改")


if __name__ == '__main__':
    main()
