# PPT Master static exclusion boundary

本文件记录 `code049-ppt-master-static-coexist` 阶段的否定能力清单。`vendor-manifest.json` 是逐文件事实源；本清单不授权任何运行行为。

以下上游能力和资源没有进入静态包：

- 自动更新、Git pull、pip 安装与上游 attribution guard 执行入口；
- `config.py`、`.env` 搜索、环境变量 Key 与用户主目录配置；
- 网络请求、网页转换、图片搜索/生成/下载及所有外部 provider；
- TTS、音频、旁白、视频、动画与 PowerPoint 视频导出；
- Confirm UI、SVG Editor、本地 Flask 服务、端口、浏览器打开和 detached 子进程；
- Image-to-PPTX、Beautify、Edit Native PPTX 与模板创建工作流；
- brands、icons、sounds、decks、AI image comparison 与其他模板库资产。

静态包只保留离线 DrawingML/native object 原语、OPC 校验原语、设计 schema/scaffold、固定许可与 attribution 文件。它不包含 CLI、builder、路由或服务入口，因此不能生成 PPTX。
