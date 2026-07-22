#!/usr/bin/env python3
"""
修复场景演示类表格的语义问题
将垂直堆叠的 Steps 改为横向对比的 Steps（每个 Step 包含一行的3张对比图）
"""

import re
from pathlib import Path


def fix_ai_controls(file_path: Path) -> bool:
    """修复 ai-controls.mdx"""
    content = file_path.read_text(encoding='utf-8')
    original = content

    # 定位到需要修复的 Steps 区域
    # 每3张图为一组：场景 | 输入示例 | 输出效果

    replacement = """输出：面向审批人输出结论

<Steps>
<Step title="场景 1：请假申请分析">
<div className="flex gap-4">
<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">场景</p>
<Frame>

![截屏2025-12-02 10.39.02.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/492bb9e8-ea2a-40b6-ac73-de03eb6c0643.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输入示例</p>
<Frame>

![截屏2025-12-02 10.43.50.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/4809e7b7-01f9-44e7-a023-9eab7c708add.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输出效果</p>
<Frame>

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/ac1ab9d0-0eed-4006-b0a7-9e6970311111.png)
</Frame>
</div>
</div>
</Step>

<Step title="场景 2：合同审批分析">
<div className="flex gap-4">
<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">场景</p>
<Frame>

![截屏2025-12-02 11.06.49.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/62ae5a56-0c7d-46e5-8747-07180eed5983.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输入示例</p>
<Frame>

![截屏2025-12-02 11.08.02.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/7328e688-b517-43f6-a01e-fdef68d0580b.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输出效果</p>
<Frame>

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/c60bf8d4-ca6d-4246-a79f-8166d496773a.png)
</Frame>
</div>
</div>
</Step>

<Step title="场景 3：费用报销分析">
<div className="flex gap-4">
<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">场景</p>
<Frame>

![截屏2025-12-02 11.10.12.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/3c61345a-4ce7-4f17-8133-7a261fc1c26e.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输入示例</p>
<Frame>

![截屏2025-12-02 11.12.42.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/17348500-6505-45d5-93b2-f1e5565df1f1.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输出效果</p>
<Frame>

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/25ade518-a4b3-4df5-8219-9c5e89f54235.png)
</Frame>
</div>
</div>
</Step>

<Step title="场景 4：采购申请分析">
<div className="flex gap-4">
<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">场景</p>
<Frame>

![截屏2025-12-02 11.41.34.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/6abbf260-cc17-4a93-801f-33e4bc7baa74.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输入示例</p>
<Frame>

![截屏2025-12-02 11.43.21.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/fc1525ce-6cac-4057-b325-474b9c3a8881.png)
</Frame>
</div>

<div className="flex-1">
<p className="text-center text-sm font-semibold mb-2">输出效果</p>
<Frame>

![image.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/yBRq1ZPyX12BWOdv/img/3f557e1f-e699-487b-aedb-0a132e59eb97.png)
</Frame>
</div>
</div>
</Step>
</Steps>"""

    # 查找并替换
    pattern = r'输出：面向审批人输出结论\n\n<Steps>.*?</Steps>'
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    if content != original:
        file_path.write_text(content, encoding='utf-8')
        return True

    return False


def main():
    """主函数"""
    approval_dir = Path(__file__).parent.parent / 'zh' / 'approval'

    files_to_fix = {
        'ai-controls.mdx': fix_ai_controls,
    }

    print("修复场景演示表格的语义问题...")
    print()

    for filename, fix_func in files_to_fix.items():
        file_path = approval_dir / filename
        if not file_path.exists():
            print(f"⚠️  文件不存在: {filename}")
            continue

        print(f"处理: {filename}")
        if fix_func(file_path):
            print(f"  ✓ 已修复")
        else:
            print(f"  - 无需修改")

    print()
    print("完成！")


if __name__ == '__main__':
    main()
