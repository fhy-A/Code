---
name: image-generation
description: 使用 matplotlib 生成数据图表，或用 Pillow 对已有图片做缩放、裁剪、拼接和基础标注。这是本地确定性绘图/处理工作流，不是文生图或生成式 AI 图像模型。
allowed-tools: list_files, read_file, glob_files, manage_generated_image, write_file, run_command
metadata:
  keywords: matplotlib, pillow, 数据+可视化, 画+图表, 生成+图表, 柱状图, 折线图, 饼图, 散点图, chart, data+plot
  tools: list_files, read_file, glob_files, manage_generated_image, write_file, run_command
---

# 数据图表与基础图片处理

## 能力边界

- 适用：柱状图、折线图、散点图、分布图、小型仪表盘和基础像素操作。
- 不适用：从自然语言创作照片、插画、角色、场景或艺术海报。对这类请求说明需要生成式图像工具，不用 matplotlib 伪装成 AI 生图。
- 用户只要数据分析时，不为了触发 Skill 强制生成图片。

## 工作流程

1. 确认数据或图片来源、字段含义、单位、缺失值和用户要表达的关系。
2. 如果输入是当前 Session 中 `generate_image` 的历史资产，只使用原工具回执提供的权威 `assetId`，先调用 `manage_generated_image` 经既有授权分别转存到当前项目 `output/generated-images`，再对成功回执中的工作区路径执行本地处理。不得猜测内部缓存路径，也不得要求用户查找、粘贴或从图片卡片读取 ID；多个候选按用户语义和回执顺序处理，真正不明确时只询问“哪张/哪几张”。
3. 选择最简单能回答问题的图表或像素操作，不默认使用饼图、双轴或装饰性 3D。
4. 首次使用时确认 `matplotlib` / `PIL` 可导入；使用 `matplotlib.use('Agg')`，禁止 `input()`、`plt.show()` 和其他交互/阻塞调用。
5. 输出路径优先使用用户指定值。未指定时，如项目已有 `output/` 则使用它，否则使用项目根目录中的明确英文文件名。
6. 输出后检查文件存在、尺寸、格式和大小；能视觉检查时确认文字、图例、轴标签和颜色对比。

## matplotlib 规则

- 明确设置画布尺寸、`tight_layout()` 和导出 DPI（通常 144–180）。
- 中文标签前先检查本地字体；可优先尝试 `Microsoft YaHei`、`SimHei`，不能保证时提醒用户可能缺字。
- 使用色盲友好且背景对比充足的色板，不只靠颜色区分关键系列。
- 保留原始数值精度，轴范围、截断和聚合不得造成误导。

简短图表可使用 `python -c` 生成；超过命令长度或需要复现时，用 `write_file` 创建清晰的 Python 脚本，运行验证后根据用户要求保留或删除。

## Pillow 规则

- 读取前确认源文件和模式，保留用户需要的 alpha 通道、ICC/EXIF 方向和尺寸。
- 默认输出新文件，不覆盖原图；覆盖必须是用户明确意图。
- 缩放使用高质量采样，JPEG 明确质量，需要透明时使用 PNG/WebP。

交付时给出生成文件的完整路径、尺寸/格式和实际验证结果。
