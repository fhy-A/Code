# pi / Code / DSH 三方 Agent 架构对照

> 版本：v1.0 · 2026-08-14
>
> 历史快照声明：本文的仓库规模、stars、能力判断和建议均固定在 2026-08-14 的资料截面，不代表 pi、Code 或 DSH 当前状态；继续使用前应按目标版本重新核对。正文与结论保留当时原貌，未核验边界仍以第五节为准。
>
> 基线：
> - **pi**：GitHub 公开信息（2026-08-14 拉取），`earendil-works/pi`（89,746 stars，MIT，TypeScript monorepo）+ `agegr/pi-web`（4,181 stars，Next.js）
> - **Code**：本仓库代码与文档（2026-08-14 会话深度阅读，已核验）
> - **DSH**：本机部署随附包 `0.1.0-rc.6` 源码（已核验）
>
> 用途：回答"Code 的架构选择在同类实现中的位置"，为后续方向（TUI/桌面壳、权限、会话格式、评估资产）提供对照依据。pi 侧仅核验了 README、包结构与 pi-web 文档，**未读 pi 本体源码**，相关结论以公开信息为准（见第五节局限）。

---

## 一、三方概况

| | pi | Code | DSH |
|---|---|---|---|
| 主体 | `earendil-works/pi`（agent 本体）+ `agegr/pi-web`（Web UI） | `api中转站/code`（单仓库单产品） | `@deepseek-ai/dsh-*`（多包 monorepo） |
| 定位 | "AI agent toolkit：统一 LLM API、agent loop、TUI、coding agent CLI" | 本地 Windows Web 编程 Agent（对标 Claude Code） | 官方编码 Agent harness（Web GUI + headless + ACP） |
| 规模 | 89.7k stars；TS monorepo：agent-core / ai / coding-agent / tui / telemetry / server / protocol / evals | 13.4k 行单文件 server.py + 原生 JS 前端；~1146 测试 | 数十个 npm 包；每个子系统独立包 + README |
| UI | **TUI 为主** + pi-web（Next.js，四语） | Web（原生 JS，中英） | Web（主）+ headless/ACP |
| 许可证 | MIT | MIT | 随部署分发（包内 LICENSE） |

## 二、架构形状对照

| 维度 | pi | Code | DSH |
|---|---|---|---|
| 运行时归属 | **CLI 进程**（agent-core，transport 抽象）；`pi-server` 标记 experimental | **服务端持有** AgentRun 生命周期（浏览器是观察窗） | 服务端持有，transport-agnostic |
| 服务化协议 | `pi-protocol`：**CBOR、transport-neutral、remote sessions**（为远程会话设计） | HTTP/JSON + SSE，自定义 `/api/agent/runs/*` | Typert/Remote 注册表 + fetch/SSE |
| 会话存储 | `~/.pi/agent/sessions/<encoded-cwd>/<timestamp>_<uuid>.jsonl`，**CLI 与 Web 共享同一份数据** | 自有 Session JSONL + AgentRun 事件/检查点 + 索引 | 会话日志 JSONL（append-only 真源）+ 投影 |
| 会话组织 | 按 **encoded-cwd 目录**分组 | 按 项目（多根）+ source 分组 | 按 Workspace 注册表（realpath 规范化）记账 |
| 权限模型 | **无内置权限系统**（README 明说：默认以启动用户权限运行，建议容器化/沙箱化） | 四档权限（read/plan/accept/bypass）+ 授权流 + 项目根路径沙箱 + 服务端硬门禁 | 三档沙箱（read-only/workspace-write/full）+ 审批（ask/never）+ 升级授权 |
| 扩展机制 | 扩展体系 + Gondolin（host 外微 VM 路由工具） | Skills（SKILL.md + 依赖操作引擎） | Cordis 插件（静态组合 + 动态双半插件）+ Skills + Agent 预设 |
| 工具模型 | agent-core：tool calling + state management（transport 抽象） | `SERVER_TOOL_REGISTRY`（effect/idempotent/background 分类）+ 注册表执行 | tools 注册表 + 完整流水线（pre-execute/guard/execute/post-execute/finalize） |
| 质量验证 | `pi-evals` 包；供应链硬化（精确版本、shrinkwrap、audit、--ignore-scripts）；**公开真实会话数据集**（badlogic/pi-mono on HF） | H0-H4 确定性回放 + 语义哈希 + 影子投影 + Playwright E2E；双入口一致性 | 生成目录门禁（API/工具/槽位）+ invariant + 每子系统 README 的 KV Cache 影响声明 |
| 语言/时区 | TS/Node；四语文档（中/日/俄/英） | Python/原生 JS；中英 | TS/Node；英文生态 |
| 渠道/计费 | 无（内置 provider 登录管理，模型面板） | **workbar 中转闭环**（自动 Key 同步 + 计费） | 网关无关（settings 驱动），默认官方路由 |
| 安全姿态 | 信任执行 + 网络边界（pi-web 警告"绑定非回环=暴露高权限 agent"，提供 Basic Auth） | 127.0.0.1 默认 + 授权流 + 项目范围 | 127.0.0.1 默认 + 沙箱围栏 + 审批 |

## 三、关键差异分析

### 3.1 权限模型：三方站在信任光谱的三个位置

```
pi ─────────────── Code ───────────────── DSH
无内置权限          四档 + 服务端硬门禁        三档沙箱 + 审批
（信任+容器化）      （权限最细、最强制）        （策略围栏+升级）
```

- pi 的 README 明说没有内置权限系统，安全靠"以用户权限运行 + 容器化三模式（Gondolin/Plain Docker/OpenShell）"——对 CLI 工具是合理取舍，但 pi-web 的远程访问警告暴露了代价：没有授权层，只能靠网络边界兜底。
- Code 是三者中权限最强制化的：工具目录按档过滤 + 运行时按 effect 硬门禁 + 编辑/命令/文件授权流 + 重复命令拦截（之前分析过）。对"面向非技术用户的本地产品"，这是正确的差异化。
- DSH 居中：fs 沙箱按模式围栏写操作、读全开，审批策略可配置；动态插件明确"像对待 bash 一样信任"。

### 3.2 运行时归属：三方在收敛到同一形状

- Code 和 DSH 都是"服务端运行时 + 浏览器投影"（刷新零重放、断连恢复）。
- pi 起点是 CLI 进程 + TUI，pi-web 是"独立 Web 观察窗 + 共享会话文件"；但 `pi-server`（experimental）+ `pi-protocol`（CBOR remote sessions）的出现说明 **pi 也在走向 agent 服务化**——三方正在收敛到"agent 是服务、UI 是 surface"这个形状。
- 差异在成熟度：Code/DSH 的服务端是唯一真源；pi 是"同一份会话文件两个进程共享"，一致性依赖文件锁与刷新。

### 3.3 会话格式与组织：同源异流

- 三方都是 JSONL 消息/事件；pi 用 `<encoded-cwd>/<timestamp>_<uuid>.jsonl` 天然按工作目录分组，Code 用项目+source+AgentRun 双层，DSH 用 workspace 注册表 + session header cwd 记账。
- pi 的"按 cwd 编码目录"最朴素（无注册表、无迁移），Code/DSH 都建立了索引/归属层——对多项目多会话的可管理性是增量，但也各自承担了索引一致性的工程税（Code 的 `_rebuild_index_if_needed`、DSH 的 workspace 启动拒绝不一致）。

### 3.4 pi 独有的两个实践（Code 可参考）

1. **公开真实 OSS 会话数据集**：badlogic 把真实工作会话发布到 HuggingFace（pi-mono），用于改进 agent 而不是玩具 benchmark。Code 的 H 系列 fixture 是测试资产，pi 的做法是"训练/评估资产"——两者可结合：脱敏真实轨迹 → 长期评估集。
2. **供应链硬化**：精确版本、shrinkwrap 白名单、`--ignore-scripts`、定时 audit——如果 Code 将来发布 PyPI 包或引入更多第三方依赖，这套纪律值得复制（Python 侧对应 pip-tools + 锁文件 + 依赖审计）。

### 3.5 pi-web 的可借鉴点

- **Git worktree 切换 + 会话按仓库分组**（`docs/worktrees.md` 有完整设计）——Code 的 CODE-021（worktree 隔离）可参考其可见性/创建/移除语义。
- **下游集成钩子**（`pi-web:session-row-contextmenu` 可取消浏览器事件，允许 Electron 壳扩展而不改源码）——与 Code"surface 可替换"哲学一致。
- **语言切换器**（中/日/俄/英）——Code 目前只中英，pi-web 的多语言成本模式可参考。

## 四、对 Code 的结论与建议

1. **权限模型是 Code 相对 pi 的核心差异化**——pi 无内置权限、DSH 是策略围栏，Code 的四档 + 服务端硬门禁是三者中最适合"非技术用户本地产品"的；不要因为对标 Claude Code 而弱化它（CODE-029 的方向是对的：把"自动"档的边界讲清楚）。
2. **运行时归属上 Code 已经站在正确的一侧**（与 DSH 同侧、领先 pi 的实验性 server）——将来做 TUI/桌面壳（CODE-022）时，参考 DSH 的 surface 模式而非 pi 的共享文件模式：服务端唯一真源，新增 surface 只加投影层。
3. **评估资产是三方差距最小的洼地**：pi 有公开会话数据集 + evals，DSH 有生成目录门禁 + invariant，Code 有 H 系列。建议把"脱敏真实轨迹 → 长期评估集"作为 H 系列的自然延伸（已有 fixture 基础，成本低）。
4. **供应链硬化值得在依赖引入时执行**：Code 目前依赖极少（Python 标准库 + pystray/Pillow/docx），这是优势；将来加依赖时按 pi 的纪律（锁文件、审计、最小生命周期脚本）执行。

## 五、局限与未核验项

1. **pi 侧未读本体源码**：agent-core 的循环实现、权限相关代码、pi-server/protocol 的实际能力均未核验；`pi-server` 官方标记 experimental，能力可能随时变化。以上对照中 pi 相关结论均基于公开 README/包结构/pi-web 文档（2026-08-14 拉取）。
2. **pi 的会话格式**仅凭 pi-web README 描述（`~/.pi/agent/sessions/<encoded-cwd>/<ts>_<uuid>.jsonl`），未核验 JSONL 内部结构。
3. **Code/DSH 侧**基于本会话已核验的源码与文档（见前序调研），无新增未核验项。
4. stars 数、更新时间均为拉取时点数据，可能变动。

## 附录：对照数据来源

- `earendil-works/pi`：GitHub API + README.md + packages/ 目录 + 各包 package.json（2026-08-14）
- `agegr/pi-web`：GitHub API + README.md + 根目录结构（2026-08-14）
- Code：本仓库 `server.py`/`app.js`/`src/`/`docs/`/`TODO.md`（2026-08-14 会话）
- DSH：`%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\` 下已读包（0.1.0-rc.6）
