#!/usr/bin/env python3
"""
修复审批文档中表格包含图片导致内容挤压的问题
将「设置项（图）+ 名称 + 说明」三列表格转为 Steps 组件
"""

import re
from pathlib import Path


def convert_table_to_steps(content: str) -> str:
    """
    将包含图片的三列表格（设置项 | 名称 | 说明）转换为 Steps 组件

    表格模式：
    | 设置项 | 名称 | 说明 |
    | --- | --- | --- |
    | ![图片](url) | **撤销设置** | 允许发起人撤销... |
    |  |  | 允许发起人撤销... |  (合并行)

    转换为：
    <Steps>
    <Step title="撤销设置">
    <Frame>![图片](url)</Frame>

    允许发起人撤销...
    </Step>
    </Steps>
    """

    lines = content.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 检测表格开始（三列：设置项 | 名称 | 说明）
        if line.strip() == '| 设置项 | 名称 | 说明 |':
            # 收集整个表格
            table_lines = [line]
            i += 1

            # 跳过分隔行
            if i < len(lines) and re.match(r'\|\s*---\s*\|', lines[i]):
                table_lines.append(lines[i])
                i += 1

            # 收集所有表格行
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1

            # 转换表格
            steps_content = convert_single_table(table_lines)
            result.append(steps_content)
            continue

        result.append(line)
        i += 1

    return '\n'.join(result)


def convert_single_table(table_lines: list) -> str:
    """
    转换单个表格为：图片 + AccordionGroup 组件

    原表格：一个图标对应多个功能设置
    新结构：
    - 图片外置（<Frame>）
    - 每个功能一个 Accordion
    """

    if len(table_lines) < 3:  # 至少需要表头 + 分隔 + 一行数据
        return '\n'.join(table_lines)

    # 解析数据行（跳过表头和分隔行）
    data_rows = table_lines[2:]

    items = []
    current_item = None
    table_image = None  # 整个表格共用的图片

    for row in data_rows:
        # 解析表格列
        cells = [c.strip() for c in row.split('|')[1:-1]]  # 去掉首尾空列

        if len(cells) != 3:
            continue

        icon_cell, name_cell, desc_cell = cells

        # 如果第一列有图片，提取图片（整个表格只用一次）
        if icon_cell and '![' in icon_cell and not table_image:
            img_match = re.search(r'!\[([^\]]*)\]\(([^\)]+)\)', icon_cell)
            table_image = img_match.group(0) if img_match else ''

        # 如果第二列有加粗标题，说明是新的功能项
        if name_cell and '**' in name_cell:
            # 保存上一个 item
            if current_item:
                items.append(current_item)

            # 提取标题
            title = name_cell.replace('**', '').strip()

            # 开始新的 item
            current_item = {
                'title': title,
                'content': [desc_cell] if desc_cell else []
            }

        # 如果前两列都为空，第三列有内容，说明是合并行
        elif not icon_cell and not name_cell and desc_cell:
            if current_item:
                current_item['content'].append(desc_cell)

    # 保存最后一个 item
    if current_item:
        items.append(current_item)

    # 生成新结构
    if not items:
        return '\n'.join(table_lines)

    result = []

    # 添加图片（如果有）
    if table_image:
        result.append('<Frame>')
        result.append('')
        result.append(table_image)
        result.append('</Frame>')
        result.append('')

    # 添加 AccordionGroup
    result.append('<AccordionGroup>')

    for item in items:
        result.append(f'<Accordion title="{item["title"]}">')
        result.append('')

        # 添加内容（用换行分隔多个段落）
        for content in item['content']:
            # 将 <br /> 替换为真正的换行
            content_lines = content.replace('<br />', '\n').split('\n')
            for line in content_lines:
                line = line.strip()
                if line:
                    result.append(line)
                    result.append('')

        result.append('</Accordion>')

    result.append('</AccordionGroup>')

    return '\n'.join(result)


def process_file(file_path: Path):
    """处理单个文件"""
    print(f"处理文件: {file_path}")

    content = file_path.read_text(encoding='utf-8')
    original = content

    # 转换表格
    content = convert_table_to_steps(content)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"  ✓ 已转换表格为 Steps 组件")
        return True
    else:
        print(f"  - 无需修改")
        return False


def main():
    """主函数"""
    approval_dir = Path(__file__).parent.parent / 'zh' / 'approval'

    if not approval_dir.exists():
        print(f"错误：目录不存在 {approval_dir}")
        return

    # 只处理包含表格+图片的文件
    target_file = approval_dir / 'admin-advanced-settings.mdx'

    if not target_file.exists():
        print(f"错误：文件不存在 {target_file}")
        return

    modified = process_file(target_file)

    if modified:
        print("\n✓ 完成！已将表格转换为 Steps 组件")
    else:
        print("\n- 文件无需修改")


if __name__ == '__main__':
    main()
