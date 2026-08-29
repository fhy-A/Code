---
name: ppt-master
description: PPT Master v5.1.0 的固定静态共存包；仅供显式供应链与适配审查，本阶段不可执行。
---

# PPT Master static coexistence package

`STATIC_ONLY_DO_NOT_EXECUTE`

本包只在用户通过 `/ppt-master` 或明确点名 `ppt-master` 时进入上下文。普通“生成 PPT / 制作演示文稿”继续使用既有 `/pptx`，不得自动选择本包。

## 当前阶段边界

- 这是固定来源的静态准入基线，不是可运行的 PPT 生成器。
- 即使依赖检查显示部分组件已存在，也不得 import、运行或调用 `vendor/` 中的任何 Python 文件。
- 不得搜索或猜测 Skill 的绝对目录，不得把 vendor 路径加入 `PYTHONPATH`，不得建立兼容降级入口。
- 不得安装依赖、启动服务、访问网络、读取 Key / `.env`、读取用户目录或调用模型、图片与语音供应商。
- 本阶段没有执行入口；用户请求实际生成或转换时，说明 `offline-core` 仍缺少 `skia-pathops` 与 `uharfbuzz`，并等待新的运行时适配授权。

## 可复核资源

- `vendor-manifest.json`：固定仓库、tag、commit、tree、逐文件 SHA-256 与 Git blob OID。
- `EXCLUDED_CAPABILITIES.md`：明确没有进入包的能力和资产。
- `NOTICE.md` 与 `vendor/LICENSE`：上游及第三方 attribution 边界。

不得将这些静态资源解释为执行授权。后续阶段必须先通过 Code 自有完整性校验、依赖授权和运行时隔离门禁。
