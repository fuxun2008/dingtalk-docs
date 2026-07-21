#!/usr/bin/env python3
"""
批量修复审批文档中的表格图片问题

修复策略:
1. 表格后堆积图片（破碎表格）→ 根据表头判断转换方式
2. 单元格内图片 → 提取图片，转为合适的组件结构
"""

import re
from pathlib import Path


def detect_table_type(header: str) -> str:
    """
    根据表头判断表格类型
    返回: 'device_compare' | 'feature_demo' | 'config_table' | 'unknown'
    """
    # 设备对比表格（电脑端 vs 手机端 / 操作人 vs 手机端 vs 电脑端）
    if '电脑端' in header and '手机端' in header:
        return 'device_compare'

    # 场景演示表格（场景 | 输入示例 | 输出效果）
    if '场景' in header and ('输入示例' in header or '输入' in header):
        return 'feature_demo'

    # 分条件字段表格
    if '分条件字段' in header or '分条件设置' in header:
        return 'branch_control'

    # 配置属性表格（类别 | 详情）
    if '类别' in header and '详情' in header:
        return 'config_table'

    # 属性样式表格（属性 | 样式 | 说明）
    if '属性' in header and '样式' in header:
        return 'style_table'

    return 'unknown'


def fix_device_compare_table(lines, start_idx):
    """
    修复设备对比表格
    转换为双列布局
    """
    # 跳过表头和分隔行
    i = start_idx + 2

    # 收集图片
    images = []
    while i < len(lines) and lines[i].strip().startswith('!['):
        images.append(lines[i].strip())
        i += 1

    if not images:
        return None, i

    # 判断是 2 列还是 3 列
    header = lines[start_idx].strip()
    cols = len([c for c in header.split('|') if c.strip()])

    if cols == 3:  # 操作人 | 手机端 | 电脑端
        # 按 3 列布局
        result = ['<div className="flex gap-4">']

        # 每列的图片
        col_count = 3
        for col_idx in range(col_count):
            result.append('<div className="flex-1">')
            col_name = ['操作人', '手机端', '电脑端'][col_idx] if col_idx < 3 else ''
            if col_name:
                result.append(f'<p className="text-center font-semibold mb-2">{col_name}</p>')

            # 该列的图片（每 col_count 张一组）
            for img_idx in range(col_idx, len(images), col_count):
                result.append('<Frame className="mb-4">')
                result.append('')
                result.append(images[img_idx])
                result.append('</Frame>')
                result.append('')

            result.append('</div>')
            result.append('')

        result.append('</div>')
        return result, i

    elif cols == 2:  # 电脑端 | 手机端
        # 双列布局
        result = ['<div className="flex gap-4">']

        for col_idx, col_name in enumerate(['电脑端', '手机端']):
            result.append('<div className="flex-1">')
            result.append(f'<p className="text-center font-semibold mb-2">{col_name}</p>')

            # 该列的图片（偶数/奇数索引）
            for img_idx in range(col_idx, len(images), 2):
                result.append('<Frame className="mb-4">')
                result.append('')
                result.append(images[img_idx])
                result.append('</Frame>')
                result.append('')

            result.append('</div>')
            result.append('')

        result.append('</div>')
        return result, i

    return None, i


def fix_feature_demo_table(lines, start_idx):
    """
    修复场景演示表格（场景 | 输入示例 | 输出效果）
    转换为 Steps 组件
    """
    i = start_idx + 2

    # 收集图片
    images = []
    while i < len(lines) and lines[i].strip().startswith('!['):
        images.append(lines[i].strip())
        i += 1

    if not images:
        return None, i

    # 每 3 张图为一组（场景、输入、输出）
    result = ['<Steps>']

    for idx in range(0, len(images), 3):
        step_num = idx // 3 + 1
        result.append(f'<Step title="场景 {step_num}">')

        # 添加这一组的图片
        for img_idx in range(idx, min(idx + 3, len(images))):
            result.append('<Frame className="mb-4">')
            result.append('')
            result.append(images[img_idx])
            result.append('</Frame>')
            result.append('')

        result.append('</Step>')

    result.append('</Steps>')
    return result, i


def fix_branch_control_table(lines, start_idx):
    """
    修复分条件控制表格
    转换为 Tabs 组件（每 2 张图一个 Tab）
    """
    i = start_idx + 2

    # 收集图片
    images = []
    while i < len(lines) and lines[i].strip().startswith('!['):
        images.append(lines[i].strip())
        i += 1

    if not images:
        return None, i

    result = ['<Tabs>']

    # 每 2 张图一个 Tab
    for idx in range(0, len(images), 2):
        tab_num = idx // 2 + 1
        result.append(f'<Tab title="条件 {tab_num}">')
        result.append('<div className="flex gap-4">')

        for img_idx in range(idx, min(idx + 2, len(images))):
            result.append('<Frame className="mb-4">')
            result.append('')
            result.append(images[img_idx])
            result.append('</Frame>')
            result.append('')

        result.append('</div>')
        result.append('</Tab>')

    result.append('</Tabs>')
    return result, i


def fix_config_table(lines, start_idx):
    """
    修复配置表格（类别 | 详情）
    简单展示，不转换结构，只为图片添加 Frame
    """
    i = start_idx + 2

    # 收集图片
    images = []
    while i < len(lines) and lines[i].strip().startswith('!['):
        images.append(lines[i].strip())
        i += 1

    if not images:
        return None, i

    result = []
    for img in images:
        result.append('<Frame className="mb-4">')
        result.append('')
        result.append(img)
        result.append('</Frame>')
        result.append('')

    return result, i


def fix_table_with_images(content: str) -> str:
    """修复所有表格图片问题"""
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测表头
        if line.strip().startswith('|') and line.strip().endswith('|') and '---' not in line:
            # 检查是否是表格（下一行是分隔行）
            if i + 1 < len(lines) and '| ---' in lines[i + 1]:
                # 检查表格后是否有堆积的图片
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith('|'):
                    j += 1

                # 如果表格后有图片，说明是破碎表格
                if j < len(lines) and lines[j].strip().startswith('!['):
                    table_type = detect_table_type(line)
                    converted = None
                    next_i = j

                    if table_type == 'device_compare':
                        converted, next_i = fix_device_compare_table(lines, i)
                    elif table_type == 'feature_demo':
                        converted, next_i = fix_feature_demo_table(lines, i)
                    elif table_type == 'branch_control':
                        converted, next_i = fix_branch_control_table(lines, i)
                    elif table_type in ['config_table', 'style_table']:
                        converted, next_i = fix_config_table(lines, i)

                    if converted:
                        result.extend(converted)
                        i = next_i
                        continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def fix_inline_image_table(content: str) -> str:
    """
    修复表格单元格内的图片
    策略：将图片提取出来，放在表格后
    """
    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测包含图片的表格行
        if line.strip().startswith('|') and '![' in line:
            # 提取图片
            images = re.findall(r'!\[([^\]]*)\]\(([^\)]+)\)', line)

            if images:
                # 保留表格行但移除图片
                clean_line = re.sub(r'!\[([^\]]*)\]\(([^\)]+)\)', '', line)
                result.append(clean_line)

                # 跳过后续的表格行
                i += 1
                while i < len(lines) and lines[i].strip().startswith('|'):
                    result.append(lines[i])
                    i += 1

                # 在表格后添加提取的图片
                result.append('')
                for alt, url in images:
                    result.append('<Frame className="mb-4">')
                    result.append('')
                    result.append(f'![{alt}]({url})')
                    result.append('</Frame>')
                    result.append('')

                continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def process_file(file_path: Path) -> bool:
    """处理单个文件"""
    content = file_path.read_text(encoding='utf-8')
    original = content

    # 1. 修复表格后堆积图片
    content = fix_table_with_images(content)

    # 2. 修复单元格内图片
    content = fix_inline_image_table(content)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True

    return False


def main():
    """主函数"""
    approval_dir = Path(__file__).parent.parent / 'zh' / 'approval'

    # 待修复的文件列表（从扫描报告得出）
    target_files = [
        'admin-controls.mdx',
        'admin-process-design.mdx',
        'ai-controls.mdx',
        'ai-fill-form.mdx',
        'conditional-branch-controls.mdx',
        'operation-interface.mdx',
        'operator-guide.mdx',
    ]

    print("开始批量修复审批文档表格图片问题...")
    print()

    fixed_count = 0
    for filename in target_files:
        file_path = approval_dir / filename
        if not file_path.exists():
            print(f"⚠️  文件不存在: {filename}")
            continue

        print(f"处理: {filename}")
        if process_file(file_path):
            print(f"  ✓ 已修复")
            fixed_count += 1
        else:
            print(f"  - 无需修改")

    print()
    print(f"完成！共修复 {fixed_count}/{len(target_files)} 个文件")


if __name__ == '__main__':
    main()
