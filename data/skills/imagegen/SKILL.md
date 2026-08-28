---
name: imagegen
description: 使用已配置的独立生成式图像模型创建新图片，或编辑当前 Session 中的一张参考图。适用于照片、插画、角色、场景和艺术视觉；不用于数据图表或 Pillow/matplotlib 的确定性处理。
keywords: 文生图, 生成+图片, 生成+图像, 创作+插画, 创建+海报, image+generation, text+to+image, edit+image
tools: generate_image
---

# 生成式图像

只使用 `generate_image` 完成生成式文生图或单参考图编辑，不调用脚本、命令、外部图像服务或文件写入工具。

- 新图：把用户的主题、构图、风格、文字要求和必要限制整理为准确 prompt，再调用一次 `generate_image`。
- 编辑：仅使用当前 Session 已提供的附件 identity，或先前 `generate_image` 返回的生成资产 ID；不要传本地路径、远程 URL、连接、Key 或 header。
- 数据图表、缩放、裁剪、拼接和基础标注属于 `image-generation` 的本地确定性工作流，不要用本 Skill 代替。
- 以工具的成功回执和资产元数据为准；不要虚构图片、链接或成功状态。失败或未配置独立生图连接时，准确说明错误且不要改用聊天连接。
