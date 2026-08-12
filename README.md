<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/code-logo-white.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/code-logo-black.svg">
    <img src="assets/code-logo-black.svg" width="88" height="88" alt="Code Logo">
  </picture>
</p>

<h1 align="center">Code</h1>

<p align="center"><strong>本地 Web 服务 · AI Coding Agent</strong></p>
<p align="center">让 AI 真正进入你的项目，而不是停在对话框里。</p>

<p align="center">
  <a href="https://github.com/fhy-A/Code/releases/latest"><img src="https://img.shields.io/badge/version-0.6.1-2563EB" alt="Version 0.5.30"></a>
  <img src="https://img.shields.io/badge/platform-Windows-0078D4" alt="Windows">
  <img src="https://img.shields.io/badge/python-3.12+-3776AB" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/tests-842%20passed-16A34A" alt="842 tests passed">
  <a href="docs/LICENSE"><img src="https://img.shields.io/badge/license-MIT-6B7280" alt="MIT License"></a>
</p>

---

## 项目简介

Code 是一个运行在本机的 AI 编程 Agent。它以浏览器作为交互界面，通过 OpenAI 兼容 API 接入模型，并在用户选定的项目目录中读取文件、搜索代码、执行命令、修改内容和验证结果。

它不是 IDE 插件，也不是只能生成代码片段的聊天页面。一次任务可以从理解项目开始，经过多轮工具调用、测试和修复，最终把结果直接落到真实工作区。

Code 当前聚焦三个目标：

- **项目上下文**：围绕完整目录、依赖关系和历史会话工作，而不是只理解粘贴进来的片段。
- **持续执行**：任务由本地服务承载；刷新页面、切换会话或新建会话不会打断其他正在运行的任务。
- **可见且可控**：文件修改、命令结果、结构化问卷和最终回答都保留在会话中，用户可以随时停止、确认或继续调整。

## 核心能力

| 领域 | 当前能力 |
|---|---|
| 项目理解 | 文件树、全文搜索、跨文件关联、项目记忆、长对话上下文压缩 |
| 文件操作 | 读取、创建、编辑、目录管理、备份与项目外路径处理 |
| 命令执行 | PowerShell、Git、Python、Node 等本地命令，带超时与输出回传 |
| Agent 循环 | 多轮“分析 → 工具 → 验证 → 回答”，单任务最多 200 轮工具交互 |
| 后台任务 | 服务端运行任务、SSE 流式输出、刷新续接、多会话并行与独立停止 |
| 文件预览 | 图片、Markdown、PDF、CSV、TSV 以及常见文本和代码文件 |
| 图片输入 | 粘贴、拖拽、路径引用，以及工具读取图片后的视觉模型续轮 |
| 结构化交互 | 单选、多选、补充输入、风险确认等任务内问卷 |
| 会话系统 | JSONL 持久化、分支会话、层级索引、异常恢复和历史导出 |
| Skills | Markdown 技能、渐进式说明加载、资源读取及内置办公/设计工具包 |
| 通知 | 断网重试、任务完成、待确认和问卷通知 |
| 界面 | 中英双语、浅色/深色/跟随系统主题、托盘常驻和响应式布局 |

## 工作方式

```text
浏览器界面
    │  会话、SSE、问卷、文件预览
    ▼
本地 Python 服务（127.0.0.1:3010）
    ├── 模型任务运行时与会话持久化
    ├── 文件 / 搜索 / 命令 / Git 工具
    └── OpenAI 兼容代理
              │
              ▼
          workbar API 网关
```

前端负责展示与交互，本地服务负责模型请求、任务状态、会话数据和工具执行。模型 API Key 只用于请求，不写入持久化的任务运行状态。

服务端现已具备独立的持久化 AgentRun：“只读分析”“计划”“接受编辑”和“自动”四种权限的新任务均由服务端连续完成模型请求与允许的工具调用，浏览器只负责流式展示、问卷和授权决定；自动模式按既有产品语义直接执行允许的操作，不弹出授权。AgentRun 协议支持项目读取、网络、Skills、命令、项目记忆、编辑提案、直接文件变更和子任务。每个 `task` 会创建独立持久 Child AgentRun，继承父任务模型、权限和工具策略但不能再次委派或打开问卷；同一模型轮次最多并发运行 3 个子任务，超出的调用排队，最终工具结果仍按模型原始调用顺序回填。子任务授权由父任务统一展示和提交，父任务取消会同步停止子任务，服务重启后按原子任务 ID 复用结果和用量。同一会话在主任务输出期间再次发送的消息也会创建独立持久 AgentRun，与主任务分别保存状态、用量和结果，不会相互打断；刷新或服务重启后按稳定请求 ID 重新附着，而不会重复创建上游任务。页面关闭后任务仍可恢复，重新打开时会按 `agentRunId + 事件游标` 续接；服务重启后则等待前端重新注入内存态凭据。详见[服务端 Agent 循环迁移计划](docs/SERVER_AGENT_LOOP_PLAN.md)。

## 快速开始

### Windows 单文件版

1. 从 [GitHub Releases](https://github.com/fhy-A/Code/releases/latest) 下载 `Code-v0.6.1.exe`。
2. 双击运行。Code 会常驻系统托盘，并打开 `http://127.0.0.1:3010/`。
3. 按页面提示登录 workbar；Code 会同步账号下的 API Key 并刷新可用模型。
4. 选择一个项目目录，在输入框中直接描述任务。模型服务地址固定为 `https://workbar.ai`。

> v0.5.4 是首次使用 Code 名称发布的版本。旧版测试用户请退出 Agent Lite 后重新下载；首次运行会迁移原有用户数据与浏览器设置。

### 从源码运行

环境要求：Windows、Python 3.12+；托盘功能依赖 `pystray` 和 `Pillow`。

```powershell
git clone https://github.com/fhy-A/Code.git
Set-Location Code

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pystray pillow pytest

python server.py
```

直接运行 `python server.py` 仅作为占用 3010 的命令行调试入口。日常源码开发建议使用下方独立的 3011 开发实例。源码模式默认把运行数据保存在仓库的 `data/` 中；正式 EXE 使用用户目录下的 `.code/`。

### 同时运行正式版与开发版

需要使用正式发布版 Code 开发当前源码时，请通过 `启动Code开发版.bat` 或指向该脚本的 `Code Dev.lnk` 启动开发实例：

| 实例 | 入口 | 地址 | 数据目录 | 界面与托盘标识 |
|---|---|---|---|---|
| 正式版 | `Code-v*.exe` / `Code.lnk` | `http://127.0.0.1:3010/` | `%USERPROFILE%\.code\` | `Code` |
| 开发版 | `dev_server.py` / `启动Code开发版.bat` | `http://127.0.0.1:3011/` | `<项目>/data` | `Code Dev` |

两套实例可以同时运行，进程、端口、数据和重启入口彼此隔离。3010 与 3011 属于不同浏览器来源，因此 workbar 登录态和浏览器本地保存的 Key 配置也分别维护；在一个端口登录或修改设置不会自动同步到另一个端口。

打包后的正式版始终使用 3010 和正式版标识，不受启动开发版时设置的环境变量影响。需要临时调整开发实例时，可使用 `CODE_DEV_PORT` 和 `CODE_DEV_DATA_DIR`，无需修改正式发布配置。

## 模型与项目配置

首次启动后打开设置：

1. **Base URL**：填写 New API 或其他 OpenAI 兼容网关地址；本地开发默认值为 `http://localhost:3000`。
2. **API Keys**：可以添加多枚 Key，并为每枚 Key 关联可用模型。
3. **项目目录**：选择 Code 可以工作的项目根目录。
4. **模型与推理强度**：在输入区选择本次任务使用的模型和参数。

可用环境变量：

| 变量 | 作用 | 默认值 |
|---|---|---|
| `CODE_PORT` | 源码服务端口；打包正式版固定使用 3010 | `3010` |
| `CODE_DATA_DIR` | 源码模式的数据目录 | `<项目>/data` |
| `CODE_DEV_PORT` | 独立开发实例端口 | `3011` |
| `CODE_DEV_DATA_DIR` | 独立开发实例数据目录 | `<项目>/data` |
| `NEW_API_BASE_URL` | 服务端默认模型网关 | `http://localhost:3000` |

## 数据与隐私

正式 EXE 的用户数据位于 `%USERPROFILE%\.code\`：

```text
.code/
├── config.json          # 项目目录等本地配置
├── sessions/            # 会话元数据、JSONL 消息与运行检查点
├── agent-runs/          # 服务端多轮 AgentRun 状态、事件与工具检查点
├── attachments/         # 会话附件
├── file-backups/        # 文件修改备份
├── memory/              # 项目记忆
├── skills/              # 用户与内置技能
├── update.log           # 自动更新日志（如有）
└── crash.log            # 启动异常记录（如有）
```

- Web 服务只监听 `127.0.0.1`，默认不向局域网暴露。
- 项目文件和会话保存在本机；发送给模型的上下文仍会经过你配置的 API 网关及其上游模型服务。
- Code 拥有真实文件和命令执行能力，请只选择可信项目并检查重要改动；关键项目建议同时使用 Git。

## 会话与后台任务

每个模型任务都拥有独立的运行 ID、运行状态、停止信号和恢复检查点。主任务输出期间再次发送的消息会作为同会话后台 AgentRun 独立运行，结果与用量只合并一次。主任务和后台消息分别从发送时刻记录端到端耗时，刷新后沿用原起点；结果按完成顺序显示，后台回答通过可点击的单行回复引用关联原用户消息，不在正文重复完整提示词。页面刷新后会重新连接各自的 SSE 事件流；切换或新建会话只改变前台视图，不会取消后台任务。

会话正文采用 JSONL 持久化，元数据与消息分开保存。历史 JSON 会话可以迁移，长会话则通过上下文压缩减少重复 Token，同时保留必要任务背景与近期交互。

## 项目结构

```text
Code/
├── server.py                # HTTP 服务、模型代理、任务运行时和本地工具
├── dev_server.py            # 隔离的 3011 源码开发实例入口
├── launcher.py              # EXE 启动、托盘、数据目录与浏览器接管
├── 启动Code开发版.bat       # Windows 开发实例启动与页面复用
├── index.html               # 应用结构
├── app.js                   # 前端主流程与状态投影
├── agent-runtime.js         # 浏览器侧任务运行时桥接
├── styles.css               # 主题与响应式样式
├── src/                     # 已拆分的前端核心与服务模块
├── data/skills/             # 随程序分发的 Skills
├── assets/                  # Code 品牌与界面资产
├── tests/                   # 自动化测试与测试夹具
├── docs/                    # 使用、迁移、架构计划、开发日志与版本说明
│   └── development-log/     # 开发日志索引、按日期记录与冻结历史归档
├── build_exe.py             # PyInstaller 单文件构建入口
├── VERSION                  # 当前版本号
└── TODO.md                  # 尚未完成的路线清单
```

## 开发与验证

```powershell
# 全量测试
python -m pytest tests -q

# JavaScript 语法检查
node --check app.js
node --check agent-runtime.js

# Python 编译检查
python -m py_compile server.py launcher.py build_exe.py

# 构建 Windows 单文件程序
python build_exe.py
```

### 界面文案与 i18n

- 只有按钮、标题、说明、占位符、状态提示和错误提示等产品固定文案需要翻译；用户消息、模型回答、代码、文件名、路径和命令输出保持原文。
- 所有浏览器端翻译统一维护在 `src/core/i18n.js`。新增文案必须在对应 `LANG` 或 `I18N` 的 `zh`、`en` 区域使用同一个 key 成对添加，即使两种语言暂时使用相同文本也不能省略一侧；不要在业务文件中新建语言字典。
- HTML 静态文案使用 `data-i18n`，悬浮标题使用 `data-i18n-title`；JavaScript 动态文案使用 `t("key")`，带变量时使用 `t("key", { name })`。
- 修改界面文案后运行 `node --check src/core/i18n.js` 和 `python -m pytest tests/test_frontend_modules.py tests/test_p2_coverage.py -q`。词典任一语言缺少 key 时，回归测试必须失败。
- 前端人工检查至少覆盖：切换到英文后立即生效、刷新后仍保持英文、切回中文后立即生效，以及设置页、动态面板或弹窗没有残留错误语言。

构建产物位于 `dist/Code-v<version>.exe`。发布前应同时核对：

- `VERSION`、`file_version_info.txt` 和 README 版本号一致；
- 全量测试与语法检查通过；
- EXE 的 Windows 版本元数据、文件名和内置版本一致；
- SHA-256 已写入对应的 `docs/releases/` 版本说明；
- Git 标签和 GitHub Release 使用同一版本号。

## 文档与路线

- [v0.5.7 发布说明](docs/releases/v0.5.7.md)
- [v0.5.6 发布说明](docs/releases/v0.5.6.md)
- [v0.5.4 发布说明](docs/releases/v0.5.4.md)
- [会话 JSONL 迁移说明](docs/session-jsonl-migration.md)
- [服务端 Agent 循环迁移计划](docs/SERVER_AGENT_LOOP_PLAN.md)
- [前端模块拆分计划](docs/APP_JS_SPLIT_PLAN.md)
- [开发日志索引](docs/development-log/README.md)
- [待办与路线](TODO.md)

## 当前边界

- 正式打包和托盘流程目前仅支持 Windows。
- Code 依赖外部 OpenAI 兼容模型网关，本仓库不提供模型服务或 API 额度。
- 四种权限的新 Agent 主任务与同会话后台消息均由本地服务持有，浏览器关闭后无需人工决定的步骤仍可继续；迁移前的浏览器检查点会保留现有消息并明确失败，不会重放可能已发生的副作用。
- 当前前端仍以原生 JavaScript 为主，`app.js` 的进一步模块化正在进行。

## 许可证

本项目采用 [MIT License](docs/LICENSE)。
