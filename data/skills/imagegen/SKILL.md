---
name: imagegen
description: 使用独立生成式图像模型创建新图片，或编辑当前 Session/受控工作区中的一张参考图；可按用户明确要求转存或重命名生成资产。适用于照片、插画、角色、场景和艺术视觉；不用于数据图表或确定性本地图像处理。
allowed-tools: generate_image, manage_generated_image
metadata:
  keywords: 文生图, 生成+图片, 生成+图像, 创作+插画, 创建+海报, image+generation, text+to+image, edit+image
  tools: generate_image, manage_generated_image
---

# 生成式图像

使用 `generate_image` 完成生成式文生图或单参考图编辑；仅当用户明确要求转存或重命名时，使用 `manage_generated_image`。不调用脚本、命令、外部图像服务或通用文件写入工具。

“一次调用”按明确阶段计算，而不是整个复杂任务终身一次：先生成、再基于权威资产回执编辑属于两个阶段，每个阶段各调用一次。首次成功回执的 `assetId` 可在同一 AgentRun 后续 round，或同 Session 的后续 AgentRun 中作为 `generated_asset` reference；后续编辑默认 `count=1`。

- 新图：把用户的主题、构图、风格、文字、视角、光线和必要限制整理成准确 prompt，再调用一次 `generate_image`。默认且未明确数量时必须 `count=1`；只有当前用户消息明确要求 2–4 张/版本时，才在一次工具调用中传对应 `count`。模糊的“多张/多个版本”先询问确切数量；4K、尺寸和历史消息中的数字都不是本次数量。
- 编辑：在 prompt 中明确保留与改变的内容；reference 仅使用当前 Session 已提供的附件 identity、先前 `generate_image` 返回的生成资产 ID，或当前项目 `output/generated-images` 内已验证的 workspace image identity。存在多个候选而用户未明确指定时先询问，不要猜测“最后一张”。不要传远程 URL、连接、Key、header 或其他本地路径。
- 不传 `size`、`quality` 或 `outputFormat`；把视觉质量、比例意图和构图要求写进 prompt，供应商执行参数由运行时管理。
- 成功资产由运行时自动校验并在对话 gallery 展示。回答中不制作预览表、不猜测缓存或桌面路径。同 Session 二次编辑直接使用 `generated_asset`，不要求先转存；只有跨 Session、重命名或工作区文件处理且用户明确要求时才调用一次 `manage_generated_image`。只有其权威成功回执中的完整绝对路径可作为可点击本地链接。
- 数据图表、缩放、裁剪、拼接和基础标注属于 `image-generation` 的本地确定性工作流，不要用本 Skill 代替。
- 以工具的成功回执和资产元数据为准；不要虚构图片、链接或成功状态。不要在同一阶段循环同一 prompt，也不要为备选版本自行推断 `count>1`。批次部分成功时如实报告已成功与失败的数量及现有资产，不自行补生成。失败、结果未知或未配置独立生图连接时立即停止，不在同一 AgentRun 重试，也不要改用聊天连接。
