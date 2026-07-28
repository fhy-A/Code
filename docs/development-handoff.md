# 开发交接快照

> **上次更新**：<!-- FILL: YYYY-MM-DD -->
>
> **事实源**：`CHANGELOG.md`（已完成）和 `TODO.md`（未完成）是唯一事实源。本文件只做导航和模板——开始任何工作前必须先核对 Git 现场状态，与本文件冲突时以现场为准。
>
> **使用方式**：每次任务交接时，填写下方的 `<!-- FILL: ... -->` 占位字段，其他内容保持不动。稳定章节只有在架构或规则真正变化时才修改。

---

## 一、当前仓库状态

> 每次交接必填。运行以下命令获取最新值后填入：
> ```powershell
> git log -1 --oneline
> git branch --show-current
> git status --short
> ```

| 项目 | 值 |
|------|-----|
| 项目目录 | `C:\Users\Admin\Desktop\api中转站\code` |
| 当前分支 | `<!-- FILL: master / main / feature-branch -->` |
| HEAD 提交 | `<!-- FILL: git log -1 --oneline -->` |
| 发布基线 | `<!-- FILL: vX.Y.Z -->` |
| 未跟踪/未提交文件 | `<!-- FILL: 列出需要注意的未跟踪文件，无则写"无" -->` |

### 快速校验命令

任何 Agent 接手后先执行：

```powershell
Set-Location "C:\Users\Admin\Desktop\api中转站\code"
Get-Content CHANGELOG.md -Encoding utf8 -TotalCount 120
Get-Content TODO.md -Encoding utf8
git status --short
git log -8 --oneline
```

---

## 二、项目不变量

> 以下描述项目的稳定架构、技术栈和核心约定。这些内容不常变化——只有在新功能改变了系统设计时才更新对应条目。

### 技术栈与入口

| 项 | 说明 |
|----|------|
| 服务入口 | `server.py`，监听 `127.0.0.1:3010`（可通过 `CODE_PORT` 环境变量覆盖） |
| 前端 | 原生 JavaScript / HTML / CSS，主状态在 `app.js`，部分功能已迁入 `src/` |
| 打包 | PyInstaller 单文件 EXE（`build_exe.py`），入口 `launcher.py` |
| 数据目录 | 正式 EXE 用 `%USERPROFILE%\.code\`，源码模式用 `data/` |
| 模型网关 | 固定为 `https://workbar.ai`，前端不展示或编辑 Base URL |

### 发版

- **必须使用 `release.py`**，不得手动改版本号。用法详见 `docs/release-guide.md`。
- Agent 发版加 `--yes`；推送或 Release 失败时立刻报告用户。
- 发布说明、更新摘要和开发日志默认使用中文；发布前检查无占位文案，并确认内容只覆盖上一标签至当前标签之间的实际改动。

### 协作规则（详见 `AGENTS.md` 和 `CLAUDE.md`）

1. 新需求、优化建议或 Bug 先进行只读调查并给出初步方案；用户明确同意前不得修改业务代码，实施范围发生明显变化时必须重新确认。
2. 诊断请求默认只读；本地提交可按阶段规则自动完成，推送、标签、发布、删除数据和线上配置修改必须获得明确授权。
3. 临时测试参数必须在结束前恢复、核对并报告，不得进入提交或发布。
4. 同一级 `AGENTS.md` 与 `CLAUDE.md` 的共同规则保持同步；根目录与子项目的相同全局规则也要检查同步。
5. 会话格式、持久化数据、工具协议或配置结构变更，方案必须包含兼容、迁移和回退方式。
6. 一次只做一个阶段，不混入下一阶段功能。
7. 先验证后提交：测试、语法检查、`git diff --check` 全过才提交。
8. 视觉、时序、交互改动必须人工验收后才提交。
9. 每阶段结束更新 `CHANGELOG.md` 和 `TODO.md`，独立 `git commit`。

### i18n 约定

- 所有浏览器端翻译统一在 `src/core/i18n.js`，不得在业务文件中新建局部语言字典。
- 新增文案必须在 `zh` 和 `en` 区域用同一 key 成对添加。
- 修改后运行 `node --check src/core/i18n.js` 和 `pytest tests/test_frontend_modules.py tests/test_p2_coverage.py -q`。

### AgentRun 与会话

- 四种权限模式的任务均由服务端持久 AgentRun 执行；浏览器负责 SSE 观察、问卷和授权交互。
- 主任务运行时的新消息 FIFO 排队，不自动转为后台任务；明确并行操作（`/parallel`）才创建后台 AgentRun。
- 模型 `task` 工具创建子 AgentRun，同一轮次最多并发 3 个，不可递归委托。
- 会话使用 JSONL 持久化；分支会话复制父会话消息后独立保存。
- 刷新/切换/新建会话不取消其他正在运行的 AgentRun。

### Skills 依赖管理

- `dependencies.json` 以能力为单位声明 Python/Node/系统依赖。
- Python 与 Node 依赖只能在 Code 管理的隔离运行时（`data/runtime`）中、经用户授权后安装。
- 系统级依赖只提供 `installHint`，不由模型直接执行系统包管理器。
- 已阻止：`winget`/`choco`/`apt`、PATH 修改、全局包装器、相同命令重复执行超过两次。

### 安全边界

- workbar Access Token、API Key、Authorization 头不得写入 AgentRun 状态、交接文档、测试输出或 Git。
- 不得使用 `git reset --hard`、`git checkout --` 或其他破坏性命令处理共享工作区。
- `data/` 包含本地会话、授权状态和备份；除非任务明确要求，不要批量清理。
- Docker 构建优先使用 `--pull=false`。

---

## 三、本次交接备注

> 每次交接填写。描述当前阶段目标、特殊注意事项、已知问题或临时约束。

### 当前建议推进

<!-- FILL: 从 TODO.md 中摘取本次最优先的 1-3 项任务，简要说明目标和边界 -->

1. **<!-- FILL: 任务名 -->**：<!-- FILL: 目标和范围 -->
2. **<!-- FILL: 任务名 -->**：<!-- FILL: 目标和范围 -->

### 特殊注意事项

<!-- FILL: 本次交接特有的警告、约束或背景信息。没有则写"无"。 -->

### 已知阻塞

<!-- FILL: 当前有哪些阻塞项？依赖什么条件？没有则写"无"。 -->

---

## 四、验证流程

每个阶段结束前必须完成以下验证，再提交。

### 自动检查清单

```powershell
# Python 编译检查（按实际改动选取文件）
python -m py_compile server.py launcher.py build_exe.py

# JavaScript 语法检查
node --check app.js
node --check agent-runtime.js
node --check src/core/i18n.js

# 定向测试（按改动范围选取，以下为常用组合）
python -m pytest tests/test_server.py tests/test_routes.py -q
python -m pytest tests/test_frontend_modules.py tests/test_p2_coverage.py -q

# 提交前最后一道检查
git diff --check
```

### 人工验收条件

以下情况必须交给用户人工确认，不能自行判定通过：

- 视觉变更：布局、颜色、间距、动画
- 交互变更：焦点行为、键盘导航、拖拽
- 时序变更：流式显示、加载状态、通知时机
- 浏览器差异：不同浏览器或窗口尺寸下的表现

### 全量回归

重大变更或发版前运行：

```powershell
python -m pytest tests -q
```

---

## 五、新任务启动消息模板

> 以下模板可直接粘贴给新 Agent。将 `{...}` 占位符替换为当前值后使用。

```text
请接手 {项目目录} 的后续开发。

开始前完整阅读 AGENTS.md、CHANGELOG.md、TODO.md 和 docs/development-handoff.md，
并用 git status --short、git log -8 --oneline 核对现场状态。
CHANGELOG.md 是已完成改动的事实源，TODO.md 是未完成事项的事实源；
交接快照与现场冲突时以现场为准。

当前建议推进：{简要描述本次最优先任务}。

一次只推进一个阶段；自动测试充分时自行验证、更新 CHANGELOG/TODO 并提交；
涉及界面和时序时先给出人工测试步骤，等确认后再提交。
```
