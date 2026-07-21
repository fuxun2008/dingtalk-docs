#!/usr/bin/env python3
"""
全面扫描和分析审批文档中的表格图片问题
生成修复报告，标记需要处理的文件
"""

import re
from pathlib import Path
from collections import defaultdict


def analyze_table_with_images(file_path: Path) -> dict:
    """
    分析文件中的表格图片情况
    返回: {
        'has_issue': bool,
        'tables': [
            {
                'line': int,
                'header': str,
                'type': 'image_in_cell' | 'image_after_table',
                'image_count': int
            }
        ]
    }
    """
    content = file_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    result = {
        'has_issue': False,
        'tables': []
    }

    i = 0
    while i < len(lines):
        line = lines[i]

        # 检测表头
        if line.strip().startswith('|') and line.strip().endswith('|') and '---' not in line:
            table_header = line.strip()

            # 检查这是否是表头（下一行是分隔行）
            if i + 1 < len(lines) and '| ---' in lines[i + 1]:
                # 这是一个表格
                table_info = {
                    'line': i + 1,
                    'header': table_header,
                    'type': None,
                    'image_count': 0
                }

                # 检查表格数据行是否包含图片
                j = i + 2
                has_image_in_cell = False
                images_after = []

                # 检查表格行
                while j < len(lines) and lines[j].strip().startswith('|'):
                    if '![' in lines[j]:
                        has_image_in_cell = True
                        table_info['image_count'] += 1
                    j += 1

                # 检查表格后紧跟的图片（破碎表格）
                while j < len(lines) and lines[j].strip().startswith('!['):
                    images_after.append(lines[j].strip())
                    j += 1

                if has_image_in_cell:
                    table_info['type'] = 'image_in_cell'
                    result['has_issue'] = True
                    result['tables'].append(table_info)
                elif images_after:
                    table_info['type'] = 'image_after_table'
                    table_info['image_count'] = len(images_after)
                    result['has_issue'] = True
                    result['tables'].append(table_info)

        i += 1

    return result


def main():
    """主函数"""
    approval_dir = Path(__file__).parent.parent / 'zh' / 'approval'

    if not approval_dir.exists():
        print(f"错误：目录不存在 {approval_dir}")
        return

    print("=" * 80)
    print("审批文档表格图片问题扫描报告")
    print("=" * 80)
    print()

    issue_files = []
    stats = defaultdict(int)

    for mdx_file in sorted(approval_dir.glob('*.mdx')):
        analysis = analyze_table_with_images(mdx_file)

        if analysis['has_issue']:
            issue_files.append((mdx_file.name, analysis))

            for table in analysis['tables']:
                stats[table['type']] += 1

    # 打印统计
    print(f"扫描文件总数: {len(list(approval_dir.glob('*.mdx')))}")
    print(f"有问题的文件: {len(issue_files)}")
    print()
    print("问题类型统计:")
    print(f"  - 表格单元格内有图片: {stats['image_in_cell']} 处")
    print(f"  - 表格后堆积图片（破碎表格）: {stats['image_after_table']} 处")
    print()
    print("=" * 80)
    print()

    # 打印详细报告
    for filename, analysis in issue_files:
        print(f"📄 {filename}")
        print(f"   问题表格数: {len(analysis['tables'])}")

        for idx, table in enumerate(analysis['tables'], 1):
            type_desc = {
                'image_in_cell': '单元格内图片',
                'image_after_table': '表格后堆积图片'
            }[table['type']]

            print(f"   [{idx}] 第 {table['line']} 行 - {type_desc} ({table['image_count']} 张)")
            print(f"       表头: {table['header'][:60]}...")

        print()

    # 已修复的文件
    fixed_files = ['admin-advanced-settings.mdx', 'initiator-guide.mdx']

    print("=" * 80)
    print("修复建议:")
    print("=" * 80)
    print()
    print("✅ 已修复文件:")
    for f in fixed_files:
        print(f"   - {f}")
    print()

    need_fix = [f for f, _ in issue_files if f not in fixed_files]

    if need_fix:
        print(f"⚠️  待修复文件 ({len(need_fix)} 个):")
        for f in need_fix:
            print(f"   - {f}")
        print()
        print("建议修复优先级:")
        print("   1. 高频访问文档: quick-start, operator-guide, admin-guide-overview")
        print("   2. 控件配置文档: admin-controls, ai-controls, conditional-branch-controls")
        print("   3. 其他文档")
    else:
        print("🎉 所有文件已修复完成！")


if __name__ == '__main__':
    main()
