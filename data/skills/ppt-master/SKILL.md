---
name: ppt-master
description: 显式离线生成新的可编辑 PowerPoint；仅支持 inline Markdown 或项目内 Markdown/TXT，不替代默认 pptx。
tools: create_ppt_master_deck
metadata: {"toolCapability":"offline-core"}
---

# PPT Master offline runtime pilot

本 Skill 只在用户通过 `/ppt-master` 或明确点名 `ppt-master` 时使用。普通“生成 PPT / 制作演示文稿”继续使用既有 `/pptx`；不要自动选择或替换默认 Skill。

## 唯一运行入口

调用 `create_ppt_master_deck`，并且只传以下两者之一：

- `markdown`：inline UTF-8 Markdown；
- `sourcePath`：当前项目根内的 `.md` / `.txt` 相对路径。

工具自行固定输出到当前 AgentRun 的 `output/ppt-master/<runId>/presentation.pptx`。不得要求或猜测 Skill/vendor 的绝对路径，不得传模块名、脚本、命令、URL 或输出目录。

Markdown 可使用 `##` 划分内容页、pipe table 生成原生表格，并用受限的 fenced `chart` CSV 生成原生图表。生成物包含可编辑文本、形状、表格和图表，不是整页截图。

## 首阶段边界

- 仅新建离线 free-design PPTX；输入上限 1 MiB，超限或过密内容应解释并停止。
- 禁止图片、模板/品牌/Icon/Sound、PDF/DOCX/XLSX 输入、已有 PPTX 编辑、Image-to-PPTX、动画、旁白、视频和本地预览服务。
- 禁止网络、Key / `.env`、用户目录、任意命令与外部供应商；不要调用 `run_command` 作为降级生成路径。
- 工具受 `file_mutation` 授权、固定 30 秒进程树取消、run-owned staging、原子发布和 AgentRun execution/result 去重保护。
- 若 `offline-core` 不 ready，Skill 的工具声明会被 Code 投影为不可用；不要自行安装、切换 Python 或绕过 receipt。

## 可复核资源

- `vendor-manifest.json`：固定仓库、tag、commit、tree、逐文件 SHA-256 与 Git blob OID。
- `EXCLUDED_CAPABILITIES.md`：明确没有进入包的能力和资产。
- `NOTICE.md` 与 `vendor/LICENSE`：上游及第三方 attribution 边界。

不得将这些静态资源解释为执行授权。后续阶段必须先通过 Code 自有完整性校验、依赖授权和运行时隔离门禁。
