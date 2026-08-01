# app.js 后续拆分计划

> 状态：阶段 1 至 6 已完成；6D 已收口真正的临时全局，并在正式版恢复能力审计后有意保留经典回退与 `window.Code` 模块命名空间
> 适用范围：Code 前端  
> 核心原则：先拆职责、保持行为，再引入构建工具；每一批都可验证、可回滚。

## 1. 当前基线

截至本计划编写时：

- `app.js`：14,393 行、462,213 bytes、296 个顶层函数（2026-07-16 第一批拆分后）。
- `agent-runtime.js`：已独立承接模型运行时的创建、续接和取消。
- `index.html`：按依赖顺序加载普通脚本，尚未使用 ES Module 或前端打包器。
- `src/core/namespace.js`、`icons.js`、`utils.js` 已完成抽离，统一通过 `window.Code.core` 暴露接口。
- `build_exe.py` 已显式打包 `agent-runtime.js` 与 `src/`，避免正式 EXE 缺少拆分后的前端资源。
- 前端状态主要集中在一个全局 `state` 对象中，会话、流式运行、文件预览、权限、问卷、Skill、设置等功能仍直接共享和修改该对象。
- `app.js` 同时承担状态管理、接口调用、业务逻辑、DOM 渲染、事件绑定和应用初始化，修改局部功能时容易影响其他区域。
- 自动化测试已经覆盖会话恢复、网络重连、并发会话、权限、问卷、子 Agent、编辑流水线、文件预览等关键路径，应作为拆分期间的行为护栏。

## 2. 拆分目标

### 2.1 目标

1. 将 `app.js` 缩减为只负责应用装配、初始化和少量顶层事件协调的入口文件。
2. 将状态、会话、渲染、文件、Agent 执行、工具、权限、设置等职责形成清晰边界。
3. 保持当前 UI、数据格式、API 请求和用户操作行为不变。
4. 降低修改单一功能时的影响范围，方便 Claude Code、Codex 和人工开发者并行维护。
5. 为后续引入 esbuild、TypeScript 或更完整的前端测试打好边界基础。
6. 保持开发版和正式 EXE 的资源加载、更新和兼容性一致。

### 2.2 非目标

本轮拆分阶段不同时进行以下工作：

- 不更换前端框架。
- 不重做 UI 或交互。
- 不修改会话 JSON、配置文件和运行时检查点的数据结构。
- 不改 New API 请求协议、工具协议和权限规则。
- 不在同一提交中混入功能增强或视觉改版。
- 不立即把所有代码改成 ES Module；构建体系放到模块边界稳定之后。

## 3. 总体架构

### 3.1 过渡期加载方式

第一阶段延续 `agent-runtime.js` 的做法：

- 每个模块使用 IIFE 封装内部实现。
- 只通过 `window.Code` 暴露必要的公共接口。
- `index.html` 按依赖顺序加载脚本。
- `app.js` 暂时保留兼容代理函数，调用新模块实现。
- 每完成一个模块，就从 `app.js` 删除对应旧实现，避免长期保留两套逻辑。

建议统一命名空间：

```text
window.Code.core
window.Code.services
window.Code.features
window.Code.agent
window.Code.ui
```

### 3.2 依赖方向

依赖只允许从上层流向下层：

```text
app.js / bootstrap
        ↓
ui + features
        ↓
agent + services
        ↓
core
```

约束：

- `core` 不依赖 DOM，不依赖具体业务模块。
- `services` 负责 API、持久化和浏览器能力，不直接渲染页面。
- `agent` 负责模型、工具、权限和任务循环，不直接管理侧栏与设置页面。
- `features` 负责会话、文件、Skill、设置等产品功能。
- `ui` 只负责展示、事件转发和视图状态，不直接拼接后端协议。
- 模块不得直接创建新的全局变量；统一挂载到 `window.Code`。

### 3.3 状态访问规则

拆分初期保留一个共享状态源，但逐步禁止任意模块直接修改：

1. `state` 由状态模块创建和持有。
2. 模块通过 `getState()`、领域选择器和明确的更新函数访问。
3. 会话级运行状态继续以 `sessionId` 隔离，防止切换会话影响后台任务。
4. 任何持久化字段变更都必须先保证旧会话可读取。
5. 不在纯渲染函数中写状态，不在状态更新函数中操作 DOM。

## 4. 目标目录结构

第一轮建议采用以下结构，不追求过度细分：

```text
code/
├─ app.js                         # 最终只保留装配、初始化和顶层协调
├─ agent-runtime.js               # 现有服务端模型流传输层
├─ src/
│  ├─ core/
│  │  ├─ namespace.js             # window.Code 初始化和模块注册
│  │  ├─ state.js                 # 全局状态、选择器、领域更新入口
│  │  ├─ utils.js                 # 纯工具函数
│  │  ├─ i18n.js                  # 语言字典、t()、动态文本刷新
│  │  └─ icons.js                 # 图标定义和静态图标升级
│  ├─ services/
│  │  ├─ api-client.js            # JSON/SSE 请求、错误标准化
│  │  ├─ persistence.js           # 配置、会话和本地状态保存
│  │  └─ notifications.js         # 浏览器通知、提示和声音
│  ├─ agent/
│  │  ├─ model-stream.js          # 模型请求、SSE 解析、usage 累计
│  │  ├─ tools.js                 # 工具 schema、调用和结果标准化
│  │  ├─ permissions.js           # 权限模式、授权队列和确认面板数据
│  │  ├─ questionnaire.js         # request_user_input 生命周期
│  │  ├─ subagents.js             # 子 Agent 和后台任务调度
│  │  ├─ compaction.js            # 上下文压缩和压缩标记
│  │  └─ agent-loop.js            # 原计划候选；5G 审计后不创建，入口编排保留在 app.js
│  ├─ features/
│  │  ├─ sessions.js              # 会话 CRUD、切换、恢复和分支
│  │  ├─ files.js                 # 文件树、上传、附件和路径处理
│  │  ├─ preview.js               # 文本/代码/图片/MD/PDF/CSV 预览
│  │  ├─ skills-memory.js          # Skill 与 Memory 检索、管理和上下文
│  │  ├─ settings.js               # 设置、更新、认证和引导
│  │  └─ branches.js               # 分支创建、标记和分支面板
│  └─ ui/
│     ├─ markdown.js               # Markdown、代码块和 ANSI 渲染
│     ├─ diff.js                   # Diff 解析和编辑建议卡片
│     ├─ messages.js               # 消息投影、流式内容和 usage 行
│     ├─ timeline.js               # 时间线、压缩/分支标记
│     ├─ panels.js                 # 顶部面板、预览栏、设置面板
│     └─ events.js                 # DOM 事件绑定和快捷键
└─ tests/
   └─ ...                          # 按领域补充结构与行为测试
```

如果某个文件超过约 1,200 行或内部出现两个独立职责，再做第二次细分；不要一开始制造大量只有几十行的小模块。

## 5. 实施阶段

### 阶段 0：冻结基线与建立护栏

#### 工作内容

- 记录当前 `app.js` 行数、函数数和关键功能清单。
- 确认全量测试基线通过。
- 为 `index.html` 脚本加载顺序、EXE 资源打包、已有会话兼容增加检查。
- 建立最小浏览器冒烟清单。
- 绘制全局 `state` 各字段的读写归属表。

#### 验收

- 没有功能代码变化。
- 全量测试通过。
- 能明确回答每个待拆模块依赖哪些状态、接口和 DOM 节点。

### 阶段 1：抽离低风险基础模块

#### 当前进度

- [x] 建立 `window.Code` 五层命名空间。
- [x] 抽离图标表与 `uiIcon()` 到 `src/core/icons.js`。
- [x] 抽离 HTML 转义、数字/时间格式化与 token 估算到 `src/core/utils.js`。
- [x] 固化脚本加载顺序与正式 EXE 资源清单。
- [x] 增加模块存在、依赖顺序、重复定义和打包资源回归测试。
- [x] 抽离语言字典、参数插值、DOM 翻译和语言切换运行时到 `src/core/i18n.js`；`app.js` 仅注入业务重绘回调。
- [x] 抽离 Toast 与系统通知到 `src/services/notifications.js`，业务触发条件仍保留在 `app.js`。
- [x] 抽离 `apiJson()` 到 `src/services/api-client.js`，保留模型流、AgentRun 和专用请求的原有所有权。

#### 拆分内容

- `icons.js`
- `i18n.js`
- `utils.js`
- `notifications.js`
- `api-client.js` 中不涉及 Agent 循环的通用请求函数

#### 原则

- 优先移动纯函数和无状态逻辑。
- 保持原函数名的兼容代理，逐步替换调用点。
- 不调整 UI 样式与文案。

#### 验收

- 中英界面切换正常。
- 图标、复制、通知和通用错误提示正常。
- `app.js` 预计减少 800 至 1,500 行。

### 阶段 2：抽离独立产品功能

#### 当前进度

- [x] 抽离文件列表加载、搜索、排序、目录导航、右键菜单、项目目录管理、新建文件夹和普通文件附件到 `src/features/files.js`；预览继续由原所有者实现，文件模块只通过公开回调请求打开文件。
- [x] 抽离图片、Markdown、PDF、CSV/TSV、代码和大文件预览到 `src/features/preview.js`；文件树只通过 `openFile` 回调进入预览，渲染与交互依赖由应用装配层显式注入。
- [x] 抽离 Skill 与 Memory 管理到 `src/features/skills-memory.js`；自动匹配、正文懒加载、斜杠建议、启停、CRUD 与 Memory 上下文由模块统一承接。
- [x] 抽离设置、更新、平台认证与首次使用引导到 `src/features/settings.js`；模型请求、权限和 AgentRun 执行状态继续留在原所有者中。

#### 拆分内容

- 文件树与附件：`files.js`
- 多格式预览：`preview.js`
- Skill 与 Memory：`skills-memory.js`
- 设置、更新和认证：`settings.js`

#### 原则

- 每次只拆一个产品功能。
- 模块通过公开接口更新页面，不跨模块查找内部变量。
- 同步更新 `build_exe.py` 和 PyInstaller 资源清单，确保 `src/` 脚本进入正式 EXE。

#### 验收

- 文件树、添加文件、附件路径、预览栏拖拽均正常。
- 图片、MD、PDF、CSV/TSV、代码和大文件预览正常。
- 设置页、版本检测、更新红点、登录认证正常。
- Skill 搜索、`/` 命令和 Memory 注入正常。
- `app.js` 预计再减少 2,000 至 3,000 行。

### 阶段 3：拆分渲染与消息投影

#### 当前进度

- [x] 抽离 Markdown、代码块、语法高亮与 ANSI 渲染到 `src/ui/markdown.js`；本地路径、外部链接和本地图片后处理统一由模块生成，消息与流式 DOM 生命周期保持不变。
- [x] 抽离 Diff 解析和编辑建议卡片到 `src/ui/diff.js`；应用/拒绝、折叠、复制、路径打开和文件授权状态继续由应用装配层管理。
- [x] 修复最终回复耗时晚于消息持久化的问题；刷新恢复后保留真实耗时，历史缺失耗时不再显示为 `0s`。
- [x] 抽离消息投影和渲染到 `src/ui/messages.js`；消息分组、思考与最终回答、后台引用、用量/耗时和稳定顺序由模块承接，增量流式补丁、事件与滚动仍由应用装配层管理。
- [x] 抽离时间线、分支和压缩标记到 `src/ui/timeline.js`；用户节点投影、点击定位、分支来源和压缩标记由模块承接，完整分支元数据在会话加载后回填到摘要。
- [x] 抽离顶部面板和 Session Info 到 `src/ui/panels.js`；Session Info 统计、会话字段、路径复制和三个顶部面板的互斥/关闭交互由模块承接，分支树与工具日志内容仍由原业务所有者投影。

#### 拆分内容

- Markdown、代码块、ANSI：`markdown.js`
- Diff 与编辑建议：`diff.js`
- 消息投影和渲染：`messages.js`
- 时间线、分支和压缩标记：`timeline.js`
- 顶部面板和 Session Info：`panels.js`

#### 关键风险

- 流式内容更新时重复重建 DOM，导致闪烁或滚动跳动。
- 完成后刷新页面时滚动位置不一致。
- 思考过程、最终回答、编辑卡片和 usage 投影重复或丢失。

#### 验收

- 思考过程与最终回答保持完整流式输出。
- 会话切换、刷新恢复和后台输出不互相干扰。
- 用户消息、思考、编辑建议和最终回答仍是对话区仅展示的四类内容。
- 分支和压缩标记按真实消息顺序留在消息流中。
- `app.js` 预计再减少 2,000 至 3,000 行。

### 阶段 4：拆分会话状态与持久化

#### 当前进度

- [x] 4A-1：新增 `src/core/state.js`，抽离应用状态源以及会话消息、stats、usage、运行状态、后台任务和排队消息检查点的纯状态访问器；`app.js` 删除重复定义并保持兼容装配。
- [x] 4A-2：新增 `src/services/persistence.js`，抽离可配置字段组合的消息序列化、保存负载构建和按会话串行保存队列；保持同会话串行、跨会话并行和失败后续跑语义。
- [x] 4B：迁移会话 CRUD、切换和刷新恢复。
  - [x] 4B-1：新增 `src/features/sessions.js`，抽离会话 CRUD 数据访问、历史消息规范化和待处理编辑卡片重建；保留切换与恢复副作用编排。
  - [x] 4B-2：扩展 `src/features/sessions.js`，迁移前台新建、切换、导航竞态保护和当前会话状态装配；保持后台运行隔离与首次发送延后刷新语义。
  - [x] 4B-3：迁移刷新后的前台会话恢复与 Agent 恢复启动协调；保持前台运行、排队消息和后台任务的原有启动顺序与隔离语义。
- [x] 4C：新增 `src/features/branches.js`，迁移分支创建、stats/usage 继承、父子切换、分支树构建与渲染，并兼容只含 `_parentId` 的列表摘要。

#### 拆分内容

- `state.js`
- `persistence.js`
- `sessions.js`
- `branches.js`

#### 关键设计

- 明确“当前查看会话”和“后台运行会话”的区别。
- 每个会话独立保存消息、usage、运行状态、问卷、权限请求和检查点。
- 会话保存继续串行化，避免并发写入覆盖。
- 旧版 JSON 会话不迁移也能读取；新增字段提供默认值。

#### 验收

- 任意会话运行时可新建、切换、重命名、删除其他会话。
- 多会话同时执行仍保持独立流式输出。
- 刷新后恢复正确任务，不重复调用上游，不重复执行副作用工具。
- 创建普通会话不出现空分支标记；真实分支在父会话删除后仍保留来源快照。
- `app.js` 预计再减少 1,500 至 2,500 行。

### 阶段 5：拆分 Agent 核心执行链

#### 拆分顺序

1. `model-stream.js` / `model-request.js`
2. `tools.js`
3. `permissions.js`
4. `questionnaire.js`
5. `subagents.js`
6. `compaction.js`
7. `agent-loop.js`（原计划审计候选；5G-2 决定不创建）

#### 原则

- 这是风险最高的一阶段，必须最后进行。
- 先抽离协议解析和纯计算，再迁移有副作用的执行逻辑。
- 主 Agent、子 Agent、后台任务共享工具定义，但保留各自 usage 和消息账本。
- 计划模式、接受编辑模式和完全访问模式的行为不能因模块化改变。
- 问卷与权限继续是两个独立的等待通道。

#### 当前进度

- [x] 5A-1：新增 `src/agent/model-stream.js`，抽离 SSE 行解析、OpenAI / Anthropic / Responses 文本与思考增量提取、工具调用分片合并、模型请求错误标准化、模型访问失败分类和原生工具兼容降级判断。
- [x] 5A-2a：抽离模型轮次纯累加器，统一思考、正文、工具分片、usage 引用和完成/错误事件，消息投影、账本、检查点与 Runtime ID 仍由 `app.js` 编排。
- [x] 5A-2b：抽离可测试的 SSE 数据读取器，覆盖任意 UTF-8 字节分块、同块多帧、CRLF/keepalive 和无末尾换行尾帧；`app.js` 删除重复尾缓冲并只保留一个 `[DONE]` 原子提交出口。
- [x] 5A-3：新增 `src/agent/model-request.js`，抽离请求消息映射、原生工具调用序列化、工具调用/结果配对、孤立结果降级、未完成调用清理和非原生工具回退格式；普通请求、服务端 Agent、后台子任务与会话压缩共享同一纯边界。
- [x] 5A-4：扩展 `src/agent/model-request.js`，抽离固定请求字段、系统消息插入、工具配置以及 Claude thinking、OpenAI reasoning effort、Gemini reasoning effort 的纯装配；`app.js` 仅传入已经解析的输入。
- [x] 5A 保持请求上下文选择、项目上下文与系统提示词异步加载、UI 配置读取、`_callModelOnceAttempt()`、请求发起、`AgentRuntime.openSseResponse()`、Abort/读取错误分类、usage 账本、消息/DOM 投影、运行检查点和网络恢复状态在原所有者中，没有改变 JSONL、API、SSE、工具协议或 AgentRun 事件。
- [x] 5A 收口审计确认剩余模型调用代码均为异步准备或副作用编排；删除无调用的 `isTransientModelError()` 和无效消息构造导入，补齐 Responses reasoning、完整工具调用和读取器冻结测试，不再为减少行数继续搬迁模型调用主体。
- [x] 5B-1：新增 `src/agent/tools.js`，抽离 `parseJsonLoose()`、`normalizeNativeToolCall()` 和 `normalizeToolCallList()`；复用 `model-request.js` 的 `buildNativeToolCallMessage()`，保持工具 ID、参数覆盖、索引顺序、空名称过滤和输入不可变语义。
- [x] 5B-1 保持静态 `nativeTools` schema、`toolPolicy` / `getNativeTools()`、`formatToolCall()` / `formatToolResult()`、权限、问卷、网络、持久化、UI 投影和真实工具执行在原所有者中；没有修改服务端、JSONL、API 或工具协议。
- [x] 5B-2：将前端 15 项静态 `nativeTools` schema 原样迁入 `src/agent/tools.js`，以序列化哈希固定完整内容，并覆盖名称顺序、过滤不修改源数组以及问卷、命令、Memory 三处关键兼容差异；`toolPolicy` 与 `getNativeTools()` 仍由 `app.js` 负责。
- [x] 5B-2 不统一前后端定义：服务端 Agent 只采用前端传入的工具名称并从 `SERVER_TOOL_REGISTRY` 重新取得执行 schema；直接代理兼容路径继续使用前端定义。没有修改 `server.py`、JSONL、API、工具协议、权限或工具执行。
- [x] 5B-3：只读收口确认剩余工具选择属于权限策略，结果摘要属于 UI/i18n，授权、持久化、服务端事件桥接与真实执行属于副作用编排；不再为减少行数迁入 `tools.js`。
- [x] 5B-3 删除 `app.js` 中已经由 `src/ui/messages.js` 承接且无引用的旧工具渲染表、状态/目标/结果摘要辅助函数和单条/分区渲染函数，共减少 159 行；保留仍由消息模块注入使用的 `_toolActionLabel()`，并增加源码所有权回归护栏。
- [x] 5B 正式结束：`tools.js` 保持纯 schema 与调用标准化边界，权限、问卷、网络、持久化、UI 投影和真实工具执行均未改变；下一阶段进入 `permissions.js` 只读盘点。
- [x] 5C-1：新增 `src/agent/permissions.js`，抽离四种权限模式的静态工具策略、`getAllowedToolNamesForProfile()` 与 `executionOwnerForPermissionProfile()`；模块不读取 DOM、state、网络或持久化状态，每次返回独立 `Set`。
- [x] 5C-1 保持 read/plan/accept/bypass 工具名称与顺序、未知模式回退到 accept 工具集合、未知执行所有者回退到 browser，以及服务端注册表二次筛选行为不变；授权队列、确认面板、权限提示文本、问卷、恢复和真实执行均未迁移。
- [x] 5C-2：Git 历史与全仓引用审计确认，`isToolAllowed()`、`shouldAskBeforeTool()` 和 `requestAuthorization()` 在 `b26a0fb` 删除旧浏览器 Agent 执行循环后已失去全部调用方；同步删除只由旧请求入口使用的 `finishLocalAuthorizationRequest()` 和 `resolveAuthorization()` 中不可达的非 serverAgent 分支。
- [x] 5C-2 保持 `requestServerAgentAuthorization()`、服务端授权提交、确认面板 DOM、后台任务、旧会话恢复、持久化和通知链不变；旧本地授权 Promise 从未形成可恢复数据，因此无需迁移，并增加旧代码不得回流的源码护栏。
- [x] 5C-3：扩展 `src/agent/permissions.js`，迁移四种权限提示、授权请求序列化、按会话筛选待授权项和稳定分组四项纯逻辑；`pendingAuthorizations()` 保留为 `state.authorizationRequests` 适配器，`restoreAuthorizationRequest()` 与所有授权副作用继续由 `app.js` 编排。
- [x] 5C-3 固定提示文本、未知模式无提示、瞬态字段剔除、JSON 深拷贝、会话隔离、输入顺序和引用保持语义；未修改 JSONL、API、AgentRun、问卷、授权面板 DOM 或真实工具执行。浏览器真实授权流程通过，测试中发现的模式预览即时同步问题记入 TODO，未扩大本批范围。
- [x] 5D-1：新增 `src/agent/questionnaire.js`，抽离 `normalizeUserInputQuestions()` 与 `serializeUserInputRequest()` 两项纯逻辑；`app.js` 继续生成请求 ID、会话 ID、默认标题和时间，并持有问卷状态、恢复、DOM、持久化、通知与服务端提交副作用。
- [x] 5D-1 固定最多 3 个问题、最多 8 个选项、类型与字段默认值、无效问题过滤、pending 初态、瞬态字段剔除、JSON 深拷贝和输入不可变语义；未修改前后端 schema 差异、JSONL、API、AgentRun、授权通道或旧会话兼容完成分支。
- [x] 5D-2：扩展 `src/agent/questionnaire.js`，迁移答案文本和提交结果构造；`app.js` 仅保留传入 `t("questionCanceled")` 的本地化适配器，四个结果调用点和完成时序不变。
- [x] 5D-2 固定文本 trim、选项标签映射、未知值回退、用户选择顺序、`、`/`：` 分隔符、取消与空答案回退、`values`/`text` 的 undefined 序列化、`other` trim 和选择数组隔离语义；未统一前后端取消文案，未修改 `/input`、旧会话兼容结果或问卷 UI。
- [x] 5D-3：收口审计确认剩余问卷代码均为运行时元数据、本地化适配、状态、DOM、持久化、通知、AgentRun 提交或旧会话兼容副作用，不再为减少行数继续迁移。
- [x] 5D-3 新增测试护栏，固定恢复去重、服务端提交、旧浏览器问卷 reload 后工具结果重建、`resumedFromUserInput` 恢复、DOM/持久化所有权和纯模块禁止读取全局副作用；5D 正式收口。
- [x] 5E-1：新增 `src/agent/subagents.js`，抽离子 Agent 私有 system prompt、上下文数据构造、显式 `/parallel` 命令解析和后台任务提示词构造；`app.js` 仅保留运行时授权 ID 生成及既有副作用接线，由 10,268 行降至 10,247 行。
- [x] 5E-1 固定父上下文配置继承、独立消息/usage 账本、授权标签空白折叠与 24 字符上限、禁用递归 `task`/`request_user_input`、主任务摘要最多 150 字符、输入工具数组不变及显式并行语义；未修改服务端 Child AgentRun、后台调度、AgentRuntime、授权、持久化、JSONL、API 或恢复协议。
- [x] 5E-2a：扩展 `src/agent/subagents.js`，抽离后台任务 timeout 常量、checkpoint 序列化、提交起点耗时和 usage 合并纯计算；`app.js` 继续提供当前时间、保留 stats 原对象并负责耗时格式化与状态写入，由 10,247 行降至 10,213 行。
- [x] 5E-2a 固定旧字段默认值、父上下文目录回退、`rootPaths` 数组隔离、瞬态字段剔除、`cacheWrite` 仅在子 usage 明确报告时累加、输入对象不变、排队时间优先和负耗时归零语义；未迁移 reload job 装配、Promise/resolver、调度、去重、AgentRuntime、授权或持久化。
- [x] 5E-2b：扩展 `src/agent/subagents.js`，抽离 reload checkpoint 到 runtime job 的纯字段规范化；复用 checkpoint 默认值边界并保留未知字段，`app.js` 仅提供消息文本、当前模型和两个显式时间回退，由 10,213 行降至 10,202 行。
- [x] 5E-2b 固定 `id`/`clientRequestId` 字符串化、session 归属、旧文本与模型回退、cursor/AgentRun/时间恢复、强制 `pending`、`restored`、未知字段保留、`rootPaths` 隔离和输入不变语义；Promise/resolver、消息补建、既有结果去重、checkpoint 移除、dispatcher 注册、保存和调度继续由 `app.js` 负责。
- [x] 5E-3：抽离后台结果严格判重和成功/异常结果消息构造，统一 `jobId`、AgentRun、错误状态、父任务排序、模型、时间、耗时与可选 usage 元数据；成功、异常和 reload 三处复用同一判重规则，`app.js` 由 10,202 行降至 10,176 行。
- [x] 5E-3 收口审计确认剩余代码均为运行时上下文适配、AgentRuntime、Abort、授权等待、Promise、消息写入、dispatcher、上传、持久化或 UI 副作用；以源码所有权护栏固定边界，不迁移 `createBackgroundServerContext()`、`runBackgroundSubAgentJob()`、`pumpBackgroundDispatcher()`、dispatch 或 restore 编排，5E 正式结束。
- [x] 5F-1：新增 `src/agent/compaction.js`，抽离压缩摘要识别、最新摘要后的主上下文选择和模型上下文上限三项纯策略；`app.js` 只注入后台/排队消息隔离谓词，并继续负责请求准备、状态和 UI 副作用，由 10,176 行降至 10,152 行。
- [x] 5F-1 固定无摘要、多个摘要取最新、detached 消息排除、输入数组不变及 Claude/OpenAI/DeepSeek/Gemini/未知模型上限语义；未修改 JSONL、API、压缩按钮、压缩结果、消息时序或持久化。用户补充 5F-2 必须保留最新几轮完整上下文，工具调用与结果不可拆分。
- [x] 5F-2：扩展 `src/agent/compaction.js`，抽离导入边界分组、API 消息映射、三轮完整上下文选择、服务端保留数兼容、摘要请求裁剪、Token 节省估算和摘要消息构造；`app.js` 只注入映射/文本/隔离函数并执行原有网络、归档、状态、DOM 和保存副作用，由 10,152 行降至 10,117 行。
- [x] 5F-2 默认至少保留最近 3 个非 detached 用户轮次，并在最近 6 条 API 可见消息落入更早轮次时向前对齐到该轮用户消息，确保工具调用、工具结果和最终回复不在保留边界处拆开；摘要请求只携带导入边界、真正移除的 API 前缀和服务端公式所需的 2 至 6 条尾部，未新增 `/api/compact` 字段或修改服务端。
- [x] 5F 收口确认剩余手动压缩代码均为配置、确认框、网络、归档、状态替换、DOM、保存和错误提示副作用，不再为减少行数强行迁移；随后作为独立产品增强完成 90% 自动压缩、同一 AgentRun 中途续行、上下文超限单次恢复和执行轨迹投影，未改变 5F 的纯策略所有权。
- [x] 5G-1：完成服务端主循环状态矩阵与职责所有权审计，并新增源码护栏固定凭据恢复、事件监听、问卷、授权、完成、取消和失败分支的现有顺序；本批不创建模块、不修改运行行为。
- [x] 5G-2：定向与全量回归均通过，审计结论正式落定为不创建 `agent-loop.js`。唯一可迁移候选只是单消费者的状态标签映射，无法隔离任何运行时副作用，跨文件接口成本高于维护收益；保留 `runServerAgentLoop()` 作为入口编排层，阶段 5 至此完成。

#### 5G-1 主循环状态矩阵

| 返回位置 / 状态 | 现有动作 | 后续流向与所有权 |
|---|---|---|
| 首次 `getAgentRun()` 返回 `waiting_credentials` | 调用 `resumeAgentRun()` 注入当前 Key 与 Base URL | 随后进入同一次 `watchAgentRun()`；网络和凭据副作用继续由 `app.js` 编排 |
| `watchAgentRun()` 返回 `waiting_credentials` | 不在返回点重复提交，直接进入下一轮 | 下一轮先重新读取快照并恢复凭据，避免在同一快照上重复动作 |
| `waiting_user_input` | 等待 `requestServerAgentInput()` | 问卷状态、DOM、持久化、通知和服务端提交继续由现有问卷编排持有 |
| `waiting_authorization` | 等待 `requestServerAgentAuthorization()` | 授权投影、用户决定、持久化和服务端提交继续由现有授权编排持有 |
| `completed` | 清空 `ctx` 与 `run` 两层 AgentRun ID / cursor，返回结果 | 终态清理由 `app.js` 原子完成，避免恢复时误接已完成运行 |
| `cancelled` | 抛出 `AbortError` | 复用现有取消与上层错误收束语义 |
| `failed` 或其他非等待终态 | 保留 `status` / `errorCode` 后抛错；`model_access_denied` 先刷新模型能力 | 错误分类、模型刷新和 UI 收束继续属于入口编排层 |

`watchAgentRun()` 在状态为 `running` 时自行长轮询并顺序投影事件，因此 `app.js` 不需要也不应新增独立的 `running` 返回分支。主循环同时持有 AgentRuntime 创建/监听、游标提交、网络恢复投影、问卷、授权、模型列表刷新和终态清理；把状态字符串改成跨文件枚举或动作标签不会形成可独立复用的纯领域边界。

#### 验收

- 纯对话、工具调用、编辑审批、命令执行、问卷和子 Agent 均正常。
- 暂停任务在 New API 中出现 `client_gone/context canceled` 仍属于用户主动中断的预期结果。
- 网络断开能显示重连状态并恢复原服务端流。
- 子 Agent 并行 usage 只合并一次，不打断主任务。
- 自动压缩阈值和压缩后上下文行为不变。
- `app.js` 保留跨领域装配、初始化、运行时副作用协调和必要的薄适配器；行数仅作为观察指标，不为达到数值目标迁移高耦合代码。

### 阶段 6：引入 esbuild 并清理兼容层

仅在阶段 1 至 5 稳定后进行：

#### 当前进度

- [x] 6A：固定 `esbuild 0.28.1` 开发依赖，新增 `src/frontend-entry.js` 作为唯一 bundle 入口，并以现有 `index.html` 的 31 个内部脚本实际顺序导入全部模块、`agent-runtime.js` 与 `app.js`。
- [x] 6A：新增 `scripts/build-frontend.mjs` 和 `npm run build:frontend` / `npm run check:frontend`，输出未压缩、保留函数名、关闭 tree-shaking 的 IIFE bundle、外置 source map 与 metafile；默认产物位于已忽略的 `dist/frontend/`，构建脚本不清理或覆盖 `dist/` 中其他文件。
- [x] 6A：完善顺序护栏，补入此前测试遗漏的 `theme-engine.js` 与 `subagents.js`，并验证经典脚本顺序与 bundle 入口完全一致、无重复、两次构建字节一致且产物可通过 `node --check`。
- [x] 6A 保持 `index.html`、`build_exe.py`、发布脚本和正式 EXE 资源清单不变，bundle 尚未进入 3011 或 3010 的运行路径；回退只需撤销本批依赖、入口、构建脚本与测试文件。
- [x] 6B：构建脚本在 `dist/frontend/` 生成 bundle 专用 `index.html`，移除 30 个模块/Runtime 脚本并在原 `app.js` 底部位置加载单一 bundle；样式与图标改用根路径，外部 KaTeX / marked 保持不变。当前 3011 可通过显式 `/dist/frontend/index.html` 访问，默认根页面继续加载原始脚本，3010 与 EXE 不包含该旁路产物。
- [x] 6B：自动检查固定预览标记、资源路径、单一 bundle、脚本执行位置、经典脚本完全移除和重复构建一致；HTTP 验证预览 HTML 与 bundle 均为 200。用户人工确认页面、会话、模型、只读工具、问卷刷新恢复、最终回答与工具轨迹、设置中英文切换及 `/compact` 取消流程均正常。
- [x] 6C-1：构建产物新增 `code.bundle.state.json` 和 `index.classic.html`；状态清单记录规范化输入列表、源码 SHA-256 指纹、esbuild 版本及 bundle、source map、metafile、预览页和经典回退页的大小与哈希。`--check` 只读校验输入与全部产物，构建开始前先移除旧状态，避免中断后的半成品被误判为新鲜产物。
- [x] 6C-1：`npm run verify:frontend` 独立执行新鲜度与 bundle 语法检查，`npm run check:frontend` 继续先构建再验证；临时目录回归覆盖两次构建一致、有效状态通过、bundle 篡改、伪造源码指纹和回退页缺失。默认 `index.html`、3011 根页、3010、EXE 和发布链均未切换。
- [x] 6C-2：开发默认 `index.html` 已切换为单 bundle，入口完成后写入就绪标记；bundle 加载或同步初始化失败会自动转到 `index.classic.html`。经典回退页的 31 个原始脚本直接从 `src/frontend-entry.js` 导入清单生成，避免维护两份顺序。
- [x] 6C-2：3011 在启动及根页面刷新时执行新鲜度检查，过期时按“检查、构建、复核”顺序串行重建，失败返回 503 而不继续加载半成品；Windows 下 Node 检查使用隐藏子进程参数，刷新页面不会闪现终端窗口。默认页、自动重建、经典回退和窗口行为均已完成自动与人工验收。
- [x] 6C-3：`build_exe.py` 在 PyInstaller 前强制构建并复核前端，EXE 同时携带默认 bundle、经典回退页面及原始脚本资源，不打包 source map、metafile 或构建状态；当前版本 spec 已由真实构建刷新并通过归档清单检查。
- [x] 6C-3：发布脚本在代码质量阶段增加独立前端门禁，正式发版强制构建后检查新鲜度与语法，`--dry-run` 只读校验且不改产物；实际打包前由 `build_exe.py` 再次复核。构建失败或产物过期会在 PyInstaller、Git 提交、标签和发布之前终止。
- [x] 6D：`v0.5.32` 作为首个 bundle 默认入口正式版本完成发布和人工验收后，已评估经典脚本兼容资源及 `window.Code` 中的剩余边界；真正的临时全局按 6D-1 至 6D-3 收口，经典回退与模块命名空间按 6D-4 决策保留，TypeScript 继续后置。
- [x] 6D-1：消息复制、消息图片预览/加载和输入区图片预览改为模块事件绑定，移除相应内联 `onclick` / `onload` 及 `window.copyMessageText` 桥接；经典回退、`window.Code` 模块命名空间、原始脚本资源和模型/会话/工具协议均保持不变。
- [x] 6D-2：默认页使用局部启动闭包创建 bundle 脚本并监听加载/初始化结果，移除内联 `onerror`、`window.__codeUseClassicFrontend` 和 `window.Code.frontendBundleLoaded`；成功状态改由 DOM 属性表达，经典回退的两类失败原因及生成方式保持不变。
- [x] 6D-3：`AgentRuntime` 注册归入 `Code.agent.runtime`，`app.js` 通过单一局部引用消费，删除独立的 `window.AgentRuntime` 顶层全局；运行时对象、文件名、加载顺序、经典回退、EXE 资源和服务端协议保持不变。
- [x] 6D-4：完成开发刷新、bundle 构建、EXE 打包、正式更新和故障恢复链路审计。经典页由唯一入口清单自动生成，自身约 50 KiB；随其保留的 `src/`、`app.js` 与运行时原始脚本合计约 834 KiB，相对约 30 MiB 的正式 EXE 成本有限，也不存在第二套手工加载顺序。
- [x] 6D-4：经典页明确作为同一正式版本的备用前端启动方式保留：只在 bundle 加载或同步初始化失败时使用原始脚本，不回退服务端、会话数据或应用版本。开发实例可以重建 bundle，正式 EXE 不能；当前应用内更新又依赖可用前端，安装脚本会清理旧版本且没有独立自动回滚，因此现在移除会把单一 bundle 故障放大为整个 UI 不可用。
- [x] 6D-4：`window.Code` 被 29 个实际模块用作运行时注册边界，不再视为待删除的过渡代理；后续若改为真正的 ES Module / TypeScript 架构，应作为独立迁移重新设计。只有在具备无界面更新或回滚入口、启动完整性检测和可验证的故障恢复后，才重新评估删除经典页面及原始脚本资源。

- 将 `src/` 作为源码，生成单个浏览器 bundle。
- 开发环境保留 source map，正式 EXE 不打包 source map、metafile 或构建状态等调试产物；在独立恢复能力具备前继续打包经典页面及其原始脚本。
- `index.html` 从多脚本顺序加载改为单入口。
- 移除已确认只用于过渡的全局代理；`window.Code` 本身保留为当前模块注册边界。
- 更新 `build_exe.py`、PyInstaller spec、发布脚本和版本检测测试。
- 后续再评估是否引入 TypeScript；不与 esbuild 首次接入同时进行。

#### 验收

- 开发版和正式 EXE 页面一致。
- 离线启动不依赖本地缺失的源码文件。
- source map 仅用于开发，不进入不必要的发布资产。
- 构建失败能阻止发布，不产生缺少脚本的 EXE。

## 6. 每批改动的标准流程

每个模块按以下步骤迁移：

1. 标记待迁移函数、状态字段、DOM 节点和调用方。
2. 为高风险行为补充或确认回归测试。
3. 新建模块并复制实现，暂不删除旧代码。
4. 通过兼容代理切换调用到新模块。
5. 完成语法检查、领域测试和浏览器冒烟测试。
6. 删除 `app.js` 中旧实现，确认不存在重复定义。
7. 再跑一次全量测试。
8. 单独提交 Git，提交信息只描述本次抽离范围。
9. 在当天开发日志中记录实际完成内容和验证结果，并更新 `docs/development-log/README.md` 索引。
10. 更新本计划中的进度与下一批入口。

禁止一次提交同时完成“大量搬迁 + 行为改造 + UI 调整”。

## 7. 测试矩阵

### 7.1 自动化检查

- `app.js` 与所有新 JS 文件语法检查。
- `server.py` 语法检查。
- 全量 Python 测试。
- 脚本加载顺序和全局模块存在性检查。
- EXE 资源清单检查。
- 旧会话和旧配置加载兼容测试。

### 7.2 浏览器冒烟测试

每个阶段至少验证：

1. 新建会话并完成普通对话。
2. 一个会话输出时切换到另一个会话，再切回查看流式内容。
3. 输出中刷新页面，确认续接；输出完成后刷新，确认滚动到底部。
4. 暂停回答，确认页面状态恢复。
5. 断网后观察重连提示，再恢复网络。
6. 计划模式、接受编辑模式、完全访问模式各跑一次工具任务。
7. 触发一次问卷并刷新恢复。
8. 运行一次前台子 Agent 和一次后台子任务。
9. 触发一次手动压缩和一次分支创建。
10. 打开代码、图片、MD、PDF 和 CSV/TSV 预览。
11. 切换深浅主题和中英文界面。
12. 检查设置、更新检测和正式 EXE 启动。

## 8. 风险与防护

| 风险 | 典型表现 | 防护措施 |
|---|---|---|
| 脚本加载顺序错误 | 模块未定义、页面白屏 | 在 `namespace.js` 统一注册；增加加载顺序测试 |
| 重复事件绑定 | 点击一次执行两次 | `events.js` 统一绑定；初始化函数保持幂等 |
| 状态双写 | 会话切换后数据串线 | 单一状态源；按 `sessionId` 更新；禁止渲染函数写状态 |
| 闭包依赖遗漏 | 拆出后变量为 undefined | 每批先列依赖表；通过显式参数或模块 API 注入 |
| 流式 DOM 重建 | 闪烁、滚动跳动 | 保留稳定节点，只增量更新文本和状态 |
| 会话格式漂移 | 旧历史无法加载 | 新字段默认值；保存前后兼容测试 |
| 正式 EXE 缺资源 | 开发版正常、正式版白屏 | 同步修改打包资源清单并执行正式构建冒烟 |
| 循环依赖 | 初始化顺序不稳定 | 遵守单向依赖；共享逻辑下沉到 `core/services` |
| 一次拆分过大 | 难定位回归、难回滚 | 每个模块独立提交，单批目标控制在可人工复核范围 |

## 9. 完成定义

满足以下条件后，`app.js 模块化` 才可在 `TODO.md` 标记完成：

- `app.js` 中剩余职责均能解释为跨领域装配、初始化、顶层事件协调、运行时副作用编排或必要薄适配器；行数不是硬性完成门槛。
- 业务实现已进入职责清晰的模块，模块间无循环依赖。
- 除 `window.Code` 和必要的第三方库外，不新增散落全局变量。
- 开发版、正式 EXE、更新后重启均能加载完整前端资源。
- 旧会话、旧配置和现有 New API 接口保持兼容。
- 自动化全量测试通过。
- 测试矩阵中的关键浏览器场景通过。
- 按日期开发日志记录各阶段实际结果并同步索引，`TODO.md` 状态与代码一致。

## 10. 推荐的下一步

阶段 1 至 5 已按职责所有权完成拆分与收口。`runServerAgentLoop()` 保留在 `app.js`，作为跨 AgentRuntime、网络、事件投影、问卷、授权、模型刷新和终态清理的入口编排层；源码护栏继续固定其状态顺序，不以目录结构或行数目标制造薄模块。

后续工作遵循以下边界：

1. 导入边界在最新摘要后的模型可见语义、模型真实上下文上限等产品兼容议题继续按 `TODO.md` 独立处理，不并入已完成的纯拆分。
2. 阶段 6 已完成：`v0.5.32` 作为首个 bundle 默认入口正式版本发布，并通过 3010/3011、默认页面和经典回退人工验收；6D-1 至 6D-3 已收口消息交互、bundle 启动及 AgentRuntime 顶层全局。
3. 6D-4 已确认经典页面是正式版故障恢复层，`window.Code` 是当前模块注册边界，两者均不再作为本轮待删除兼容项；未来的 ES Module / TypeScript 迁移以及无界面更新、回滚和启动完整性恢复能力按独立需求重新规划。
