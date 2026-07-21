#!/usr/bin/env python3
"""
修复 initiator-guide.mdx 中的表格问题

问题 1：图片堆在表格外（MDX 解析错误）
问题 2：表格第二列包含图片，挤压第三列内容

解决方案：
- 将「入口 | 工作台 | OA审批」类型的表格转为 Tabs 组件
- 将「电脑端 | 手机端」类型的表格转为并排 Frame（双列布局）
- 将「序号 | 常见异常 | 原因方法」表格转为 Steps 组件
"""

import re
from pathlib import Path


def fix_entry_table(lines, start_idx):
    """
    修复「入口 | 工作台 | OA审批」类型的表格
    转换为 Tabs 组件
    """
    # 收集表格后的图片
    images = []
    i = start_idx + 2  # 跳过表头和分隔行

    while i < len(lines) and lines[i].strip().startswith('!['):
        images.append(lines[i].strip())
        i += 1

    if len(images) != 6:  # 应该有 6 张图（2行×3列）
        return None, i

    result = [
        '<Tabs>',
        '<Tab title="工作台">',
        '<div className="flex gap-4">',
        '<Frame>',
        '',
        images[0],
        '</Frame>',
        '',
        '<Frame>',
        '',
        images[3],
        '</Frame>',
        '</div>',
        '</Tab>',
        '<Tab title="OA审批">',
        '<div className="flex gap-4">',
        '<Frame>',
        '',
        images[1],
        '</Frame>',
        '',
        '<Frame>',
        '',
        images[4],
        '</Frame>',
        '</div>',
        '</Tab>',
        '<Tab title="侧边栏">',
        '<div className="flex gap-4">',
        '<Frame>',
        '',
        images[2],
        '</Frame>',
        '',
        '<Frame>',
        '',
        images[5],
        '</Frame>',
        '</div>',
        '</Tab>',
        '</Tabs>',
    ]

    return result, i


def fix_device_table(lines, start_idx):
    """
    修复「电脑端 | 手机端」类型的表格
    转换为并排 Frame（双列布局）
    """
    # 收集表格后的图片
    images = []
    i = start_idx + 2  # 跳过表头和分隔行

    while i < len(lines) and lines[i].strip().startswith('!['):
        images.append(lines[i].strip())
        i += 1

    if len(images) < 2:
        return None, i

    # 根据图片数量决定布局
    if len(images) == 2:
        result = [
            '<div className="flex gap-4">',
            '<div className="flex-1">',
            '<p className="text-center font-semibold mb-2">电脑端</p>',
            '<Frame>',
            '',
            images[0],
            '</Frame>',
            '</div>',
            '',
            '<div className="flex-1">',
            '<p className="text-center font-semibold mb-2">手机端</p>',
            '<Frame>',
            '',
            images[1],
            '</Frame>',
            '</div>',
            '</div>',
        ]
    elif len(images) == 4:
        result = [
            '<div className="flex gap-4">',
            '<div className="flex-1">',
            '<p className="text-center font-semibold mb-2">电脑端</p>',
            '<Frame>',
            '',
            images[0],
            '</Frame>',
            '',
            '<Frame>',
            '',
            images[2],
            '</Frame>',
            '</div>',
            '',
            '<div className="flex-1">',
            '<p className="text-center font-semibold mb-2">手机端</p>',
            '<Frame>',
            '',
            images[1],
            '</Frame>',
            '',
            '<Frame>',
            '',
            images[3],
            '</Frame>',
            '</div>',
            '</div>',
        ]
    else:
        return None, i

    return result, i


def fix_issue_table(lines, start_idx):
    """
    修复「序号 | 常见异常情况 | 问题原因&解决方法」表格
    转换为 Steps 组件
    """
    # 收集表格数据行
    data_rows = []
    i = start_idx + 2  # 跳过表头和分隔行

    while i < len(lines) and lines[i].strip().startswith('|'):
        row = lines[i].strip()
        cells = [c.strip() for c in row.split('|')[1:-1]]
        if len(cells) == 3:
            data_rows.append(cells)
        i += 1

    if not data_rows:
        return None, i

    result = ['<Steps>']

    for cells in data_rows:
        seq, image_cell, desc_cell = cells

        # 提取图片
        img_match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', image_cell)
        if not img_match:
            continue

        img_markdown = img_match.group(0)

        # 清理描述（去掉 <br /> 标签）
        desc_lines = desc_cell.replace('<br />', '\n').split('\n')

        result.append(f'<Step title="情况 {seq}">')
        result.append('<Frame>')
        result.append('')
        result.append(img_markdown)
        result.append('</Frame>')
        result.append('')

        for line in desc_lines:
            line = line.strip()
            if line:
                result.append(line)
                result.append('')

        result.append('</Step>')

    result.append('</Steps>')

    return result, i


def convert_tables(content: str) -> str:
    """转换所有表格"""
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测「手机端 | 电脑端 | 」三列表格（第一个特殊表格）
        if line.strip() == '| 手机端 | 电脑端 |  |':
            # 跳过这个表格（表头 + 分隔行 + 数据行）+ 后续图片
            i += 1  # 分隔行
            if i < len(lines) and '| --- |' in lines[i]:
                i += 1  # 数据行
            if i < len(lines) and lines[i].strip().startswith('| 工作台'):
                i += 1  # 跳过数据行
            # 跳过后续的图片
            while i < len(lines) and lines[i].strip().startswith('!['):
                i += 1
            # 不输出任何内容，直接跳过这个表格
            continue

        # 检测「入口 | 工作台 | OA审批」表格
        if line.strip() == '| 入口 | 工作台 | OA审批 |':
            converted, next_i = fix_entry_table(lines, i)
            if converted:
                result.extend(converted)
                i = next_i
                continue

        # 检测「工作台 | 工作台 | 侧边栏」表格
        if line.strip() == '| 工作台 | 工作台 | 侧边栏 |':
            converted, next_i = fix_entry_table(lines, i)
            if converted:
                result.extend(converted)
                i = next_i
                continue

        # 检测「电脑端 | 手机端」表格
        if line.strip() == '| 电脑端 | 手机端 |':
            converted, next_i = fix_device_table(lines, i)
            if converted:
                result.extend(converted)
                i = next_i
                continue

        # 检测「序号 | 常见异常情况 | 问题原因&解决方法」表格
        if '| 序号 | 常见异常情况 | 问题原因&解决方法 |' in line:
            converted, next_i = fix_issue_table(lines, i)
            if converted:
                result.extend(converted)
                i = next_i
                continue

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

    # 转换表格
    content = convert_tables(content)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ 已转换表格为组件")
    else:
        print(f"- 无需修改")


if __name__ == '__main__':
    main()
