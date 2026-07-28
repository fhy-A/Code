# Code 开发日志

> 记录 Claude Code、Codex 以及其他协作方的重要改动，按时间倒序。

## 2026-07-28 18:31 · Codex

### 3011 隔离开发实例、workbar 回跳诊断与 Dev 标识

- 新增 `dev_server.py` 和 `启动Code开发版.bat`：开发实例默认使用 3011、仓库 `data/`、独立重启入口和 `dev` 运行模式，可与 3010 正式版同时运行；桌面 `Code Dev.lnk` 已在本机改为调用该脚本，但快捷方式本身不纳入仓库。
- 修复 workbar 登录完成后固定回到 3010 的问题，授权回跳地址改为当前页面来源，兼容 3010、3011 和自定义开发端口；两套端口的浏览器登录态与本地配置仍按浏览器同源规则隔离。
- 为 workbar Key 同步增加不泄露敏感信息的结构化诊断，区分令牌列表、完整 Key 读取阶段以及 HTTP、超时、网络和响应格式错误；前端提供对应的中英文提示，不记录 Access Token、API Key、响应正文或原始异常。
- 开发实例的侧栏产品名、页面标题、任务状态标题和托盘悬停/菜单改为 `Code Dev`；正式版继续保持 `Code`，未改变图标。冻结打包实例会忽略继承的开发端口与模式环境变量，强制使用 3010 和正式版标识，避免开发启动设置影响发布产物。
- 重启入口新增应用目录内 Python 文件校验；启动脚本只复用属于当前仓库的 3011 服务，端口被其他程序占用时明确停止，避免误操作其他进程。
- 在 `TODO.md` 记录低优先级状态提示优化：后续细分平台无令牌、完整 Key 不可读和 Key 已全部添加，不影响现有本地缓存 Key 的继续使用。
- 验证：
  - `python -m pytest -q`：**843 passed, 236 subtests passed**；
  - `python -m py_compile server.py dev_server.py`、`node --check app.js`、`node --check src/features/settings.js`、`node --check src/core/i18n.js` 与 `git diff --check` 通过；
  - 用户人工确认 3010/3011 可同时运行、workbar 回跳与模型同步恢复、`Code Dev` 网页及托盘标识正确，并确认正式版端口保护符合预期。

**涉及文件**：`dev_server.py`、`启动Code开发版.bat`、`server.py`、`app.js`、`index.html`、`src/features/settings.js`、`src/core/i18n.js`、`tests/test_dev_server.py`、`tests/test_server.py`、`tests/test_routes.py`、`tests/test_frontend_modules.py`、`tests/test_image_vision_and_browser_refresh.py`、`README.md`、`docs/development-handoff.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-28 12:04 · Codex

### 发布说明正文保留与占位硬拦截

- 修复 `release.py` Phase 5 无条件覆盖预写发布说明的问题：已有文件会保留人工正文，仅重新生成日期、版本号、构建信息、文件大小和 SHA-256；旧版英文模板和仅包含正文的预写文件均可兼容提取。
- 新生成的发布说明改为中文模板，并使用明确的正文边界与自动元数据区；发布前校验正文非空、标题与安装包版本一致，拦截“待补充”、`TBD`、`[TODO]`、`DRY_RUN_SHA256` 和 `vX.Y.Z` 等占位内容。
- 占位校验位于 Git 提交、打标签和 GitHub Release 之前，`--yes` 只能跳过交互确认，不能绕过校验；人工流程编辑后会重新读取文件，恢复命令中的默认分支名同步修正为 `master`。
- 新增 `tests/test_release_script.py`，覆盖中文模板与默认拦截、旧模板正文保留及元数据刷新、正文文件保留、五类占位识别和校验门禁顺序。
- 同步更新 `AGENTS.md`、`CLAUDE.md` 与 `docs/release-guide.md`，并从 `TODO.md` 移除对应已完成事项。
- 验证：
  - `python -m pytest tests/test_release_script.py -q`：**5 passed, 5 subtests passed**；
  - `python -m pytest tests -q`：**822 passed, 233 subtests passed**；
  - `python release.py 0.5.31 --dry-run`、`python -m py_compile release.py` 与 `git diff --check` 通过。

**涉及文件**：`release.py`、`tests/test_release_script.py`、`AGENTS.md`、`CLAUDE.md`、`docs/release-guide.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-28 11:54 · Codex

### 协作授权、实施门禁与发布规范

- 在 `AGENTS.md` 与 `CLAUDE.md` 增加强制协作门禁：收到新需求、优化建议或 Bug 后，必须先完成只读调查，向用户说明需求理解、现有实现、影响范围、初步方案、主要取舍与验收方式；用户明确同意前不得修改业务代码。
- 明确需求歧义不能由 Agent 自行猜测，方案确认前不得先进行大篇幅实现；实施过程中若需要扩大范围或改变既定行为、数据结构、安全边界或交互方式，必须暂停并重新取得用户确认。
- 补充操作授权、诊断与修复分离、临时测试参数恢复、协作文档同步、中文发布说明及数据/协议兼容性六项边界；本地提交仍按阶段规则自动完成，推送、标签、发布、数据删除和线上配置修改必须获得明确授权。
- 在 `docs/development-handoff.md` 和 `docs/release-guide.md` 同步简要规则，并将上一级工作区的 `AGENTS.md`、`CLAUDE.md` 保持为相同标准；上一级目录不属于 Git 仓库，不纳入本提交。
- 记录 `release.py` 当前会覆盖预写发布说明且 `--yes` 自动确认的已知缺口，后续需修复为可验证、无占位文案的自动发布闭环。
- 本阶段仅修改协作与交接文档，不涉及业务代码、界面或运行时行为。

**涉及文件**：`AGENTS.md`、`CLAUDE.md`、`docs/development-handoff.md`、`docs/release-guide.md`、`TODO.md`、`CHANGELOG.md`

---

## 2026-07-27 · Codex

### Agent 工具过程展示、轮次时序与内容拦截分流（开发版本基线 v0.5.29）

- 将首个模型轮与后续工具续行轮明确分开：第一轮显示“等待模型响应”，工具完成后的后续轮显示“等待模型继续”，延迟提示也按轮次区分；过程状态右侧计时统一表示整项任务总耗时，不会在工具轮之间重置。当前模型轮次写入 durable Agent 快照，刷新恢复后仍能恢复正确文案。
- 将模型随工具调用返回的过程内容从普通“思考摘要”改为紧凑的工具过程卡：工具名称、规范化参数、运行状态、结构化成功/失败结果和参数别名在同一区域投影；最终回答继续独立展示。连续相同失败折叠显示重复次数，默认收起详细结果，编辑建议等特殊工具结果也能正常终结运行态。
- 前端事件投影完整保留服务端新增的 `outcome`、结构化 `result` 和 `argumentAliases`；刷新恢复、中英文即时切换、停止任务、SSE 增量以及旧记录回填继续沿用既有兼容边界，不把工具过程内容重复写进最终回答。
- 修复显式内容策略终止被误判为空回复的问题：上游返回 `finish_reason=content_filter / safety / blocked` 时立即以 `content_filtered` 结束，不再消耗一次无动作续行预算或重复发送完整上下文；前端显示专用的“响应被内容策略拦截”说明与恢复建议。
- 修复结构化 Agent 错误已经持久化并展示后，外层表单错误处理仍追加第二条纯文本错误的问题；已处理错误会带内部渲染标记，确保同一故障只显示一张错误卡。
- 验证：
  - `python -m pytest -q`：**822 passed, 228 subtests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/core/i18n.js`、`node --check src/ui/messages.js` 与 `git diff --check` 通过；`server.py` 仍只报告既有 Windows 路径无效转义 `SyntaxWarning`；
  - 用户使用真实 Claude 渠道人工确认：`content_filter` 只产生一张结构化错误卡，显示原始 `finish_reason`，没有重复错误或额外空回复重试，任务计时正常结束。

**涉及文件**：`server.py`、`app.js`、`styles.css`、`src/core/i18n.js`、`src/ui/messages.js`、`tests/test_agent_runtime.py`、`tests/test_frontend_modules.py`、`tests/test_model_runtime.py`、`tests/test_p0_stability.py`、`tests/test_routes.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### Agent 工具协议校验与重复失败熔断（开发版本基线 v0.5.29）

- 在服务端建立与内置工具定义共源的轻量 JSON Schema 校验，覆盖对象、数组、必填字段、字段类型、枚举、嵌套项、数量限制和 `additionalProperties: false`；Agent 工具轮和直接 `/api/tools/*` 入口均不能再把缺失或未知字段送入执行器。参数错误返回稳定的 `invalid_tool_arguments`、字段路径和原因，不再把“缺少 `path`”误报为“文件不存在”。
- 为部分 Claude 模型的历史参数习惯增加仅限 Agent 模型边界的窄兼容：`read_file.file_path` 在没有冲突时规范化为正式的 `path`，随后使用规范化参数计算指纹、写入模型历史并执行；直接工具 API 继续严格拒绝 `file_path`，正式协议和 Schema 未改变。兼容转换会记录 `argumentAliases` 供诊断。
- 保留 `status: completed` 作为“工具生命周期已经终止、不可重放”的既有语义，新增独立的 `outcome: succeeded / failed` 并随 durable record、公开快照和 `tool_completed` 事件传递；旧记录按 `result.ok` 回填，避免破坏授权恢复、幂等重放、命令未知状态和子 Agent 调度。
- 新增基于“规范化工具指纹 + 相同错误签名”的重复失败保护：前三次真实失败允许模型纠正，第三次结果明确标记重试上限；第四次完全相同的调用不再触碰执行器，并进入一次无工具收尾轮。参数改变、工具改变、错误类型改变或同指纹成功都会解除连续失败判断，避免误伤有效恢复。
- 重复失败保护和强制收尾状态均可持久恢复；工具调用 ID 重放、写入/删除的 `_operationId` 幂等协议、问卷嵌套参数、四种权限模式、编辑/命令授权和子 Agent 继续沿用既有边界。
- 验证：
  - `python -m pytest tests/test_routes.py tests/test_agent_runtime.py tests/test_model_runtime.py -q`：**137 passed, 22 subtests passed**；
  - `python -m pytest -q`：**821 passed, 228 subtests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/core/i18n.js` 与 `git diff --check` 通过；`server.py` 仍只报告既有 Windows 路径无效转义 `SyntaxWarning`；
  - 本阶段未改前端投影和状态文案，相关人工验收留到下一阶段。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`tests/test_routes.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 模型首次有效响应 120 秒硬截止（开发版本基线 v0.5.29）

- 为服务端模型运行时增加 **120 秒首次有效响应硬截止**，从本轮请求开始统一计时，并由同一轮的备用 Key 共用；不会因切换 Key 重新获得一段完整等待时间。只有非空正文、思考增量或工具调用算作有效响应，HTTP 响应头、SSE 注释/心跳、空事件、角色事件和仅 usage 事件均不会解除截止。
- 截止时间按绝对单调时钟计算，每次读取上游流之前都使用剩余时间约束底层 socket；持续心跳不能再刷新等待窗口。两分钟内收到有效响应后解除首响截止，后续长回答继续沿用原有 180 秒流空闲超时，不把两分钟误当成整条回复的总时长上限。
- 首响超时会立即关闭子模型流，将模型运行时和父 Agent 一并置为 `failed`，透传可重试的 `model_response_timeout`，清空活动模型轮并触发现有健康快照回滚；前端提供“模型首次响应超时”的中英文错误说明，不再无限停留在慢上游提示。
- 模型运行终态现在会在通知等待方之前清除请求 payload 和 Key，消除终态已可见但敏感请求字段尚未释放的短暂竞态。
- 验证：
  - `python -m pytest tests/test_model_runtime.py tests/test_agent_runtime.py::TestDurableAgentRuntime::test_agent_stops_when_first_meaningful_model_response_times_out tests/test_frontend_modules.py -q`：**116 passed, 2 subtests passed**；
  - `python -m pytest -q`：**815 passed, 228 subtests passed**；
  - `python -m py_compile server.py`、`node --check app.js` 与 `node --check src/core/i18n.js` 通过；`server.py` 仍只报告既有 Windows 路径无效转义 `SyntaxWarning`；
  - 人工真实两分钟时序验收待用户确认后补记。

**涉及文件**：`server.py`、`app.js`、`src/core/i18n.js`、`tests/test_model_runtime.py`、`tests/test_agent_runtime.py`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### Agent 无有效动作恢复与首反馈时序复审（开发版本基线 v0.5.29）

- 复审 v0.5.29 的三分类实现后，将“完全空回复、只有 reasoning 没有正式回答、只有过程性承诺”统一为同一个无有效动作闭环：三种结果共用 **1 次**自动续行预算，第一次自动提醒模型立即执行或给出完整答案，第二次无效轮次明确以 `empty_response` 停止；跨类型切换也不会重置预算，避免“空回复 → 仅思考 → 空承诺”无限循环。
- 工具调用和实质性最终回答被视为真实进展，会清空此前的无动作计数；续行提示只保存在服务端 Agent 上下文，不伪装成用户在会话中手工发送的新消息。每个模型轮新增 `outcome`，并发出可恢复的 `model_recovery` 事件，前端显示“模型未给出有效结果，正在自动续行（1/1）”。
- 完善过程性承诺识别：兼容“好的 / Okay”等确认前缀，保留真正的短承诺检测；含完成/结果证据、实质性冒号后文、多行结果、代码块和较长回答不再误判，“First, update... Then...”等用户可直接采用的步骤说明也不会被当作空承诺。
- 修复 Agent 终态持久化竞态：此前 `completed / failed / cancelled` 会先唤醒等待方、再写磁盘，快速刷新可能读到缺少 `errorCode` 的旧快照；现在终态、错误码和无动作计数先落盘再通知。`errorCode / nonActionCount` 同步写入 durable record、重载对象和公开快照，重启不会获得新的续行预算。
- 模型轮开始后立即显示“已提交模型，正在等待首个响应”，不再先静默显示 25 秒笼统“处理中”；25 秒升级为“首个响应尚未到达”，60 秒继续显示慢上游/可能重试提示。收到首个 reasoning、正文或工具增量后恢复正常处理状态。
- 空模型轮不再持久化或展示字面量 `(empty response)`；纯 reasoning 保持为思考内容，不再复制成最终回答。兼容已经由 v0.5.29 持久化的 `empty_response` 等待任务，前端会自动转入同一续行闭环，无需用户再次点击旧按钮。
- 验证：
  - `python -m pytest tests/test_agent_runtime.py tests/test_p0_stability.py -q`：**86 passed, 13 subtests passed**；
  - `python -m pytest -q`：**812 passed, 226 subtests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/core/i18n.js` 与 `git diff --check` 通过；`server.py` 仍只报告既有 Windows 路径无效转义 `SyntaxWarning`；
  - 用户人工确认无有效动作自动续行、首反馈等待状态与整体交互正常。

**涉及文件**：`server.py`、`app.js`、`src/core/i18n.js`、`tests/test_agent_runtime.py`、`tests/test_p0_stability.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 模型运行时错误分流、流式观感与慢上游反馈收口（v0.5.29）

- 将模型授权失败与上游瞬时故障拆成稳定的结构化语义：模型无权访问返回 `model_access_denied` 且不自动重试，`408 / 425 / 429 / 5xx`、网络和流中断归为可恢复的 `upstream_error`；Agent 运行快照同步保留 `errorCode / transient`，前端按错误类型提供本地化说明和恢复建议。
- 模型刷新记录每把 Key 实际可见的模型集合，请求时优先选择列出目标模型的 Key；遇到模型授权失败会刷新模型目录，避免继续轮询已知无权 Key，也不再以固定延时把授权错误伪装成可重试故障。
- 对上游已经返回的大块纯文本 SSE 做有界、Unicode 安全的显示级平滑投影，最多拆分 12 帧并限制批次等待次数；工具调用、函数调用、`finish_reason`、usage 和 `[DONE]` 边界保持原样，不改变上游协议、持久化内容或工具执行时序。
- 同一任务计时中新增 25 秒“等待模型响应”和 60 秒“上游响应较慢”提示，首个思考、正文或工具增量到达后恢复正常状态。workbar 日志已确认其渠道内部存在一次重试，因此 Code 不叠加第二层 502 自动重试，避免把单次故障放大为更长的无反馈等待。
- 真实链路对照显示：workbar 渠道连通测试可成功，但 Code 使用同一模型的普通令牌路径即使关闭思考、工具和扩展参数，最小流式请求仍可能在渠道内部重试后返回 502。现阶段保留为网关普通请求路径与渠道测试路径差异的后续调查，不在本版本写入未经验证的兼容补丁。
- workbar 配置状态同步：用户确认 `GENERATE_DEFAULT_TOKEN` 与 `QuotaForNewUser` 的开发推送已经完成，待办据此关闭；本仓库未包含对应服务端配置改动。
- 验证：
  - `python -m pytest -q`：**811 passed, 226 subtests passed**；
  - 用户人工确认 25 秒与 60 秒两级慢响应提示已经生效；
  - Claude 模型最小请求、关闭思考、关闭工具及渠道测试对照均已完成，未发现 Code 请求体中的单一可疑字段，502 根因仍归入后续上游稳定性调查。

**涉及文件**：`agent-runtime.js`、`app.js`、`server.py`、`src/core/i18n.js`、`tests/test_frontend_modules.py`、`tests/test_model_runtime.py`、`tests/test_p0_stability.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 长会话时间线与侧栏拖动性能收口（开发版本基线仍为 v0.5.28）

- 将会话区左侧时间线改为 Codex 风格短线：默认低干扰，当前主节点和所有进入消息视口的会话轮次分别突出；点击节点继续平滑定位到对应用户消息，悬停时以当前节点为最长、最亮主节点，并让上下各两个相邻节点按距离递减长度和颜色，形成对称阶梯。
- 每个节点按“用户消息 + 该轮最后一条有效模型最终回答”生成预览：用户消息作为单行加粗标题并限制长度，跳过系统消息、工具轮次、流式中间态和工具规划占位；模型回答最多显示三个非空内容行，空行不计入行数。预览层新增 Markdown 到纯文本转换，移除标题、强调、列表、链接和代码围栏等格式标记，但不改写原始会话消息或正文 Markdown 渲染。
- 长会话时间线使用固定 9 px 节点节距和浏览器可用高度最多 70% 的动态窗口，按实际高度计算可见节点数；只渲染当前窗口，鼠标位于时间线时可用滚轮按 3 个节点移动窗口，聊天滚动会自动跟随当前轮次。中间会话区宽度低于 560 px 时暂时隐藏时间线，空间恢复后自动显示。
- 优化左右侧栏拖动：指针移动通过单帧 `requestAnimationFrame` 合并更新，结束时才持久化最终宽度；拖动期间固定长会话消息区和预览内容宽度，避免每次指针移动触发大段文本重排，并在结束或取消时完整清理临时状态。修复窄屏隐藏预览后仍保留空白网格列的问题。
- 补齐时间线导航、节点跳转、无标题和暂无最终回答的中英文文案及列表/当前位置语义；中英文即时切换、点击定位、滚轮窗口、可见节点计算和窄屏恢复均保持一致。
- 验证：
  - `python -m pytest -q`：**805 passed, 226 subtests passed**；
  - `node --check app.js`、`node --check src/core/i18n.js`、`node --check src/features/preview.js`、`node --check src/ui/timeline.js` 与 `git diff --check` 通过；
  - 真实长会话浏览器验证：720 px 高度下动态展示约 54 个节点，时间线滚轮窗口、多个可见轮次、用户/模型预览、Markdown 纯文本化、窄宽自动隐藏与恢复正常；
  - 用户人工确认时间线位置、节点密度、高度比例、多个可见节点、三行非空预览、纯文本回答和悬停阶梯效果正常，并授权提交。

**涉及文件**：`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`src/features/preview.js`、`src/ui/timeline.js`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 会话导入选择器与顶部入口视觉收口（开发版本基线仍为 v0.5.28）

- 将原有导入弹窗重构为可伸缩的结构化选择器：标题区明确本机历史来源，Claude Code / Codex 来源标签显示总数并支持重新扫描；新增本地搜索、“可导入 / 全部”筛选、当前结果全选、可见数量和底部已选数量，默认只展示缺少或有更新的可导入会话，已导入和已在 Code 继续的会话仍可在“全部”中查看但不可重复选择。
- 搜索和筛选只作用于已扫描缓存，不再每次键入都请求后端；已选会话跨搜索与筛选保持，切换来源时清空搜索和选择并重新扫描。导入批次的串行执行、进度、主动停止、失败重试、来源锁定及安全快照协议保持不变。
- 完善弹窗键盘与可访问性：支持 `Esc` 关闭、焦点圈定与返回、左右方向键切换来源、稳定的对话框语义和动态状态播报；加载、忙碌、空结果、失败、状态徽标、选择数量以及中英文即时切换均保持同步。搜索框移除继承的重复内层焦点环，重新扫描图标与文字统一居中，主“导入到 Code”按钮增加明确主题色底色并区分禁用态。
- 顶部导入/导出入口改为同一视觉语言的 18 px 实心文件夹图标，分别用向下/向上箭头表达导入和导出；清理按钮组与 Token 统计之间的多余竖线，并将导入悬停提示统一为“从本机 Claude Code 或 Codex 导入历史会话”。图标继续使用主题色、独立悬停反馈和无障碍标签。
- 本阶段没有修改后端导入接口、来源识别、幂等更新、迁移边界或文件访问范围。
- 验证：
  - `python -m pytest tests/test_frontend_modules.py tests/test_p2_coverage.py tests/test_subagent_frontend.py tests/test_server.py -q`：**387 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**799 tests passed**；
  - `node --check app.js`、`node --check src/core/i18n.js` 与 `git diff --check` 通过；
  - 真实来源浏览器验证：Claude Code 为可导入 69 / 总计 74，Codex 为可导入 53 / 总计 60；本地搜索、跨搜索保留选择、来源切换重置、重新扫描、全部状态、`Esc` 焦点返回、中英文动态文案、顶部图标和弹窗入口均正常；
  - 用户逐项检查并修正确认了入口图标、分隔线、弹窗顺序、搜索焦点、重新扫描对齐和主按钮强调效果，随后授权提交。

**涉及文件**：`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 导入来源徽标生命周期收口（开发版本基线仍为 v0.5.28）

- Codex / Claude Code 来源徽标改为“刚导入快照”状态，而非永久会话属性：首次导入、未续聊的原地更新和新更新快照显示徽标；重命名、置顶和调整项目归属不会误清除；用户在 Code 中继续对话后即时隐藏，创建分支时新分支不继承短期徽标，未修改的原会话保持原状态。
- 后端新增稳定的 `sourceBadgeVisible` 投影并同步写入会话索引，统一覆盖新建、保存、追加消息、项目调整、迁移、分支和重复导入路径；旧索引缺少字段时按持久化 `importState` 惰性回填，避免重启或旧数据导致徽标重新出现、无法消除或状态失真。
- 前端在会话保存响应后同步本地徽标状态，无需刷新页面；徽标悬停说明其临时含义，导入结果区提供可持续查看的生命周期提示，首次隐藏时显示一次轻量说明。该说明单独延长至 7 秒，其他通知仍保持默认 3 秒。
- Session Info 新增永久“来源”字段：徽标隐藏或创建分支后仍可查看 `Code / 源自 Codex / 源自 Claude Code`，避免短期状态承担长期溯源职责。
- 补齐上述状态、悬停说明、导入提示、Session Info 和通知的中英文即时切换；同时在 `TODO.md` 记录低优先级“从文件导入”方案，仅自动识别任意位置的已知 Codex / Claude Code JSONL，并继续遵守只读预检和现有导入安全闭环。
- 验证：
  - `python -m pytest tests/test_server.py tests/test_projects.py tests/test_frontend_modules.py tests/test_p2_coverage.py tests/test_subagent_frontend.py tests/test_concurrency.py -q`：**427 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**797 tests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/core/i18n.js`、`node --check src/services/notifications.js`、`node --check src/ui/panels.js` 与 `git diff --check` 通过；`server.py:3176` 仍仅报告既有的无效转义 `SyntaxWarning`；
  - 用户人工确认来源徽标隐藏时机、长期来源展示和延长后的轻量提示均正常。

**涉及文件**：`server.py`、`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`src/services/notifications.js`、`src/ui/panels.js`、`tests/test_server.py`、`tests/test_projects.py`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### Token 总输入与缓存读写语义收口（开发版本基线仍为 v0.5.28）

- 统一实时响应、后台任务、子 Agent、会话账本和导入会话的 Token 协议：`input` 表示包含缓存命中部分在内的总输入，`cache` 表示总输入中的缓存读取子集；缓存读取不再被重复加入 Token 合计，合计继续使用“总输入 + 输出”。
- 按上游协议分别归一化：
  - OpenAI 兼容接口的 `prompt_tokens` 直接作为总输入，读取嵌套或顶层缓存命中字段时不再次累加；
  - Claude 原始 usage 将 `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` 计算为总输入，并把缓存创建单独投影为可选 `cacheWrite`；
  - Codex 导入保持其输入字段已包含缓存的现有语义，Claude Code 导入按 Claude 原始拆分字段重算；旧会话快照不做破坏性迁移。
- 顶部统计和 Session Info 的“输入 / 缓存”明确改为“总输入 / 缓存读取”；仅当上游明确报告缓存写入字段时显示“缓存写入”明细，单条响应仅在缓存写入大于零时显示紧凑标记。
- 单条响应的输入、输出、缓存读取和缓存写入均增加可区分的本地化悬停说明；中英文切换继续即时更新。上下文统计同时兼容规范化后的 `lastUsage.input` 与原始 `prompt_tokens`。
- 验证：
  - `python -m pytest tests/test_server.py::TestCodexImport tests/test_frontend_modules.py -q`：**138 passed**；
  - `python -m pytest tests/test_server.py tests/test_frontend_modules.py tests/test_p2_coverage.py tests/test_subagent_frontend.py tests/test_concurrency.py -q`：**403 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**793 tests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/ui/messages.js`、`node --check src/ui/panels.js`、`node --check src/core/i18n.js` 与 `git diff --check` 通过；
  - 用户人工确认 Token 统计、字段展示与界面状态正常。

**涉及文件**：`server.py`、`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`src/ui/messages.js`、`src/ui/panels.js`、`tests/test_server.py`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 导入批次主动停止与失败项一键重试（开发版本基线仍为 v0.5.28）

- 新增独立、可测试的会话导入批次运行器，保持逐项串行和来源快照锁定；用户请求停止后允许当前单项确定性完成，只阻止尚未开始的项目，不中断后端请求、不回滚已成功结果，也不会因取消时序造成来源状态未知。
- 导入弹窗新增批次进度、进度条和“停止导入”操作；运行期间锁定来源、搜索、全选与会话复选框，停止阶段明确显示“等待当前项完成”，刷新侧栏与来源列表期间显示独立收尾状态，关闭后重新打开弹窗仍能恢复当前批次视图。
- 批次结果扩展为新增、更新、新快照、无变化、已续聊、失败和已停止分类；成功、部分失败及停止使用不同结果色，未开始的项目刷新后继续保持可导入。
- 失败项保留标题、来源路径、稳定 `errorCode` 和 `retryable`：
  - 可重试失败会出现“一键重试失败项”，新批次只包含这些失败项目，不重复处理已成功或已停止项目；
  - 不可重试失败标记为“需修复来源”，详情区提供本地化原因和原始错误码；
  - 网络失败默认视为可重试，后端明确返回的 `retryable` 仍为最终判断依据。
- 新增导入运行、停止、重试、失败详情和常见来源错误的中英文文案；语言切换时正在运行的进度、停止状态、结果和失败详情会即时更新。
- 验证：
  - `python -m pytest tests/test_frontend_modules.py tests/test_server.py tests/test_p2_coverage.py -q`：**355 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**793 tests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/core/i18n.js`、`node --check src/features/session-import.js` 与 `git diff --check` 通过；
  - 浏览器可控时序验证：3 项批次停止后仅首项发出请求，结果为新增 1 / 已停止 2；临时失败重试仅再次请求失败项；中英文进度和结果即时切换，控制台无错误；
  - 用户人工确认批次进度、停止后续项目、剩余项继续导入与界面状态均正常。

**涉及文件**：`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`src/features/session-import.js`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### 导入来源一致性快照与异常路径稳健性（开发版本基线仍为 v0.5.28）

- Codex / Claude Code 导入改为单次一致性快照：先将来源流式复制到 `SpooledTemporaryFile`，4 MiB 以内保留内存、超过后自动落临时文件；消息解析、来源 SHA-256 和持久化元数据全部使用同一快照，不再解析一次、重新打开来源再哈希。
- 复制前后以及解析完成后核对文件设备、inode、大小和纳秒级修改时间；来源在读取/解析期间被写入、替换、移动或删除时停止导入并返回可重试的 `409 import_source_changed`，不会写入半截会话。无换行的损坏尾记录单独标记为可重试的 `import_source_incomplete_jsonl`。
- JSONL 转换改为严格记录边界：
  - 非法 JSON、非对象记录和无效 UTF-8 不再被静默跳过；
  - 空会话、文件缺失、权限拒绝、来源不可用、非法文件类型和来源根目录越界均使用稳定 `errorCode / retryable / HTTP status`；
  - 失败发生在持久化之前，不创建会话文件或索引记录，为后续“失败项重试”提供可靠错误语义。
- `/api/import/sessions` 只接受所选运行时会话目录内的 `.jsonl`，解析后的真实路径仍必须位于 Codex 或 Claude Code 来源根目录，阻止通过手工请求读取范围外文件。
- 扫描列表按来源运行时自身的稳定会话 ID 去重；同一 ID 存在多份文件时确定性选择内容更完整（文件更大）、随后更新时间更晚、最后规范路径排序更高的候选，并以 `duplicateCount` 暴露合并数量。无稳定 ID 时继续按规范路径区分。
- 单个损坏、无权限或扫描中消失的文件只会被隔离，不影响其他来源；标题和元数据合并为一次前缀扫描，避免列表阶段重复打开每个文件。
- 验证：
  - `python -m pytest tests/test_server.py tests/test_p2_coverage.py -q`：**254 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**791 tests passed**；
  - `python -m py_compile server.py`、`node --check app.js` 与 `git diff --check` 通过；
  - 真实来源只读扫描：Codex 60 条约 512 ms、Claude Code 74 条约 879 ms，当前均未发现重复来源组。

**涉及文件**：`server.py`、`tests/test_server.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-27 · Codex

### Codex / Claude Code 重复导入幂等与安全更新快照（开发版本基线仍为 v0.5.28）

- 导入会话新增持久化 `importState`：记录来源类型、稳定来源会话 ID、规范路径、文件大小/时间、来源 SHA-256、转换后消息快照 SHA-256、根会话和 Code 侧是否已修改，用于区分同一路径、移动后的路径、来源更新与 Code 续聊。
- 重复导入改为四类确定行为：
  - 首次导入创建会话；
  - 来源内容未变化时返回 `unchanged`，不重复写消息、不追加索引；
  - 来源有更新且 Code 侧尚未修改时原地刷新，保留用户重命名、项目归属和 `cwd`；
  - Code 侧已经续聊、压缩或仍有运行状态时，来源更新会创建按来源哈希确定 ID 的新快照，原会话及 Code 续聊内容不会被覆盖；重复导入同一更新快照仍为幂等操作。
- 来源匹配优先使用 Codex / Claude Code 自身会话 ID，再回退到规范路径；来源文件移动、仅更新时间变化或重复点击均不会产生无意义副本。旧版已导入会话在首次重新导入时安全补齐状态，存在差异时按冲突快照处理。
- 导入列表新增“可导入 / 已导入 / 已在 Code 继续 / 有更新 / 有更新·将新建快照 / 旧版导入”状态；无变化和已续聊但来源未更新的会话禁选，打开弹窗或切换来源时会在预加载内容后强制重新检查，避免缓存掩盖来源更新。
- 批量导入完成后保留弹窗并原地刷新侧栏和来源列表，不再整页重载；结果按新增、更新、新快照、无变化、已续聊和失败分别计数。导入期间冻结来源、搜索、全选和已选会话快照，避免异步切换造成列表索引错位。
- 补齐中英文即时切换、状态徽标、结果区和可访问性提示。
- 验证：
  - `python -m pytest tests/test_frontend_modules.py tests/test_server.py tests/test_p2_coverage.py -q`：**340 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**778 tests passed**；
  - `python -m py_compile server.py`、`node --check app.js`、`node --check src/core/i18n.js` 与 `git diff --check` 通过；
  - 浏览器实际验证了弹窗布局、选择计数、状态徽标和中英文即时切换；
  - 用户人工确认首次导入、原地更新、Code 续聊后的安全快照、无整页刷新及缓存重新检查均正常。

**涉及文件**：`server.py`、`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`tests/test_server.py`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-26 23:48 · Codex

### Codex / Claude Code 导入消息兼容与迁移安全边界（开发版本基线仍为 v0.5.28）

- Codex 与 Claude Code 导入会话新增不可见且可持久化的迁移边界，明确告知后续模型该会话来自迁移，并要求只使用 Code 当前实际提供的工具；历史工具、权限和工作区状态仅作为审计记录，不得重放或假定仍然有效。
- 导入转换从纯文本扩展为兼容消息协议：
  - 保留正常用户/助手文本、图片、模型名、原始时间戳、usage 和可读 reasoning/thinking 摘要；
  - Codex `function/custom/tool_search/web_search/image_generation` 与 Claude `tool_use/tool_result` 转换为配对的历史工具轨迹；
  - 所有导入工具轨迹统一标记 `imported / native:false / replayable:false / skipApi:true`，不会混入后续模型请求或当前工具时序；
  - 超过 12,000 字符的工具载荷保留首尾，并记录原始长度与 SHA-256，兼顾审计与会话体积。
- 清理外部运行时注入内容：Codex 的 AGENTS、环境、浏览器状态、文件包装和命令包装只保留其中真实用户请求；Claude 的 `system-reminder`、`isMeta` 与 `isSidechain` 内容不进入主会话，纯 `agent-*` 旁路文件不再出现在导入列表。
- 会话压缩按实际模型消息计数，排除不可发送的历史工具轨迹；压缩后继续保留迁移边界。Markdown 导出过滤隐藏系统消息，但仍忠实保留普通对话与工具审计内容。
- 验证：
  - `python -m pytest tests/test_server.py tests/test_frontend_modules.py tests/test_p2_coverage.py -q`：**330 passed, 17 subtests passed**；
  - `python -m unittest discover -s tests`：**768 tests passed**；
  - `node --check app.js` 与 `git diff --check` 通过；
  - 真实 Codex / Claude Code 样本验证了文本、图片、reasoning、工具配对、截断、usage 和旁路会话排除，导入工具轨迹可重放数量为 0；
  - 用户人工确认导入展示、工具日志、继续对话、当前工具约束与压缩后约束均正常；导出文件中的关键词命中经结构核验仅位于历史 `Tool Call / Tool Result` 代码 diff 和测试说明，隐藏系统消息命中为 0。

**涉及文件**：`server.py`、`app.js`、`tests/test_server.py`、`tests/test_frontend_modules.py`、`tests/test_p2_coverage.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-26 22:39 · Codex

### 侧栏置顶与添加文件夹图标统一

- 会话和项目的黄色星形置顶标记统一替换为 12px 中性色线性图钉，继续复用原有置顶状态、提示文案和中英文即时切换逻辑。
- “编辑项目”窗口的“添加文件夹”图标重绘为标准文件夹轮廓与内置加号，保持原有按钮尺寸和交互区域不变。
- 新增前端源码回归守卫，防止星形字符回退，并固定两类图标的共享渲染和标准路径。
- 验证：
  - `node --check app.js` 通过；
  - `python -m pytest tests/test_frontend_modules.py tests/test_p2_coverage.py -q`：**146 passed, 4 subtests passed**；
  - `python -m unittest discover -s tests`：**762 tests passed**；
  - 浏览器实际检查了会话/项目置顶及项目编辑窗口，无控制台错误；用户已确认视觉效果。

**涉及文件**：`app.js`、`index.html`、`styles.css`、`tests/test_frontend_modules.py`

---

## 2026-07-26 22:19 · Codex

### Codex 风格项目/会话闭环（第二阶段，开发版本基线仍为 v0.5.28）

- 左侧栏完成 `Project → Session` 收口：每个项目默认显示 3 条最近会话，置顶会话优先且当前会话始终可见；支持“显示全部/收起”，移除项目内会话数量和旧来源二级分组，Codex / Claude Code 只保留来源徽标。
- 项目菜单统一为“编辑项目、置顶/取消置顶”；编辑窗口支持重命名、删除项目和管理多个有序源文件夹。“无项目会话”用于表达未设定项目归属、目录随文件树变化的会话。
- 项目磁盘协议从单一 `path` 升级为 `id / label / rootPaths`；`rootPaths[0]` 是主文件夹，API 暂时保留 `path / rootPath` 作为主文件夹兼容别名。新增一次性迁移 `_migrate_project_root_paths()` 和忽略标记 `data/.codex_project_roots_migrated`。
- 项目编辑支持添加文件夹、设为主文件夹和移除文件夹：
  - 调整主文件夹顺序不会改变仍位于已挂载源文件夹中的既有会话；
  - 删除某个源文件夹时，仅将 `cwd` 位于被删除目录的会话迁移到新主文件夹；
  - 新会话默认从主文件夹开始，删除项目只解除会话归属，不删除磁盘文件。
- 会话、文件树与运行目录形成闭环：加载会话会切换文件树到该会话 `cwd`；在同一项目的挂载目录间切换时保持项目归属，切到项目外目录时会话自动转为未归属。
- AgentRun 持久化协议升级为 v2，在创建时固定 `cwd / workspaceRoots`；读写、编辑、命令、记忆和 Child Agent 均使用运行级目录上下文，不再依赖可被其他会话切换的全局 `projectRoot`，避免并行/后台任务串目录。
- 项目指令上下文按项目主文件夹独立加载并缓存，新增 `AGENTS.md` 识别；主 Agent、后台 Agent 和恢复任务使用各自项目上下文。
- 项目编辑窗口和新增交互补齐中英文即时切换及响应式布局。
- 验证：
  - `python -m unittest discover -s tests`：**760 tests passed**；
  - `python -m pytest tests/test_frontend_modules.py tests/test_p2_coverage.py -q`：**144 passed, 4 subtests passed**；
  - 浏览器真实交互验证了主文件夹重排、删除目录后的定向会话迁移、项目删除和中英文切换，无控制台错误；
  - 用户已通过实际 Code 对话确认会话/文件树切换逻辑无误。

**涉及文件**：`.gitignore`、`agent-runtime.js`、`app.js`、`index.html`、`server.py`、`src/core/i18n.js`、`styles.css`、`tests/test_concurrency.py`、`tests/test_frontend_modules.py`、`tests/test_projects.py`

---

## 2026-07-26 · Codex

### Codex 风格项目/会话数据协议（第一阶段，开发版本基线仍为 v0.5.28）

- 项目注册表改为最小字段 `id / label / path`；`name / rootPath` 只作为当前开发界面的临时 API 兼容别名，不再写入磁盘。
- 会话元数据和 `sessions/index.jsonl` 统一使用 `projectId / cwd / source`；`source` 仅记录 `code / codex / claude-code` 来源，不再作为二级分组实体。
- 新建、保存、增量保存和分支会话都会持久化同一份项目上下文；分支继承父会话的 `projectId / cwd / source`。
- 项目与会话工作目录强绑定：归属项目的会话必须使用项目路径；取消归属时保留原 `cwd`，删除项目只解除关联，不删除会话。
- Codex / Claude Code 导入会读取源会话的 `cwd`；目录真实存在时自动复用或创建对应项目，不存在时仍保留 `cwd` 但保持未归属。
- 新增幂等迁移 `_migrate_codex_project_sessions_support()`：
  - 兼容旧 `name / rootPath`、索引 `project` 和会话 `group`；
  - 移除魔法项目 `__unclassified__`；
  - 以索引和磁盘会话文件的并集重建规范索引，避免漏掉未入索引的会话；
  - 使用 `data/.codex_projects_migrated` 防止重复执行。
- 项目 CRUD、会话项目分配以及导入 API 已接入新协议；为避免第一阶段破坏当前未提交界面，响应暂时保留 `name / rootPath / group` 兼容字段。
- 运行时项目数据和迁移标记已加入 `.gitignore`，不会把用户本地项目注册表提交进仓库。
- 测试：新增 12 个项目/会话协议测试，扩充 Codex / Claude Code 导入断言；全量 **745 passed, 226 subtests passed**。
- 本阶段未提交 Claude Code 留下的侧栏两级分组界面实验；下一阶段按“项目 → 有限数量会话”重做，并在人工验证后再提交。

**涉及文件**：`.gitignore`、`server.py`、`tests/test_projects.py`、`tests/test_server.py`

---

## 2026-07-25 · Claude Code

### 会话导入功能（开发中，版本基线仍为 v0.5.28）

- **后端**：`list_importable_sessions(source, query)` 统一扫描 Codex（`~/.codex/sessions/`）和 Claude Code（`~/.claude/projects/*/`）
- **格式转换**：Codex（`response_item` → Code JSONL）、Claude Code（`type:user/assistant` → Code JSONL）
- **API**：`GET/POST /api/import/sessions?source=codex|claude-code&q=`
- **前端**：工具栏导入按钮 → 弹窗 → 来源标签（显示数量）→ 搜索 → 勾选 → 导入 → 自动刷新
- **分组**：导入的会话自动标记 `group`（Codex/Claude Code），侧栏按分组显示，手风琴折叠
- **优化**：元数据扫描用文件大小估算（200B/行），不逐行解析
- **Bug 修复**：Codex content block 类型兼容（input_text/output_text/text）、model 名从 turn_context 提取、batch 更新脚本 f-string `%%` 转义、`get_sessions` 透传 group 字段
- **实测**：61 个 Codex 会话 + 116 个 Claude Code 会话可导入
- **架构研究**：三家公司（Claude Code / Codex / Code）的会话-项目-分组模型对比已存档

**涉及文件**：`server.py`、`app.js`、`index.html`、`styles.css`、`i18n.js`、`tests/`

### 待完成（导入收尾）
- 侧栏分组折叠稳定性
- 导入窗口交互打磨

### 待规划（架构重构）
- 左侧栏会话列表 + 项目/分组架构重构（参考 Claude Code 项目模型 + Codex local-projects）

### Agent 空承诺检测与三分类完成逻辑

- **`_is_empty_promise(content)` 检测**：识别模型只回复承诺文本（"我来检查一下"/"I'll check..."）但未执行操作的模式，支持中英文，200 字上限
- **Agent 主循环三分类**：
  - 情况 1（正常）：实质性内容 → 标记 completed
  - 情况 2（截断）：content 空 + reasoning 非空 → 自动追加"继续"
  - 情况 3（空承诺）：匹配承诺模式 → 自动追加"请直接执行"（连续 2 次 → failed）
- **`_finish_agent_run` 增加 `error_code` 参数**：支持 `upstream_error` / `config_error` / `permission_denied` / `tool_error` / `user_cancelled` / `empty_response` / `internal_error`
- **`error_code` 写入 run dict 和事件**：前端可直接按 code 做差异化展示，不再需要正则猜测
- **情况 2 改为 `waiting_user_input`**：content 空 + reasoning 有 → 暂停并展示 reasoning + "继续"按钮，由用户判断是否继续（而非自动盲目继续）
- **`_submit_agent_input` 支持 `empty_response` 类型**：追加"请继续"消息并恢复 agent 运行
- **前端 `requestServerAgentInput` + `requestEmptyResponseContinue`**：识别 `empty_response` 类型，展示 reasoning 内容 + 继续按钮
- **前端错误分类展示**：`_errorCodeDisplay` 映射表（7 种错误码 → 标签/建议/是否可重试），`_formatAgentError(err)` 替代硬编码 "Request failed:"
- **agent snapshot 新增 `errorCode` 字段**，前端错误对象携带 `errorCode` 属性
- **新增 26 个测试**（`TestEmptyPromiseDetection` 17 + 前端 error_code 9）：覆盖承诺检测、三分类、完整生命周期、错误映射表、格式化输出

**涉及文件**：`server.py`、`app.js`、`tests/test_agent_runtime.py`、`tests/test_frontend_modules.py`

### batch 更新脚本 f-string %% 转义修复 (v0.5.27)

- **根因**：`_build_update_script()` 的 batch 内容写在 f-string 中，但 `%%` 在 f-string 不会被转义为 `%`（只有 `%` 格式化才会），导致 batch 文件中所有变量都是 `%%date%%` 而非 `%date%`，cmd.exe 不会展开任何变量
- **修复**：f-string 中所有 `%%` → `%`（变量展开），`%%%%` → `%%`（for 循环变量）
- **连带修复**：移除 `!pid!` 延迟展开语法（`setlocal enabledelayedexpansion` 已在 v0.5.23 移除），改用 `%%~p` 直接引用
- **验证**：生成 batch 文件确认变量正确展开，全量测试 676 passed

**涉及文件**：`server.py`、`CHANGELOG.md`

### 发版脚本代理支持 (v0.5.25)

- **自动检测 Windows 系统代理**：`detect_windows_proxy()` 从注册表读取 `ProxyServer`，自动获取 GoGoJump 代理地址（`127.0.0.1:18081`）
- **`--proxy` / `--no-proxy` 参数**：可显式指定或跳过代理
- **所有子进程自动走代理**：`run()` 注入 `HTTPS_PROXY` / `http_proxy` 环境变量，覆盖 git 和 gh CLI
- **连通性验证**：git fetch、gh auth status、git ls-remote 三种方式确认代理连通
- **`--dry-run` 全流程验证通过**：Phase 1~7 预演模式全部通过
- **v0.5.25 正式发版成功**：通过代理（127.0.0.1:18081）完成完整发版流程，676 tests 全绿
- **代理不影响本地测试**：`NO_PROXY=localhost,127.0.0.1` 确保 pytest 不绕代理

**涉及文件**：`release.py`

### EXE 安装与更新链路修复 (v0.5.25)

- **batch 更新脚本进程名过滤修复**：`tasklist /fi "IMAGENAME eq Code.exe"` 改为 `tasklist /fo csv /nh | findstr /i Code-`，使其能正确匹配 `Code-v0.5.24.exe` 等版本化进程名。旧过滤器在 EXE 改为版本化命名后永远匹配不到旧进程。
- **快捷方式创建失败日志**：`create_desktop_shortcut()` 失败时写入 `.code\install.log`（含时间戳和错误详情），不再静默失败。`ensure_installed()` 在首次安装时检查返回值并在控制台提示。
- **新增测试**：4 个 launcher 安装链路测试（`TestLauncherInstall`），覆盖 `get_code_home`、`ensure_installed` 开发模式、快捷方式 PS 脚本内容、失败日志。

**涉及文件**：`server.py`、`launcher.py`、`tests/test_server.py`

## 项目记忆与记录规范

---

## 2026-07-24 · workbar 渠道上线、更新重启修复 (v0.5.19 ~ v0.5.23)

- **workbar 渠道配置完成**：BoxYing 主力 + ByteCatCode 补充，共 5 条渠道 9 款模型上线。详见 `模型定价/` 目录
- **渠道类型踩坑**：Claude + tool_choice 时上游 OpenAI → Anthropic 格式转换问题，ByteCatCode 的 Claude 需选 Anthropic 类型。记入 `workbar-channel-type-selection.md`
- **模型分类修复**：`app.js` 新增 XAI 模式匹配 `grok`，grok-4.5 不再归入「其他」
- **文档体系**：新增 `模型定价/GUIDE.md` 运维指南、`新用户自动令牌配置.md`；重命名 `竞品数据` → `模型定价`
- **GENERATE_DEFAULT_TOKEN**：确认环境变量启用新用户自动创建令牌，配合 `QuotaForNewUser` 赠送初始余额
- **更新重启多次修复 (v0.5.19~0.5.23)**：
  - v0.5.19：XAI 分类 + workbar 品牌统一
  - v0.5.20：三层 `.part` 防护（启动/重启/下载），但 PS 脚本本身有 PyInstaller 冲突
  - v0.5.21：重启改回 batch 文件（`cmd /c` 方式），避免 PS `Start-Process` 干扰 PyInstaller 解压
  - v0.5.23：修复 batch 中 `setlocal enabledelayedexpansion` 导致 `%logPath%` 不被展开
  - **待验证**：v0.5.24 端到端更新测试

- 本文件是项目**已完成改动与验证结果**的统一记录；`TODO.md` 是项目**未完成事项、优先级与后续计划**的统一记录。
- Claude Code、Codex 及人工开发者开始任务前都应先阅读这两个文件，避免重复实现或依据过期信息工作。
- 完成功能、修复缺陷、调整架构/协议/UI、发布版本、改变产品决策或完成重要测试后，必须在本文件记录结果；尚未完成或新发现的工作同步写入 `TODO.md`。
- 记录应包含日期、贡献方、改动目的、关键行为和验证结论；必要时补充版本号或相关文件，避免只写“已优化”“已修复”等无法追溯的描述。
- 自 2026-07-15 起，新增日志标题必须包含本地具体时间戳，格式为 `YYYY-MM-DD HH:mm`；此前未记录具体时间的历史内容保持不变。
- 同一天的新增内容追加到对应贡献方区块；新的一天插入到最上方。除纠错外不改写既有历史。
- 如果两份文档、实际代码和测试结果不一致，应在当前任务内核实并同步修正，不能让冲突状态继续保留。

---

## 2026-07-23 · Claude Code

### 2026-07-23 05:23 Code：自动发版脚本与发版指南

- **自动发版脚本 `release.py`**：7 阶段自动化——版本号同步（VERSION / file_version_info.txt / README.md / .spec）→ 一致性校验 → 全量测试 + 语法检查 → PyInstaller 构建 EXE → EXE 元数据校验 + SHA-256 → 生成发布说明 → Git 提交打标签 → 推送 + GitHub Release。任何步骤失败立即停止并给出明确错误信息和补救命令。
- **Agent 友好**：`--yes` / `-y` 参数跳过所有交互确认，供 AI Agent 调用；`--dry-run` 预演模式只检查不改文件；`--skip-tests` 在刚跑过测试时跳过。
- **发版指南 `docs/release-guide.md`**：覆盖人工发版完整流程、AI Agent 使用限制、脚本不可用时的手动 9 步清单、版本号规则、相关文件索引。
- **Agent 文档更新**：`AGENTS.md`、`CLAUDE.md`、`docs/development-handoff.md` 均已加入发版脚本引用和使用规范；交接快照的"建议下一阶段"更新为当前 P1 优先事项。

**涉及文件**：`release.py`、`docs/release-guide.md`、`AGENTS.md`、`CLAUDE.md`、`docs/development-handoff.md`、`CHANGELOG.md`

### 2026-07-23 Code：workbar 品牌名统一为全小写

- **全局品牌小写化**：所有用户可见界面文案、i18n 翻译（中/英）、README、发布说明、文档注释、CSS 注释及 `server.py` 错误消息中的 "Workbar" 统一改为全小写 "workbar"。URL `https://workbar.ai` 本就是小写。
- **保留代码标识符**：i18n key 名（`getFromWorkbar`、`connectWorkbarTitle` 等 camelCase）、常量名（`WORKBAR_URL`）、CSS 类名（`.key-workbar-btn`）、测试类名（`TestWorkbarAuthentication`）保持原样——这些是代码标识符，非品牌展示。
- **协作规则固化**：`AGENTS.md`、`CLAUDE.md`、`new-api-source/AGENTS.md` 新增「品牌与命名约定」章节，要求新增或修改任何包含平台品牌名的内容前检查全小写。
- **验证**：前端模块 58 项 + 服务端认证 7 项 + 2 subtests 通过。

**涉及文件**：`src/core/i18n.js`、`src/features/settings.js`、`index.html`、`README.md`、`server.py`、`app.js`、`styles.css`、`docs/releases/v0.5.6.md`、`docs/development-handoff.md`、`docs/agent-refactoring-execution-plan.md`、`AGENTS.md`、`CLAUDE.md`、`tests/test_frontend_modules.py`、`tests/test_server.py`、`CHANGELOG.md`、`TODO.md`

## 2026-07-23 · Codex

### 2026-07-23 04:35 Code：Skill 依赖设置页操作闭环（隔离运行时）

- **隔离运行时闭环**：完成 `/api/skills/dependencies` 下安装、修复、卸载、进度、失败恢复与“重新检查”链路的服务端状态机；安装/修复仅在 `data/runtime` 隔离环境内执行 `pip` 与 `npm`，支持中断、超时、输出脱敏与失败原因透传，并支持重试。
- **系统依赖边界强化**：系统级依赖检测改为只读 `installHint` 与标准路径搜索，不再触发系统包管理器、PATH 修改或全局包装器创建。
- **一键与可选依赖操作**：新增“安装缺少的必需依赖”入口（按 Skill 聚合一次安装），并保留可选依赖手动安装入口；缺失项状态按必需/可选分层展示。
- **卸载与安全隔离**：提供“移除依赖/卸载”入口并限制作用域于托管运行时；Python 卸载支持半安装恢复，Node 卸载仅清理托管环境中的安装目录与可执行入口，不影响系统全局与共享依赖。
- **前端体验收口**：添加操作卡片、进度回显、失败后可重试、取消、清空通知、重新检查后刷新状态；中英文即时切换不退化，系统级黄色提示保留。
- **验收与测试**：前端与后端回归继续补齐到 672 项、226 个 subtests 通过；`node --check` 覆盖关键前端模块；`git diff --check` 通过；用户完成手工验收后确认安装恢复、重装重检、可选依赖标注与执行入口行为符合预期。

**涉及文件**：`skill_dependencies.py`、`server.py`、`src/core/i18n.js`、`src/features/skills-memory.js`、`styles.css`、`tests/test_frontend_modules.py`、`tests/test_p2_coverage.py`、`tests/test_routes.py`、`tests/test_server.py`、`tests/test_skill_dependencies.py`、`.gitignore`

### 2026-07-23 02:02 Code：建立跨任务开发交接快照

- **最小接手上下文**：新增 `docs/development-handoff.md`，集中导航当前 Git 基线、近期稳定能力、Skills 依赖管理的推荐下一阶段、后续 Agent 路线、验证/提交规则及环境安全注意事项；明确 `CHANGELOG.md` 与 `TODO.md` 仍是唯一事实源，交接快照必须与现场 Git 状态复核。
- **协作入口统一**：`AGENTS.md` 与 `CLAUDE.md` 增加交接快照入口，新任务可先快速定位，再回到事实源和实际代码确认，避免依赖超长历史会话或复制多个相互冲突的项目状态。
- **可复制启动消息**：交接文档内附新任务启动提示词，明确保护未跟踪的 `package.json` / `package-lock.json`，并延续“一阶段一验证一提交”的协作模式。
- **验证**：相对文档目标存在性检查与 `git diff --check` 通过；本阶段只修改 Markdown 文档，不涉及运行时代码。

**涉及文件**：`docs/development-handoff.md`、`AGENTS.md`、`CLAUDE.md`、`CHANGELOG.md`

### 2026-07-23 01:47 Code：Skill 依赖协作闭环与模型选择启动恢复

- **依赖发现与能力级预检**：扩展 `dependencies.json` 清单和设置页编辑、状态展示能力，并可从 `requirements`、`pyproject.toml`、`package.json`、Python/JavaScript/TypeScript 导入及 `SKILL.md` 中的明确安装命令自动识别候选依赖；多能力 Skill 必须指定能力后才进入安装流程，避免一次安装无关依赖。
- **首次使用协作安装**：Skill 首次使用时按能力检查依赖；Python 与 Node 依赖仅可在 Code 管理的隔离运行时内、经用户授权后安装。系统级依赖改为提供可读的 `installHint` 并与用户协作完成，不由模型直接执行系统包管理器。
- **安装安全边界**：阻止 `winget`、`choco`、`apt` 等系统安装命令、项目内包装安装脚本、全局包装器和 PATH 修改；增加相同安装命令重复执行上限、超时上限及安装提示返回，降低模型陷入依赖修复循环或污染用户环境的风险。
- **DOCX 依赖口径**：为 Pandoc、LibreOffice、Poppler 补充明确的 Windows 安装提示；`/docx` 可按创建、读取、渲染等能力分别报告就绪状态，不再把可选能力缺失误判为整个 Skill 不可用。
- **模型选择恢复**：应用初始化在静默同步前恢复上次选择的模型；模型列表成功加载后继续沿用可用选择，仅在该模型确认不可用时回退到未选择。网络失败或空列表不会误删本地选择。
- **验证**：Python、JavaScript 语法检查和 `git diff --check` 通过；定向回归 274 项、29 个 subtests，通过；排除独立运行式 Skills 路由脚本后的主测试集 640 项、42 个 subtests，通过；内置 Skills 13 项、181 个 subtests，通过；18 项路由检查零失败。用户重启 Code 后确认模型选择恢复与回退行为正常。

**涉及文件**：`app.js`、`server.py`、`skill_dependencies.py`、`index.html`、`styles.css`、`src/core/i18n.js`、`src/features/skills-memory.js`、`data/skills/docx/dependencies.json`、`tests/test_agent_runtime.py`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`tests/test_p2_coverage.py`、`tests/test_routes.py`、`tests/test_server.py`、`tests/test_skill_dependencies.py`、`tests/test_subagent_frontend.py`、`CHANGELOG.md`、`TODO.md`

## 2026-07-22 · Codex

### 2026-07-22 21:11 Code：设置页实时语言刷新与 workbar 账号文案收口

- **当前面板即时刷新**：语言切换不再依赖离开设置页再返回；模型、Memory、Skills、主题、系统提示词、账户和更新面板均会就地刷新固定文案，同时保留 Key 草稿、Memory 编辑内容、当前 Skill、主题选择、更新状态与账户加载状态。
- **动态内容统一 i18n**：补齐 Key 编辑器、模型空状态、更新操作、账户统计、Memory 表单与 Skill 依赖状态等动态节点的中英文标记；Skills 语言刷新复用已缓存的依赖预检结果，不重复扫描本机环境。
- **账户视觉与命名修复**：修正连接状态圆点样式误作用到整段文字导致“已连接”竖排的问题；设置侧栏和右侧面板统一命名为“workbar 账号 / workbar Account”。
- **验证**：相关 JavaScript 语法检查、`git diff --check`、前端与 P2 定向回归 102 项、4 个 subtests 通过；排除独立运行式 Skills 路由脚本后的完整回归 630 项、211 个 subtests 通过。浏览器检查设置页中英文即时切换与草稿/选择状态保持，用户反馈账户连接文字排版恢复正常并确认继续后续阶段。

**涉及文件**：`app.js`、`index.html`、`src/core/i18n.js`、`src/features/settings.js`、`src/features/skills-memory.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`

### 2026-07-22 20:14 Code：Skill 依赖管理阶段 2——设置页状态可视化

- **按需检查与缓存**：Skills 设置页在首次打开时才请求依赖预检，不增加应用启动负担；结果在当前页面生命周期内复用，并提供“重新检查”按钮显式刷新本机状态。
- **分层状态展示**：设置页顶部汇总已声明、可用、部分可用和不可用数量；左侧 Skill 列表以绿、黄、红状态点快速提示，详情页按能力展示可用性、必需/可选依赖、已检测版本和缺失项，不提供安装入口，也不会在检查时修改本机环境。
- **环境口径明确**：状态以实际运行中的 Code 进程为准。开发终端可从 Codex 附带 PATH 发现 `pdftoppm`，而重启后的 Code 进程未发现该命令，因此真实界面显示 10 个声明中 4 个可用、4 个部分可用、2 个不可用；该差异将由后续隔离运行时收口。
- **国际化与验证**：能力名称、状态、摘要、错误及操作完成中英文覆盖；JavaScript 语法检查与 `git diff --check` 通过，依赖接口、内置清单、路由和前端定向回归 133 项、190 个 subtests 通过。用户重启 Code 后完成人工验收，确认红、黄状态点显示正常。

**涉及文件**：`src/features/skills-memory.js`、`src/core/i18n.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 19:57 Code：Skill 依赖管理阶段 1——声明与只读预检

- **机器可读依赖契约**：新增版本化 `dependencies.json` 格式，以能力为单位声明必需/可选的 Python 包、Node 包和系统命令；首批覆盖 `docx`、`pptx`、`xlsx`、`pdf`、`mcp-builder`、`office-files`、`document-design`、`image-generation`、`hyperframes` 与 `web-artifacts-builder` 10 个内置 Skill。
- **隔离优先的环境探测**：新增独立 `skill_dependencies.py`，只读检查 `data/runtime` 托管目录、应用目录和系统环境，识别安装状态、版本、来源、可用能力与可选依赖缺口，不在启动或预检过程中执行安装。Node 依赖优先采用未来的托管运行时，Python 包通过外部解释器批量探测，避免把 PyInstaller 内部模块误判为 Agent 可调用环境。
- **状态接口与升级兼容**：新增 `GET /api/skills/dependencies`，汇总 Skill 的 `ready / partial / unavailable` 状态；持久化 Skill 缺少新清单时自动读取当前版本随程序附带的同名清单，因此升级不会覆盖用户已有 Skill 内容，也能获得最新依赖定义。
- **验证**：Python 语法检查和 `git diff --check` 通过；清单校验、托管 Node 优先级、版本检查、旧 Skill 回退、错误隔离、内置 Skill 和真实 HTTP 路由定向回归 125 项、194 个 subtests 通过；排除独立运行式 Skills 路由脚本后的完整回归 634 项、211 个 subtests 通过。

**涉及文件**：`skill_dependencies.py`、`server.py`、`data/skills/*/dependencies.json`、`tests/test_skill_dependencies.py`、`tests/test_builtin_skills.py`、`tests/test_routes.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 19:33 Code：Markdown 解析管线收口

- **单一解析管线**：Markdown 源文本先保护代码区域并投影数学公式，再仅交由 Marked 解析一次，最后恢复可信的 KaTeX 结果；移除解析完成后针对整段 HTML 的多轮正则改写，避免规则叠加造成内容增删或结构错乱。
- **语义边界明确**：行内路径、链接和图片分别交由 Marked renderer 处理；本地图片继续安全映射到 `/api/file`，外部链接保留新窗口与隔离属性。合法的 Setext 标题和水平分隔线不再被全局转义。
- **原文精确保留**：任意长度的反引号/波浪线围栏与行内反引号区域会在数学解析前隔离，代码中的 `$HOME`、`$5` 等内容保持原样；无法渲染的数学表达式恢复原始定界符，不再吞掉或改写用户文本。
- **验证**：`node --check`、`git diff --check` 通过；Markdown 与前端稳定性定向回归 75 项通过；排除独立运行式 Skills 路由脚本后的完整回归 626 项、208 个 subtests 通过。浏览器复核既有 Markdown、数学公式会话正常，用户对包含 Setext 标题、分隔线、路径、PowerShell 变量和行内/块级公式的精确样例完成人工验收。

**涉及文件**：`src/ui/markdown.js`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 19:16 Code：流式首帧内容与布局稳定性

- **未分类首帧隔离**：流式助手消息在尚未判定为思考摘要或最终答案时不再提前写入可见区域；增加 `180ms` 首帧判定窗口，确认属于答案后继续正常增量更新，工具轮则直接进入思考摘要投影，避免大段内容短暂出现后被替换。
- **居中锚点稳定**：消息列表改为真实的全宽布局容器；运行状态节点必须先挂载到会话区居中锚点后才允许显示，临时停放态由 CSS 强制隐藏，消除首帧从左侧跳到中间的问题。
- **验证**：前端模块定向回归 54 项通过，相关 JavaScript 语法检查和 `git diff --check` 通过；浏览器确认稳定消息保持 `760px` 居中布局。用户完成人工流式验收，确认首帧不再横向闪现；接受约 `180ms` 的首帧判定延迟。

**涉及文件**：`app.js`、`src/ui/messages.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 18:57 Code：运行中追加消息路由

- **默认 FIFO 排队**：主任务运行期间发送的普通消息不再自动转成后台任务，而是按提交顺序进入当前会话的持久化队列；消息在真正执行时复用标准主 AgentRun，并继承前一轮最终结果作为上下文。
- **显式并行入口**：新增 `/parallel <任务>` 命令，仅在用户明确要求时复用既有后台 AgentRun 调度器；补全中英文命令说明、斜杠建议和运行中发送按钮状态。
- **配置快照与可靠恢复**：排队时固定模型、权限模式、工具预设、思考强度、温度和最大输出，并为每项生成稳定 `clientRequestId`；队列与会话 `runState` 一同持久化，刷新后先恢复前台任务再继续队列，避免重复请求和上下文错序。
- **取消语义与复活修复**：待执行消息可独立取消且不影响主任务或后台任务；取消后从执行队列移除、保留灰色“已取消”记录并永久排除模型上下文。同步更新活动运行持有的旧消息数组，修复主任务完成时把已取消消息重新写回的问题。
- **顺序与边界收口**：排队消息固定显示在当前输出之后并保持 FIFO；本地 `/export`、`/clear`、`/branch` 命令仍优先在前端处理；单项失败后继续后续队列，启动时暂缺可用 Key 则保持待处理而不误判失败。
- **验证**：JavaScript 语法检查与 `git diff --check` 通过；队列、持久化、消息投影和 P0 稳定性定向回归 86 项通过；排除独立 Skills 路由脚本后的完整回归 621 项、208 个 subtests 通过。用户完成人工验收，确认普通排队、显式并行、取消、刷新恢复及取消消息不复活均正常。

**涉及文件**：`app.js`、`src/core/i18n.js`、`src/features/skills-memory.js`、`src/ui/messages.js`、`styles.css`、`tests/test_message_queue.py`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 09:52 Code：Agent 架构文档与路线基线更新

- **实现基线校准**：将 Agent 设计分析和执行方案统一升级到 Code v0.5.6，明确区分服务端主 AgentRun、模型显式 `task` Child AgentRun 与用户运行期追加消息三个通道；删除“尚无并发”等已失效判断，不再重复规划已完成的服务端执行、恢复、授权代理和并发底座。
- **后续路线收敛**：下一阶段确定为“普通追加消息默认排队、明确操作显式并行”，随后建立服务端白名单生成的 `Context Envelope`，再实现带依赖、预算和验证证据的结构化计划；Cron、Monitor、Workflow 与 worktree 隔离后置评估。
- **设计边界明确**：继续使用 `read / plan / accept / bypass` 四种权限策略，不新增重叠的 `collaboration_mode`；不使用关键词正则猜测并行意图，不默认复制完整会话，不向子任务传递 Key、授权 Token 或隐藏推理。
- **TODO 清理**：移除已完成项和过期的“上线前”描述，按 workbar 上线后收口、Code 核心能力、规划与自动化重新整理未完成工作；补充企业邮箱、登录融合新手指引、运行期消息路由和委托上下文契约。
- **验证**：三份文档 UTF-8、关键章节与相对链接检查通过，`TODO.md` 不再包含已完成勾选、旧品牌名或过期阶段标题；`git diff --check` 通过。

**涉及文件**：`docs/agent-refactoring-execution-plan.md`、`docs/codex-claude-code-agent-design-analysis.md`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 09:34 Code：v0.5.6 发布准备

- **版本与文档**：统一将 `VERSION`、Windows 文件元数据和 README 升级到 `0.5.6`；更新 Windows 快速开始流程和测试徽章，新增 `docs/releases/v0.5.6.md`，完整说明 workbar 登录、Key 生命周期、设置页重构、稳定性改进和升级注意事项。
- **发行构建**：使用 Python `3.12.10` 与 PyInstaller `6.21.0` 生成 Windows x64 单文件 `Code-v0.5.6.exe`；内置 `VERSION`、文件名、FileVersion、ProductVersion、OriginalFilename 及关键前端资源核验一致。
- **产物校验**：EXE 大小 `31,042,747 bytes`（`29.60 MiB`），SHA-256 为 `9A02E73E82079D1FF9C424E0E5D631407B2D1881102F5B3C5271346C1EBFBD47`，签名状态 `NotSigned`。
- **GitHub 发布**：`v0.5.6` 标签与正式 Release 已发布为仓库最新版，Windows x64 资产上传完成；GitHub 远端摘要与本地 SHA-256 完全一致。发布地址：<https://github.com/fhy-A/Code/releases/tag/v0.5.6>。
- **验证**：发布核心 JavaScript/Python 语法检查通过；定向回归 254 项、6 个 subtests 通过；发布前完整回归沿用本阶段最新结果 614 项、208 个 subtests 通过。

**涉及文件**：`VERSION`、`file_version_info.txt`、`README.md`、`docs/releases/v0.5.6.md`、`CHANGELOG.md`

### 2026-07-22 09:23 Code：登录入口与旧版新手指引收口

- **登录台文案排版**：将 workbar 登录说明拆成稳定的两行结构，明确把“并同步 API Key。”完整放在第二行，并同步中英文文案，避免不同窗口宽度下只剩 `Key` 单独换行。
- **移除旧版指引**：删除旧新手指引的启动判断、弹窗 DOM、样式、i18n 文案和设置模块接口；启动时清理 `code-onboarding` 与 `agent-lite-onboarding` 历史标记，不再让过时流程与强制 workbar 登录门禁竞争。
- **后续计划**：`TODO.md` 新增登录后一体化新手指引，计划在授权成功后结合项目选择、模型与 Key 状态、权限模式和首次任务重新设计；同时补全企业邮箱替换个人邮箱事项。
- **验证**：JavaScript 语法检查及 `git diff --check` 通过；前端定向回归 100 项、4 个 subtests 通过；排除独立 Skills 路由脚本后的完整回归 614 项、208 个 subtests 通过。浏览器确认旧指引 DOM 已完全移除，用户完成启动界面人工验收。

**涉及文件**：`app.js`、`index.html`、`src/core/i18n.js`、`src/features/settings.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 08:58 Code：设置页完善与 Key 生命周期收口阶段 4

- **轻量设置页收口**：语言切换从独立页面下沉到设置侧栏底部并实时刷新当前面板；账户页改为身份、额度/用量统计和账户详情分层展示，按需从 workbar 获取经过白名单过滤的用户名、邮箱、分组、额度、已用额度与请求次数；更新页统一为紧凑状态卡片和明确操作区。
- **Key 删除与同步边界**：以非敏感的 workbar 用户 ID 和 Token ID 记录账号内已移除项，静默同步不再自动加回用户主动删除的 workbar Key；其他渠道手动 Key 保持独立，不按名称或内容误判来源。跨标签页 Key 变化会即时刷新设置编辑器，旧隐藏输入框不再参与运行时 Key 读取。
- **旧 Key 复活根因修复**：确认品牌改名迁移会在每次启动时将残留的 `agent-lite-key` / `agent-lite-key-config` 重新复制并写回 `code-key-config`。敏感 Key 改为真正的一次性迁移，结构化配置即使为空也视为有效删除状态；保存、清空、退出和启动都会删除旧敏感存储，通用品牌迁移不再处理 Key 与旧平台授权。
- **安全与兼容**：`code-key-config` 成为模型请求、恢复任务和设置页的唯一 Key 数据源；退出登录同步清理结构化 Key、旧文本 Key、模型映射和旧版授权。账户接口只返回前端实际展示字段，workbar 公共计价设置不可用时不影响授权验证。
- **验证**：JavaScript 语法检查及 `git diff --check` 通过；i18n、设置页、Key 迁移和账户接口定向回归共 252 项、6 个 subtests 通过；排除独立路由脚本后的完整回归 612 项、208 个 subtests 通过。用户完成真实退出、重新登录和重启 Code 验收，确认已删除的旧 Key 不再恢复。

**涉及文件**：`app.js`、`index.html`、`server.py`、`src/core/i18n.js`、`src/core/platform.js`、`src/features/settings.js`、`styles.css`、`tests/test_frontend_modules.py`、`tests/test_server.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 06:58 Code：设置页交互优化阶段 3

- **模式与方案分层**：主题页顶部统一为浅色、深色、跟随系统三段式模式开关；浅色和深色模式仅展示各自方案，避免两套主题同时堆叠造成选择混乱。
- **系统双方案预设**：跟随系统模式同时展示完整的 15 个浅色和 26 个深色方案，各自保留一个选中项；选择任一方案只更新对应预设，继续保持系统模式，由系统明暗状态决定实际生效主题。
- **主题卡片优化**：主题方案改为带色板、名称、选中描边和勾选状态的紧凑卡片；模式、方案名称和数量完成中英文收口，并移除重复的系统状态提示文字。
- **验证**：`tests/test_frontend_modules.py` 与 `tests/test_p2_coverage.py` 共 92 项、4 个 subtests 通过，相关 JavaScript 语法检查和 `git diff --check` 通过；浏览器验证浅色 15 项、深色 26 项、跟随系统双组共 41 项及系统模式保持行为，1366×768 布局正常，用户人工验收通过。

**涉及文件**：`src/features/settings.js`、`src/core/i18n.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 06:41 Code：设置页交互优化阶段 2

- **模型刷新收口**：进入或切回模型面板时不再无条件请求模型列表；面板直接展示已有快照，仅在用户点击刷新按钮、Key 静默同步完成或其他既有明确刷新节点执行检测。
- **Skills 选择稳定性**：设置页记住当前 Skill，启停导致列表重排后仍保持该项选中和详情同步；保存、重命名或删除时同步更新选择，并增加异步详情竞态保护。
- **记忆加载反馈**：移除面板打开后的 100ms 延迟空白，立即显示加载状态；请求失败后展示可读错误和重试按钮，并忽略已切换面板或已被新请求取代的过期结果。
- **验证**：`tests/test_frontend_modules.py` 与 `tests/test_p2_coverage.py` 共 91 项、4 个 subtests 通过，相关 JavaScript 语法检查和 `git diff --check` 通过；浏览器验证模型面板不自动进入刷新态、非首项 Skill 启停前后保持选中、记忆列表稳定加载，用户人工验收正常。

**涉及文件**：`src/features/settings.js`、`src/features/skills-memory.js`、`src/core/i18n.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 06:27 Code：设置页布局优化阶段 1

- **导航信息架构**：统一设置页左侧导航按 `Agent`、`外观`、`应用` 三组组织，使用标题与分隔线建立层级，保留原有面板切换和更新提示逻辑。
- **窗口自适应**：设置卡片宽高改为随桌面视口收缩；标题和关闭按钮固定，仅左侧导航与右侧内容区独立滚动，解决 1366×768 下整个设置窗口滚动、标题栏移出视野的问题。
- **中英文收口**：三个导航分组标题接入统一 i18n，中文与英文切换后立即生效。
- **验证**：`tests/test_frontend_modules.py` 与 `tests/test_p2_coverage.py` 共 90 项、4 个 subtests 通过，Node 语法检查和 `git diff --check` 通过；在 1366×768 与 1879×1272 视口完成浏览器布局检查，用户人工验收导航分组和滚动体验正常。

**涉及文件**：`index.html`、`src/core/i18n.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 06:05 Code：workbar 登录与 Key 同步重构阶段 4

- **交互式 Key 获取**：模型设置面板新增低干扰的“从 workbar 获取”入口；每次打开窗口都会实时拉取账号下的 Key，以脱敏预览列出名称和状态，完整值仅在用户点击单项复制或复制全部时写入剪贴板，不进入页面 HTML。
- **精确去重与禁用保护**：使用规范化后的完整 Key 与本地结构化配置即时比对并标记“已添加”；禁用 Key 仍可见并明确标记“已禁用”，但不提供单项复制且不会进入“复制全部”，避免粘贴后被误设为启用。静默同步继续保留禁用状态更新能力。
- **Key 与模型设置优化**：API Key 改为紧凑卡片布局，统一显示、启停和删除控件的对齐，保留拖拽排序及原有存储逻辑；模型区域增加数量、提供独立的真实刷新状态和供应商分组层次，并补充空状态。
- **文案与状态提示**：同步入口、弹窗标题、刷新状态及禁用统计均完成中英文收口；底部完成提示改为“已启用的 API Key 均已在本地列表中”，避免把禁用项计入“所有 Key”。
- **验证**：前端模块定向测试 42 项通过；完整回归 596 项、208 个 subtests 通过（排除 1 个独立脚本和 1 个既有 Windows 文件锁用例）；`git diff --check` 通过。用户完成真实 workbar Key 列表、禁用项、复制行为和设置面板视觉验收，结果正常。

**涉及文件**：`src/core/platform.js`、`src/core/i18n.js`、`src/features/settings.js`、`styles.css`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 05:01 Code：workbar 登录与 Key 同步重构阶段 3

- **非阻塞静默同步**：授权有效后立即在后台同步 workbar Key，并与项目配置、会话恢复并行进行；同步完成后只刷新一次模型列表，不弹窗、不显示 Toast、不阻断正常启动视图。
- **非破坏性 Key 合并**：`source: "manual"` 的手动 Key 在任何平台同步中都不修改、不删除；仅更新已有的 `source: "platform"` 名称和启停状态，新 Key 增量加入。平台返回空列表或网络异常时不清空本地配置。
- **完整 Key 规范化**：`/api/code/sync-keys` 强制访问 `https://workbar.ai`，分页获取全部 Key、每 100 条分批查询完整值，过滤遮罩值，并对完整后缀只补一次 `sk-`；移除了包含授权状态的调试日志。
- **刷新无闪烁验证**：OAuth 首次回调仍显式验证账号；普通启动/刷新不再重复调用 `/auth/validate` 或展示验证页，由后台 Key 同步同时校验缓存授权；401 会恢复过期门禁，网络故障则保留授权和本地 Key。
- **开发期托盘重启**：托盘菜单新增 `Restart Code`；隐藏等待器会等当前 PID 完全退出后才启动同一份源码或 EXE，打包版复用当前浏览器页面；旧服务无法关闭时会取消等待器，避免之后意外自启。
- **验证**：同步、鉴权、Key 合并、分页/分批、启动顺序和托盘重启均有自动化覆盖；最终回归在排除 1 个既有 Windows 同会话并发写入偶发文件锁用例后，594 项、208 个 subtests 通过，托盘重启定向 4 项通过。用户完成真实 workbar 静默同步、刷新体验和托盘重启验收，结果正常。

**涉及文件**：`server.py`、`src/core/platform.js`、`src/features/settings.js`、`app.js`、`tests/test_server.py`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 04:35 Code：workbar 登录与 Key 同步重构阶段 2

- **强制登录门禁**：未保存平台授权时不再继续加载会话、项目上下文或模型功能，改为展示不可关闭的“连接到 workbar”引导页；授权过期与平台暂时不可用使用不同提示和恢复动作。
- **启动授权验证**：新增本地 `POST /api/code/auth/validate`，由 Code 服务端使用固定 workbar 地址调用 `/api/user/self` 验证 access token 与 User ID，前端启动时自动验证并刷新真实用户名；网络故障不会误删仍可能有效的授权。
- **OAuth 回调收口**：回调参数保存后立即清理地址栏，再通过服务端完成有效性确认；跨标签页完成授权时，原 Code 页面通过 storage 事件自动刷新。
- **退出清理**：退出登录会同步清除平台授权、全部结构化 Key、旧 Key 文本、模型映射、模型列表和已选模型，并立即恢复登录门禁。
- **验证**：授权有效、授权过期、账号不匹配、workbar 不可用和固定请求地址均有自动化覆盖；定向回归 184 项、2 个 subtests 通过，Node/Python 语法检查与 `git diff --check` 通过。用户完成真实 workbar 登录门禁与回调链路验收，结果正常。

**涉及文件**：`server.py`、`src/features/settings.js`、`src/core/i18n.js`、`app.js`、`styles.css`、`tests/test_server.py`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### 2026-07-22 04:26 Code：workbar 登录与 Key 同步重构阶段 1

- **固定服务地址**：新增 `src/core/platform.js` 作为 workbar 集成的统一配置与 Key 数据契约；模型 Base URL 和平台登录地址固定为 `https://workbar.ai`，启动时清理旧的 `code-base-url`、`code-platform-url` 自定义值。
- **移除地址配置 UI**：模型设置和账户面板不再展示 Base URL 或中转站地址输入框；旧设置弹窗仅保留隐藏的固定地址节点，以兼容现有请求链路。
- **结构化 Key 配置**：`code-key-config` 成为 Key 配置主数据源，条目统一包含 `name`、`key`、`enabled`、`source`；旧条目自动迁移为 `source: "manual"`，平台来源可保留为 `source: "platform"`。
- **输入格式兼容**：Key 解析统一支持 `名称: sk-xxx`、`名称 sk-xxx` 和纯 `sk-xxx`，并保持去重、启停状态和来源信息。
- **验证**：`tests/test_frontend_modules.py` 37 项通过；排除会在 pytest 收集期主动 `sys.exit` 的独立路由脚本后，全量回归 582 项、206 个 subtests 通过；Node 语法检查与 `git diff --check` 通过。用户完成前端验收，确认模型/账户面板地址字段已隐藏且原有功能正常。

**涉及文件**：`src/core/platform.js`、`src/features/settings.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

---

## 2026-07-21 · Claude Code

### code：Skill 移植（续）+ 斜杠命令系统 + 键盘快捷键 + bug 修复

- **斜杠命令系统**：新增 3 个前端直连 UI 命令 `/export`（导出对话）、`/clear`（清空会话）、`/branch`（创建分支），由 `handleUiSlashCommand()` 拦截直接执行不走模型。`/compact`（手动压缩上下文）保留为 skill。命令建议列表支持 ↑↓ 键盘导航、Enter 选中、默认高亮第一项。支持 `/command 参数文本` 格式。
- **键盘快捷键**：`Ctrl+K` 聚焦输入框、`Ctrl+L` 清空会话、`Ctrl+/` 打开命令列表、`Esc` 暂停流式/失焦。
- **中优先级 Skill 移植**：新增 `theme-factory`、`mcp-builder`、`algorithmic-art`、`doc-coauthoring`，Skill 总数 17 → 28。
- **mcp-builder 脚本适配**：`evaluation.py` 改为走 Code API（`requests` + `/v1/chat/completions`），不再依赖 Anthropic SDK。
- **关键词调优**：修复 4 个 skill 的误配/漏配问题（pptx/doc-coauthoring/web-artifacts-builder/theme-factory）。
- **Markdown 渲染修复**：`=====` 和 `-----` 行不再被 `marked` 误解析为 setext heading 导致文字变大加粗。
- **编辑卡片状态修复**：server-managed 编辑在自动模式下批准执行后直接显示"已应用"，不再卡在"等待批准"。
- **待办更新**：子 Agent 缺乏上下文判断、流式思考块闪现左侧、会话错误恢复等已知问题。

**涉及文件**：`app.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`src/features/skills-memory.js`、`src/ui/diff.js`、`src/ui/markdown.js`、`data/skills/`（4 个新增 + 4 个修正 + 3 个移除）、`tests/test_new_skills_routing.py`、`CHANGELOG.md`、`TODO.md`

### code：文件写入 UI 修复 + i18n 收口 + 安装教程 + npm 配置

- **write_file 预览修复**：新文件内容不再整篇渲染为格式化 Markdown，改为语法高亮代码块 + 行号（绿色 `+` 标记），超过 40 行自动折叠，展开按钮支持 `.write-file-preview` 选择器。
- **思考块长文本折叠**：超过 500 字的非流式思考总结用 `<details>` 包裹，避免长说明文字撑满思考块。
- **i18n 收口**：`LANG` 从 34 键瘦身到 12 键（移除 22 个被 `I18N` 覆盖的死键）；`I18N` 移除 6 个零引用的 `*Label` 冗余键（`inputLabel`/`outputLabel`/`cacheLabel`/`contextLabel`/`userLabel`/`agentLabel`）。服务端 `srv*` 错误键统一前缀 CamelCase，当前中文→key 映射方案可用但建议后续 server 直返 i18n key。
- **Claude Code 安装教程**：新增 `docs/claude-code-install-guide.md`（面向零基础用户），含作用域 registry 永久配置、PATH 修复、常见错误速查表。
- **npm 作用域 registry 配置**：`~/.npmrc` 新增 `@anthropic-ai:registry = https://registry.npmjs.org/`，Claude Code 自动更新不再受腾讯云镜像影响。
- **测试**：578 passed, 206 subtests passed。

**涉及文件**：`src/ui/diff.js`、`src/ui/messages.js`、`styles.css`、`app.js`、`src/core/i18n.js`、`docs/claude-code-install-guide.md`、`tests/test_frontend_modules.py`、`TODO.md`、`CHANGELOG.md`

### code：会话错误自动恢复

- **错误自动回滚**：`sendMessage` 记录本轮用户消息位置作为健康快照。模型 API 错误时（非 AbortError），自动回退到快照点：恢复原始用户消息、移除失败轮新增的 assistant/tool-call/tool-result、清理残留 `streaming`/`_streamProjection` 标记。
- **恢复提示**：回滚后追加一条 assistant 消息告知用户错误原因，并提示可修改提问重试或使用 `/branch` 创建分支。
- **i18n**：新增 `errorRecoveryHint` 键（中/英）。
- **根因分析**：错误轮的消息被持久化后反复重放 → API 持续返回相同错误。回滚打破了这个循环。
- **测试**：313 passed, 19 subtests passed。

**涉及文件**：`app.js`、`src/core/i18n.js`、`TODO.md`、`CHANGELOG.md`

---

## 2026-07-21 · Claude Code

### code：Skill 移植 + UI 细节优化

- **高优先级 Skill 移植**：从 Claude 官方 skill 移植 7 个——`docx`、`pptx`、`xlsx`、`pdf`（Office 四件套拆开）、`learn`（教学模式）、`consolidate-memory`（记忆整理）、`web-artifacts-builder`（React 组件生成）。均适配 code 的 frontmatter 格式，内容保持一致。Skill 总数从 17 增至 24。
- **路由调优**：`learn` 关键词收紧，避免普通技术问答误触发。
- **测试**：46 passed, 151 subtests passed。

**涉及文件**：`data/skills/` 7 个新 SKILL.md、`tests/test_builtin_skills.py`

---

## 2026-07-21 · Claude Code

### code：UI 细节优化 + 已知问题记录

- **面包屑溢出截断**：深层路径自动从左侧折叠为 `… ▸ parent ▸ current`，保留最后 2 段可见。
- **文件树 tooltip**：`.file-name` 添加 `title` 属性，悬停 ~1s 显示完整文件名。
- **侧边栏 splitter 简化**：移除双线 + 渐变背景，改为单条 4px `var(--line)` 分隔线。
- **explorer 最小高度动态计算**：收缩下限由硬编码 `60px` 改为 `section-head + cwd-inline` 实际高度，刚好露出项目根目录选择器。
- **已知问题记录**：流式思考块首帧闪现左侧（疑似浏览器 flex 布局 bug，已尝试 6 种方案未根治），详见 `TODO.md`。

**涉及文件**：`index.html`、`styles.css`、`src/features/files.js`、`app.js`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-20 14:00 · Claude Code

### code：文件浏览器面包屑导航

- **面包屑路径栏**：隐藏的 `#filePathBar` 改为可点击面包屑，显示当前位置相对项目根的路径。每段目录可点击直接跳转，末段为当前位置不可点击。根目录时自动隐藏。
- **视觉设计**：小字号（11px）+ 低调色（muted），`▸` 分隔符，hover 高亮，不抢文件列表注意力。explorer 收起时同步隐藏。

**涉及文件**：`index.html`、`styles.css`、`src/features/files.js`

---

## 2026-07-20 10:00 · Claude Code

### code：多主题系统完成

- **主题引擎** (`src/core/theme-engine.js`)：15 套亮色主题 + 26 套暗色主题，含颜色数学工具（hexToRgb、mixColors、alphaStr）和 CSS 变量自动推导（deriveTheme），主题激活时设置所有 30+ 个 CSS 变量并切换 `color-scheme`。
- **主题设置面板**：`renderThemePanel()` 完整改为带色板预览的变体选择器——亮色/暗色/跟随系统三种模式，每种模式下列出全部可选主题变体，点击即时切换。
- **数据属性标记**：`<html>` 标记 `data-theme-mode`（light/dark）和 `data-theme-variant`（codex/catppuccin 等），方便 CSS 按主题变体做精细调整。
- **CSS 收口**：修复 stray `}` 语法错误，合并重复的 `:root` 和 `body.theme-dark` 块，补充 `--yellow`、`--file-*`、`--sidebar-scroll-thumb*`、`--user-bubble-bg` 等缺失变量，CSS 降级回退块与主题引擎保持一致。
- **文件树颜色自适应**：文件类型颜色（`--file-*`）不再硬编码，改为从主题 base 色派生——保留语义色相（JS=琥珀、Py=蓝…），饱和度和明度根据 surface 亮度自动适配，确保与背景 ≥4.5:1 对比度。同时检测 accent 色相冲突（距离 <25° 时自动偏转 35°），避免文件色与强调色混为一体。
- **HSL 色彩工具**：新增 `rgbToHsl`、`hslToRgb` 函数，`deriveFileColors()` 在 11 种文件类型上生成适配当前主题的文件色。
- **UI 微调**：用户消息气泡内边距 `10px 14px` → `8px 12px`；composer 上方安全区从 `+40px` 缩至 `+28px`，消息区底部内边距 `42px` → `20px`，消除输入框上方大片底色空隙。
- **验证**：全量 558 passed, 148 subtests passed。

**涉及文件**：`src/core/theme-engine.js`（新增）、`src/features/settings.js`、`app.js`、`index.html`、`styles.css`

---

## 2026-07-20 02:00 · Claude Code

### New API：支付FM 集成、支付页面设计、ngrok 回调就绪

- **支付FM 正式集成**：注册支付FM 个人商户（`673047478874292224`），获取接入密钥，在 dev 环境写入数据库验证。`PayAddress` 从 Mock Epay 切换为支付FM 真实网关（`https://api-5433f3im1bsw.zhifu.fm.it88168.com/api`），支付流程走到真实 QR 码。
- **ngrok 回调隧道**：因支付FM 拒绝 `localhost` 回调地址，使用 ngrok 将 `localhost:3001` 暴露为 `https://lived-abrasive-width.ngrok-free.dev`，`CustomCallbackAddress` 同步更新。支付创建成功，回调路径就绪（待他人扫码验证）。
- **支付页面专业设计**：`epay-mock/server.py` 完整重构支付页面——官方支付宝/微信彩色 SVG Logo、中英双语自动适配（`Accept-Language` 头检测）、实时倒计时（JS 秒级刷新）、自动轮询支付状态（`/status.php` 每 3 秒检测 → 支付成功自动跳转）、移除 Mock 标记和手动按钮。
- **支付超时对齐**：新增 `topUpExpireHandler` 系统任务（5 分钟扫描，与支付FM 默认 5 分钟一致），`EpayNotify` 增加 expired/异常状态订单拒绝回调逻辑。
- **支付渠道调研**：比较支付宝当面付（需营业执照+门头照）、自建 Epay（需 PHP+商户资质）、第三方 Epay（支付FM / ZPay / 码支付），确定短期走支付FM 免签、中长期走支付宝官方 API 路线。支付FM 费率约 0.5%（平台）+ 0.6%（支付宝）= 1.1%。
- **Mock 支付页面保留**：作为直接对接支付宝方案的 UI 模板，后续替换 QR 码来源即可上线。

**待办**：
- [ ] 找人扫码 1 元实测 ngrok 回调闭环
- [ ] 支付FM 后台修改商户名称为品牌名（当前为手机号）
- [ ] 获取营业执照后切签约模式或直接支付宝 API

**涉及文件**：`controller/topup.go`、`controller/system_task_handlers.go`、`model/system_task.go`、`epay-mock/server.py`

---

## 2026-07-19 22:28 · Claude Code

### New API：Epay 支付链路审查、Mock 搭建与端到端跑通

- **Epay Mock Server 搭建**：用纯 Python `http.server` 编写完整的易支付 Mock（`epay-mock/server.py`），包含 `submit.php`（创建订单）、`pay.php`（支付页面）、`notify.php`（回调通知）三个端点，支持标准 Epay MD5 签名算法。
- **支付全链路审查**：逐段追踪 `RequestEpay` → go-epay `Purchase` → Epay submit → 支付页面 → 回调 `EpayNotify` → 验签 → 订单状态更新 → 额度到账，发现并修复三个阻塞问题。
- **端口跳转修复**：`ServerAddress` 硬编码为 `http://localhost:3000`（生产网关），导致回调发到错误容器。通过数据库设置 `CustomCallbackAddress = http://localhost:3001` 解决，与 dev 环境对齐。
- **签名算法实现**：Mock 实现标准 Epay MD5 签名（`sort(params) → key1=val1&key2=val2... + EpayKey → MD5`），回调验签通过并成功触发订单完成与额度增加。

**支付链路（生产部署参考）**：
```
用户选金额/方式 → RequestEpay 创建订单(trade_no)
                → go-epay.Purchase() 生成签名
                → Epay submit.php 保存订单并返回支付页 URL
                → 用户扫码/支付
                → Epay notify.php 回调 New API /api/user/epay/notify
                → EpayNotify 验签(MD5) → 查订单 → 改状态 → IncreaseUserQuota
```

**关键配置项**：
| 配置 | 说明 | 值（dev） |
|---|---|---|
| `PayAddress` | Epay 网关地址 | `http://10.1.2.229:8081` |
| `EpayId` | 商户 ID | `1` |
| `EpayKey` | 商户密钥（用于 MD5 签名） | `test` |
| `CustomCallbackAddress` | 回调地址（优先于 ServerAddress） | `http://localhost:3001` |
| `ComplianceConfirmed` | 支付合规确认 | 必须 `true` |

**待办**：
- [ ] `ServerAddress` 应从环境变量读取，当前硬编码 `localhost:3000`
- [ ] 支付订单超时自动作废（`expired` 状态码已存在，缺定时检测逻辑）
- [ ] 部署前替换为真实 Epay 或直接对接支付宝个人商户

**涉及文件**：`controller/topup.go`、`controller/payment_webhook_availability.go`、`setting/system_setting/system_setting_old.go`、`setting/operation_setting/payment_setting_old.go`、`epay-mock/server.py`

---

## 2026-07-19 20:55 · Claude Code

### New API：SMTP 配置、邮件模板更新、删除用户级联清理

- **SMTP 配置**：New API 开发环境接入 Gmail SMTP（smtp.gmail.com:587 / STARTTLS），使用应用专用密码认证。SMTP 参数不通过 .env 设置，而是在后台「系统设置 → 集成 → SMTP Email」中配置后写入数据库。
- **邮件模板重写**：`new-api-source/controller/misc.go` 中邮箱验证码和密码重置两封邮件改用统一 HTML 模板，品牌名自动随 `SystemName` 变化，验证码独立高亮、重置按钮替代文字链接。
- **删除用户 Key 残留修复**：发现管理员删用户和用户自注销后 API Key 残留，SQLite 环境下新注册用户因 ID 复用继承旧 Key。修复 `model/user.go` 中 `Delete()`、`HardDelete()` 和 `HardDeleteUserById()` 三条路径，在事务中增加 `DELETE FROM tokens WHERE user_id = ?`。自注销实测零孤儿 token。
- **开发环境构建切换**：dev 容器镜像从 `Dockerfile.dev`（后端占位前端）切换为 `Dockerfile.local`（Bun 构建完整前端嵌入 Go 二进制），避免 :3001 访问出现 "use frontend dev server" 占位页。
- **数据库清理**：删除旧测试账号遗留的孤儿 token（user_id=3 及已删 user_id=2）和无关消费日志，保证测试环境数据干净。

**关键发现**：
- 原 root 账号已被重命名为 `fhy`（id=1, role=100），密码改为自定义值
- `users.access_token` 同时用于「个人 API 认证」和「code 客户端授权」，两者会互相覆盖
- 用户注销（`DeleteSelf`）调用 `DeleteUserById` → `User.Delete()`，仅软删除；`CheckUserExistOrDeleted` 使用 `Unscoped()` 导致注销后邮箱仍不可复用
- 管理员删用户走 `HardDeleteUserById`，独立于 `User.HardDelete()`，修复时需覆盖全部三条路径

**涉及文件**：`new-api-source/controller/misc.go`、`new-api-source/model/user.go`、`new-api-source-runtime/docker-compose.yml`、`new-api-source/Dockerfile.local`

---

## 2026-07-19 05:52 · Codex

### 完成内置 Skills 专项审查，并为 Agent 增加运行时工具边界

- **专项 Skill 收口**：重写代码审查、Skill 查找、Hyperframes、图像生成、Office 文件和 Python 测试 6 个专项 Skill，统一触发边界、事实核验、工具选择、安全限制和验证闭环；头脑风暴同步补齐性能证据边界、默认探索预算与最终回答检查。
- **打包资源兼容**：Skill 资源读取从固定的 `scripts/references/assets` 扩展到任意非隐藏打包目录及根目录文件，同时保留路径越界、隐藏文件、缓存目录和单文件大小限制；根目录 `**/*.md` 等 glob 现在能够正确匹配，文本搜索误用正则语法时返回明确提示。
- **Skill 工具约束下沉**：系统注入 Skill 正文时同时声明 Preferred tools，并明确正文已加载、无需重复调用 `use_skill`；未声明 `task` 的 Skill 会在运行前从实际工具白名单中移除，用户明确要求并行 Agent 或子任务时仍可使用。
- **探索预算持久化**：`brainstorming` 默认将搜索/枚举限制为 3 次、定向读取限制为 4 次；预算随服务端 Agent 任务持久化，达到上限后相关工具从后续模型轮次移除，同轮超额调用返回可恢复的预算错误。明确要求深度审计时不套用默认预算。
- **修复工具结果 Token 放大**：Agent 原先只截断工具结果的 `content` 字段，宽泛搜索的 `results` 数组可把数十万字符完整带入模型上下文；现在整条模型工具消息统一限制为 12,000 字符，完整结果仍保留给界面和会话记录。
- **会话信息改显消息记录**：会话创建、保存、加载和分支接口同时返回元数据 JSON 与消息 JSONL 的绝对路径；会话信息面板及复制按钮改为使用 `.jsonl` 消息记录地址，元数据 `.json` 仍保留给内部状态、用量和分支持久化。
- **固化分阶段协作模式**：`AGENTS.md` 与 `CLAUDE.md` 统一补充单阶段推进、自动/人工验收分流、测试失败不提交、人工确认后收口、日志与 TODO 同步、精确暂存及可核验交付要求，后续 Codex 与 Claude Code 使用同一套开发节奏。
- **真实会话验证**：专项评估目录新增可重复的人工测试题；`brainstorming` 复测中无 `task`，发现类工具仅执行预算内 3 次。工具结果总量修复后，同一测试累计输入从 `861,440` 降至 `41,998`，非缓存新增输入从约 `286,336` 降至 `17,294`，最大单轮 prompt 从约 `282,338` 降至 `13,625`。
- **验证结果**：Agent 预算、任务白名单、Skill 路由/结构、资源读取、根目录 glob、正则提示、完整工具消息截断和 JSONL 会话地址均有自动化覆盖；会话路径定向回归 `112 passed, 6 subtests passed`，最终全量回归 `583 passed, 148 subtests passed`。性能类最终回答偶尔仍会把未测量数字标作假设，已作为结构化输出校验的后续事项保留在 `TODO.md`。

**涉及文件**：`AGENTS.md`、`CLAUDE.md`、`agent-runtime.js`、`app.js`、`server.py`、`src/features/skills-memory.js`、`src/ui/panels.js`、`data/skills/brainstorming/SKILL.md`、`data/skills/code-review/SKILL.md`、`data/skills/find-skills/SKILL.md`、`data/skills/hyperframes/SKILL.md`、`data/skills/image-generation/SKILL.md`、`data/skills/office-files/SKILL.md`、`data/skills/python-testing/SKILL.md`、`tests/skill-evaluation.md`、`tests/test_agent_runtime.py`、`tests/test_branch.py`、`tests/test_builtin_skills.py`、`tests/test_frontend_modules.py`、`tests/test_p2_coverage.py`、`tests/test_routes.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-19 03:28 · Codex

### 将通用工作流 Skills 改写为 Code 原生指令，补齐结构验证

- **清理外部环境依赖**：改写头脑风暴、并行子 Agent、执行计划、收到/请求代码审查、子 Agent 驱动开发、TDD 和编写计划 8 个工作流，移除 `superpowers:*`、不存在的下游 Skill 和平台专用调度语法。
- **对齐 Code 行为边界**：统一使用当前 `task`、文件、命令和用户输入工具；明确子 Agent 共享工作区、只读任务可并行、重叠写入必须串行，且最终整合与验证由主 Agent 负责。
- **降低上下文成本**：8 个通用工作流从约 1,618 行收紧到约 308 行，保留决策边界、执行闭环、失败处理和验收要求；`document-design` 同步压缩重复色板表格，所有 `SKILL.md` 均低于 500 行。
- **修正打包验证器**：`quick_validate.py` 现在允许显式调用型 Skill 省略 `keywords`，并新增目录/名称一致性、Code 工具白名单、500 行上限、资源链接存在性和路径越界检查。
- **结构回归固化**：新增 4 类内置 Skill 结构测试，确保工作流声明工具、不引用未安装 Skill、相对链接可读且全部可通过打包验证。
- **验证结果**：定向结构回归 `10 passed, 123 subtests passed`，最终全量回归 `574 passed, 148 subtests passed`。

**涉及文件**：`data/skills/brainstorming/SKILL.md`、`data/skills/dispatching-parallel-agents/SKILL.md`、`data/skills/executing-plans/SKILL.md`、`data/skills/receiving-code-review/SKILL.md`、`data/skills/requesting-code-review/SKILL.md`、`data/skills/subagent-driven-development/SKILL.md`、`data/skills/test-driven-development/SKILL.md`、`data/skills/writing-plans/SKILL.md`、`data/skills/document-design/SKILL.md`、`data/skills/skill-creator/SKILL.md`、`data/skills/skill-creator/scripts/quick_validate.py`、`tests/test_builtin_skills.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-19 03:14 · Codex

### 收紧内置 Skills 自动匹配，建立可重复的路由测试基线

- **取消描述猜测**：前后端均不再用 Skill 描述里的普通单词触发自动加载，只根据明确关键词或 Skill 名称匹配，解决解释 Python 知识时误加载测试规范等问题。
- **关键词按意图收紧**：区分代码审查与直接修复、Office 读取与文档生成、数据图表与 AI 图片、界面设计与通用头脑风暴，避免 `bug`、`生成`、`设计`、`Word` 等宽泛词导致多 Skill 冲突。
- **审查意见单独分流**：为 `receiving-code-review` 补齐复合关键词和必要读取/验证工具，其优先级高于普通代码审查，可对已收到的 review feedback 先做技术判断。
- **测试题固化**：新增内置 Skill 路由测试，覆盖 9 组正向任务、3 组误触发反例、工具可用性与目录/名称一致性；前端模块同步锁定“描述不触发”边界。
- **验证结果**：定向回归 `6 passed, 46 subtests passed`，最终全量回归 `569 passed, 71 subtests passed`。本阶段不改动 Skill 正文、工具执行、权限或会话状态。

**涉及文件**：`server.py`、`src/features/skills-memory.js`、`data/skills/*/SKILL.md`（触发元数据）、`tests/test_builtin_skills.py`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-19 02:56 · Codex

### 欢迎页完成五种随机光标接力，并稳固原生输入焦点

- **前半段保持不变**：继续使用既有 `Code` 字标逐字出现、`335ms` 靠近标语和 `780ms` 标语展开时间轴；两段仍共享同一开始时间，只在标语完整出现并停顿 `150ms` 后进入新的接力阶段。
- **五种接力机制**：加入回车换行、柔性换行、信号接力、指令封装和焦点跃迁，分别表达输入换行、连续折行、状态传递、指令派发和焦点切换；轨迹、脉冲及标记均在结束或中断时统一清理。
- **受控随机播放**：五种方案按 `30% / 30% / 20% / 15% / 5%` 权重选择，并以会话级记录排除连续重复；深浅主题继续复用现有颜色变量，不引入独立配色。
- **真实输入交接**：动画落点与真实输入框坐标绑定，落地时和模拟光标退场后各确认一次输入焦点与末尾选区；用户提前点击、按键或输入仍会立即终止动画并进入真实输入状态。
- **环境边界确认**：Edge 中动画结束后可直接输入；Codex 内置浏览器虽然页面内活动元素已是输入框，但宿主 WebView 仍需一次页面点击才能接收键盘事件，确认为内嵌浏览器外层焦点限制，不增加产品侧特殊分支。
- **设计过程留档**：新增几何路线与完整五方案两个独立 HTML 对比页，保留方案选择、完整动画节奏和深浅主题演示，便于后续继续调整。
- **验证结果**：`app.js` JavaScript 语法、`git diff --check`、欢迎页定向回归 `34 passed` 通过；最终全量回归 `564 passed, 25 subtests passed`。人工确认五种动效、随机切换、前半段节奏、提前输入中断和 Edge 原生焦点均正常。

**涉及文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`design/code-welcome-caret-flight/preview.html`、`design/code-welcome-caret-handoff/preview.html`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-19 01:46 · Codex

### 文件树修改时间按 320px 侧栏边界自适应显示

- **明确显示边界**：侧栏宽度小于 `320px` 时使用紧凑时间——当天显示 `HH:mm`、当年其他日期显示 `MM/DD HH:mm`、跨年显示 `YYYY/MM/DD`；达到 `320px` 后显示完整 `YYYY/MM/DD HH:mm`。
- **完整信息保留**：紧凑模式下悬停时间仍能查看完整时间，时间数字采用等宽排布；文件行悬停出现 `@` 按钮时，时间淡出以避免遮挡。
- **既有能力保持**：文件接口继续返回同一 `updatedAt`，默认/类型/时间排序口径、文件点击、右键菜单、附件与预览行为均未改变；侧栏现有 220–480px 拖拽范围保持不变。
- **回归保护**：新增当天、当年、跨年、无效时间格式和 `319px`/`320px` 边界测试，并锁定紧凑/完整时间节点与悬停样式。
- **验证结果**：`src/features/files.js` 与 `app.js` JavaScript 语法、`git diff --check` 和模块回归 `34 passed` 通过；最终全量回归 `564 passed, 25 subtests passed`。人工确认侧栏宽窄切换、完整时间提示、`@` 按钮避让和时间排序均正常。

**涉及文件**：`src/features/files.js`、`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-19 01:21 · Codex

### 抽离顶部面板与 Session Info，完成前端拆分阶段 3

- **面板模块独立**：新增 `src/ui/panels.js`，集中承接顶部 Session Info、Tool Log、分支面板的互斥开关、外部点击关闭和分支面板开关状态同步；分支树与 Tool Log 内容投影仍由原业务所有者生成。
- **会话统计收口**：消息角色计数、累计输入/输出/缓存 Token、最后一次 API 上下文用量、估算降级、模型上下文上限、环形进度和告警等级统一迁入面板模块，现有统计口径保持不变。
- **Session Info 字段迁移**：创建/活跃时间、会话文件路径与 ID 提示、消息分项、Token 分项、上下文占比和路径复制反馈由模块统一刷新；切换会话时继续读取当前会话独立账本。
- **旧实现退场**：`app.js` 删除原面板统计、路径、开关和外部关闭实现，通过显式 getter、渲染回调与状态回调装配新模块，净减少约 202 行；`index.html` 在应用入口前加载面板脚本。
- **回归保护**：新增独立 Node 测试，覆盖真实 `prompt_tokens` 优先级、估算降级、流式消息排除、消息/工具计数、时间与路径格式、统计字段投影、环形告警、三个面板互斥、外部关闭、幂等事件绑定和旧实现禁入。
- **验证结果**：`src/ui/panels.js` 与 `app.js` JavaScript 语法、`git diff --check`、模块定向回归 `34 passed`、稳定性/覆盖/子 Agent 前端回归 `94 passed, 4 subtests passed` 均通过；最终全量回归 `564 passed, 25 subtests passed`。人工确认 Session Info 数据、路径复制、三个顶部面板互斥与空白处关闭、会话切换后的统计刷新均正常。

**涉及文件**：`src/ui/panels.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-19 00:40 · Codex

### 抽离时间线与消息流标记模块，并补齐分支继承和表单控件边界

- **时间线能力独立**：新增 `src/ui/timeline.js`，集中承接用户消息时间线节点、点击定位、分支来源标记、上下文压缩标记及旧压缩摘要统计兼容；欢迎页、消息列表和滚动策略仍由应用装配层管理。
- **分支标记恢复**：完整会话加载后会把 `_parentId`、分支深度、子分支列表和分支消息边界回填到轻量会话摘要，解决刚创建或重新进入分支时消息流缺少来源标记的问题；标记继续按原始消息边界插入，不改变消息稳定顺序。
- **分支用量继承**：创建分支时显式建立父会话累计 `stats` 的独立副本，并同时继承服务端 `lastUsage` 上下文基线；分支后续用量从继承值继续累加，父子会话此后保持隔离。
- **表单提交边界修复**：权限模式和思考强度的 8 个选项补齐 `type="button"`，避免输入框已有内容时切换选项触发聊天表单提交；模型选择原本已有普通按钮类型，行为保持不变。
- **回归保护**：新增时间线节点过滤与截断、点击定位、压缩统计、分支元数据回填、真实分支 API 用量复制、聊天表单按钮类型和旧实现禁入测试；刷新滚动、消息投影与分支测试同步改为验证新模块所有权。
- **验证结果**：`src/ui/timeline.js`、`app.js` JavaScript 语法、`server.py` Python 编译检查及 `git diff --check` 通过；最终全量回归 `563 passed, 25 subtests passed`。人工确认时间线点击定位、分支来源标记、分支累计用量继承与独立累加，以及权限模式、模型和思考强度切换均正常且不会误发输入内容。

**涉及文件**：`src/ui/timeline.js`、`app.js`、`index.html`、`server.py`、`tests/test_branch.py`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`tests/test_p2_coverage.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 23:53 · Codex

### 抽离消息分组与投影模块，完成前端拆分阶段 3 的第三项

- **消息投影独立**：新增 `src/ui/messages.js`，集中承接内部消息过滤、工具轮次思考摘要分组、用户消息与图片、问卷摘要、最终回答、后台回复引用、编辑建议插槽、分支/压缩插槽及活动任务锚点的稳定顺序投影。
- **回复状态统一**：Token 用量标准化、耗时状态、消息时间戳和复制按钮迁入消息模块；此前修复的真实耗时持久化与历史缺失耗时降级行为保持不变。
- **流式边界保持**：`app.js` 仍拥有欢迎页、活动状态栏节点、增量流式 DOM 补丁、事件绑定、自动滚动、会话切换和网络恢复状态；消息模块只通过显式注入组合 Markdown、Diff、分支、压缩和恢复提示，不改变 SSE 或会话协议。
- **旧实现退场**：`app.js` 删除消息分类、分组和 HTML 投影实现，净减少约 321 行；`index.html` 在应用脚本前加载新模块，正式 EXE 继续通过既有 `src` 资源目录自动收录。
- **回归保护**：新增独立 Node 投影测试，覆盖用户/助手/工具消息过滤、思考与最终回答分离、活动状态锚点、后台任务状态与回复引用、分支顺序、编辑建议、流式回答、用量及缺失耗时；原刷新恢复、后台任务、压缩与分支测试同步改为验证新所有者，并禁止旧实现回流 `app.js`。
- **验证结果**：`src/ui/messages.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `132 passed, 4 subtests passed`，最终全量回归 `559 passed, 25 subtests passed`。人工确认普通只读任务的用户 Markdown、思考摘要、最终回答、模型名、Token、耗时、时间戳、复制按钮、刷新恢复，以及旧后台会话引用定位均正常，未发现重复或闪烁。

**涉及文件**：`src/ui/messages.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`tests/test_p2_coverage.py`、`tests/test_subagent_frontend.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 23:22 · Codex

### 修复模型回复耗时刷新后丢失并显示为 0s

- **完成时序修正**：会话检查点清理现在先调用统一的耗时收口逻辑，再序列化并持久化最终消息；正常完成和刷新恢复完成共用同一边界，避免 `_responseTime` 只留在内存中。
- **历史数据诚实降级**：旧会话若本来没有耗时字段，状态栏只显示现有 Token 用量，不再用 `0s` 伪装为真实耗时；用量与耗时之间的分隔符也改为按字段是否存在动态输出。
- **回归保护**：新增测试锁定“先完成计时、后持久化消息”的调用顺序，并验证缺少历史耗时时不会渲染虚假的零秒。
- **验证结果**：`app.js` JavaScript 语法与 `git diff --check` 通过；定向回归 `79 passed`，最终全量回归 `558 passed, 25 subtests passed`。人工运行逐秒输出任务得到 `20s`，刷新页面后耗时保持不变。

**涉及文件**：`app.js`、`tests/test_p0_stability.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 23:04 · Codex

### 抽离 Diff 与编辑建议卡片模块，完成前端拆分阶段 3 的第二项

- **Diff 能力独立**：新增 `src/ui/diff.js`，集中承接代码围栏与前导文本清洗、增删行统计、文件扩展名识别、Hunk/上下文行号计算、语法高亮接入和长 Diff 折叠 HTML 生成。
- **编辑建议投影收口**：编辑建议消息识别、文件目标、增删统计、待确认/排队/处理中/仅建议/已应用/已拒绝状态及卡片 HTML 迁入新模块；普通 Markdown 建议仍通过注入的 Markdown 渲染器展示。
- **交互与授权边界保持**：应用、拒绝、展开/收起、复制和路径打开事件仍由 `app.js` 绑定，文件写入审批、授权队列、已应用状态及消息顺序不变；Markdown 代码围栏继续通过显式注入调用同一 Diff 渲染器。
- **旧实现退场**：`app.js` 删除 Diff 清洗、统计、渲染和编辑卡片实现，净减少约 133 行；`index.html` 在 Markdown 模块前加载 Diff 模块，确保应用装配时依赖可用。
- **回归保护**：补充模块存在与加载顺序、公开导出、围栏清洗、文件头统计排除、Hunk 行号、语言识别、危险 HTML 转义、长 Diff 折叠，以及待确认/排队/已应用/无变化卡片测试，并禁止旧定义重新进入 `app.js`。
- **验证结果**：`src/ui/diff.js`、`src/ui/markdown.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `30 passed` 与 `116 passed, 19 subtests passed`，最终全量回归 `556 passed, 25 subtests passed`。人工在计划模式生成 45 行编辑建议，确认统计、折叠、展开/收起、复制、路径预览、刷新恢复及无实际写入均正常。

**涉及文件**：`src/ui/diff.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 22:44 · Codex

### 抽离 Markdown、代码块与 ANSI 渲染模块，进入前端拆分阶段 3

- **渲染能力独立**：新增 `src/ui/markdown.js`，集中承接 Markdown 解析、JavaScript/Python/HTML/CSS/JSON 轻量语法高亮、语言别名解析、ANSI 转义渲染以及代码围栏路由。
- **HTML 后处理收口**：本地路径点击、外部链接新标签页、本地图片 URL 转换和代码块复制所需标记统一由 Markdown 模块生成；用户消息与模型回复继续共用既有 Markdown 展示行为，原始消息的保存和模型输入不变。
- **职责边界保持**：Diff 解析与卡片渲染仍由 `app.js` 持有并以依赖形式注入，消息列表、流式投影、滚动、会话状态及真实点击动作均未迁移，避免本阶段改变流式 DOM 生命周期。
- **旧实现退场**：`app.js` 删除原语法规则、ANSI、Marked renderer 和 Markdown 后处理实现，净减少约 290 行；`index.html` 在功能模块和应用脚本前加载新的 UI 模块。
- **回归保护**：补充模块存在与加载顺序、公开导出、代码高亮、语言别名、ANSI、代码/终端/Diff 围栏、本地图片、外部链接和本地路径后处理测试，并禁止旧定义重新进入 `app.js`。
- **验证结果**：`src/ui/markdown.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `29 passed` 与 `74 passed, 6 subtests passed`，最终全量回归 `555 passed, 25 subtests passed`。人工确认用户消息和模型回复中的标题、列表、粗体、行内代码、JavaScript/JSON 高亮、行号、复制按钮、Diff 增删样式、本地路径与外部链接均正常。

**涉及文件**：`src/ui/markdown.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 22:16 · Codex

### 抽离设置、更新与认证模块，完成前端拆分阶段 2

- **设置功能独立**：新增 `src/features/settings.js`，集中承接统一设置页导航、模型配置界面、Key 编辑器、系统提示词、主题与语言、平台账户、首次使用引导和旧设置弹窗入口。
- **更新与平台认证收口**：版本提示、更新检查去重、下载进度、安装重启后的版本确认与缓存刷新，以及 Code × New API 登录回调、登录状态、Key 同步和复制弹窗均迁入新模块。
- **执行边界保持**：模型选择、API Key 轮换、权限和 AgentRun 执行链继续由 `app.js` 持有；设置模块只通过显式注入读取界面状态并调用保存、刷新、翻译及 Skills/Memory 面板接口，`loadKeyConfig()` 作为最小公开入口供请求链读取启用状态。
- **旧实现退场与稳定性**：`app.js` 删除 Key 编辑器、设置页、主题、更新、引导、平台认证及重复事件绑定，共减少约 1,291 行；模型设置页对已不存在的旧 Key 显隐按钮改为可选绑定，避免打开设置时产生空节点异常。
- **回归保护**：补充模块存在与加载顺序、公开导出、主题持久化、更新请求去重、平台登录回调、Key 配置读取和旧定义禁入测试；更新安装的版本确认测试改为验证实际所有者 `settings.js`。
- **验证结果**：`src/features/settings.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `28 passed` 与 `185 passed, 10 subtests passed`，最终全量回归 `554 passed, 25 subtests passed`。人工确认模型、账户、Memory、Skills、系统提示、主题、语言与更新页面，Key 临时增删、主题刷新保持及中英文切换均正常。

**涉及文件**：`src/features/settings.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`tests/test_server.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 21:44 · Codex

### 抽离 Skills 与 Memory 模块，完成前端拆分阶段 2 的第三项

- **领域逻辑独立**：新增 `src/features/skills-memory.js`，集中承接 Skill 摘要与正文渐进加载、自动匹配、斜杠建议、启停与 CRUD，以及 Memory 上下文加载、状态提示和设置页管理。
- **匹配规则固化**：Skill 自动匹配继续按“显式关键词 → Skill 名称 → 描述词”分层取最强命中，排除仅允许显式调用的规划类 Skill 与用户禁用项；命中后再懒加载正文，避免扩大初始请求。
- **装配边界收口**：`app.js` 只负责注入共享状态、API、翻译、通知和界面刷新回调，并保留系统提示词组装与显式 `/skill` 执行入口；原 Skills/Memory 实现和重复事件绑定已删除。
- **回归保护**：补充模块存在与加载顺序、公开导出、匹配优先级、显式 Skill 排除、禁用项排除、Skill 正文懒加载、Memory 上下文加载和旧定义禁入测试。
- **验证结果**：`src/features/skills-memory.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `27 passed` 与 `98 passed, 10 subtests passed`，全量回归 `553 passed, 25 subtests passed`。人工确认 Skills 列表与详情、禁用状态持久化、斜杠建议、Memory 新建/编辑/删除和上下文提示均正常。

**涉及文件**：`src/features/skills-memory.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 21:21 · Codex

### 抽离多格式预览模块，完成前端拆分阶段 2 的第二项

- **预览功能独立**：新增 `src/features/preview.js`，集中承接文本/代码、Markdown、CSV/TSV、图片和 PDF 预览，以及预览模式切换、表格分页、图片缩放拖拽、宽度调整、自动刷新和页面刷新后的预览恢复。
- **依赖边界收口**：文件树继续只通过 `openFile` 回调请求打开文件；Markdown 渲染、语法高亮、通用复制、格式化和 API 请求由 `app.js` 在装配时显式注入，预览模块不反向读取其他功能模块的内部变量。
- **旧实现退场**：`app.js` 删除预览渲染器、CSV 解析器、轮询计时器、宽度拖拽状态和重复事件绑定，只保留预览模块创建、公开方法接线与启动恢复调用；`index.html` 在文件模块和应用脚本前加载预览模块。
- **回归保护**：补充模块存在与加载顺序、公开导出、CSV 引号及跨行字段解析、最大行数限制、原始文件 URL、预览宽度约束和旧定义禁入测试；富预览与窄栏性能测试改为直接验证新模块所有者。
- **验证结果**：`src/features/preview.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `72 passed, 6 subtests passed`，全量回归 `552 passed, 25 subtests passed`。人工确认代码、Markdown、GBK CSV、图片缩放、预览宽度、刷新恢复和关闭后重新打开均正常。

**涉及文件**：`src/features/preview.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`tests/test_p2_coverage.py`、`tests/test_rich_previews.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 20:53 · Codex

### 抽离文件树与普通附件模块，进入前端拆分阶段 2

- **产品功能独立**：新增 `src/features/files.js`，集中承接文件列表加载、搜索、排序、目录导航、右键菜单、项目目录选择、最近目录、新建文件夹和普通文件附件上传，并通过 `window.Code.features.files` 暴露稳定入口。
- **职责边界明确**：`app.js` 改为创建并装配文件功能实例，只保留预览实现、图片附件处理以及消息编辑等其他领域逻辑；文件打开统一通过注入的 `openFile` 回调进入现有预览流程，避免本阶段同时改变预览行为。
- **事件入口收口**：移除项目目录按钮的内联事件和 `app.js` 中重复的文件事件绑定，改由文件模块一次性绑定；`index.html` 在应用脚本前按依赖顺序加载新模块。
- **回归保护**：补充模块导出、路径缩写、文件排序、附件上传、路径插入、脚本加载顺序、旧实现禁入和内联事件禁入测试。
- **验证结果**：`src/features/files.js` 与 `app.js` JavaScript 语法、`git diff --check` 通过；定向回归 `80 passed, 6 subtests passed`，全量回归 `551 passed, 25 subtests passed`。人工确认文件树、目录导航、搜索排序、右键菜单、项目目录、新建文件夹、文件预览及普通附件路径插入均正常。

**涉及文件**：`src/features/files.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 20:33 · Codex

### 抽离通用 API 客户端，完成前端拆分阶段 1

- **请求层独立**：新增 `src/services/api-client.js`，通过 `window.Code.services.apiClient` 提供 `apiJson()`；统一保留 JSON 请求头合并、响应解析、服务端错误和非 JSON 错误处理，现有业务调用签名无需调整。
- **边界保持**：`app.js` 删除重复请求实现并改为导入服务模块；模型 `/proxy/chat`、SSE、AgentRun、后台任务、模型列表和其他专用请求继续留在原所有者中，本阶段不改变执行链或界面行为。
- **加载与回归保护**：`index.html` 在 `app.js` 前加载 API 客户端；模块存在性、脚本顺序、公开导出和重复定义禁入测试同步更新，并实际覆盖成功 JSON、服务端错误、非 JSON 错误、空成功响应及自定义请求头。
- **验证结果**：JavaScript 语法与 `git diff --check` 通过，前端模块定向回归 `24 passed`；最终全量回归为 `550 passed, 25 subtests passed`。

**涉及文件**：`src/services/api-client.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 20:20 · Codex

### 固化界面文案与 i18n 维护检查约定

- **统一入口**：在根目录 `README.md` 增加“界面文案与 i18n”开发约定，明确需要翻译与保持原文的内容边界、静态和动态文案接入方式，以及中英文 key 必须成对维护的要求。
- **接手必读**：`AGENTS.md` 增加界面文案任务的强制入口，要求后续协作方遵循同一份 README 检查清单，不得在 `app.js` 或业务文件重新建立局部词典。
- **固定验收**：记录 i18n 语法与定向测试命令，并把中英文即时切换、刷新持久化和动态界面残留检查列为固定人工验收项。

**涉及文件**：`AGENTS.md`、`README.md`、`CHANGELOG.md`

---

## 2026-07-18 20:07 · Codex

### 抽离浏览器 i18n 核心模块，统一语言切换运行时

- **模块独立**：新增 `src/core/i18n.js`，集中承接原 `app.js` 内的 `LANG` / `I18N` 字典、参数插值、静态与动态 DOM 翻译、主题及文件排序标签刷新，并通过 `window.Code.core.i18n` 暴露稳定模块接口。
- **业务边界收口**：`app.js` 改为创建 i18n runtime，只注入当前语言、`code-lang` 持久化和切换后的模型、权限、会话、消息及上下文重绘回调；现有文案、存储键、HTML `data-i18n` 行为和中英文切换流程保持不变。
- **加载与回归保护**：`index.html` 在 `app.js` 前显式加载 i18n 模块；模块存在性、加载顺序、独立翻译与插值、切换回调、中英文词典缺键、重复定义禁入和原有文案归属测试同步更新。
- **验证结果**：`src/core/i18n.js` 与 `app.js` JavaScript 语法、`git diff --check`、i18n/前端定向回归 `66 passed, 4 subtests passed` 通过；最终全量回归为 `549 passed, 25 subtests passed`。人工确认中文、英文切换与刷新保持未发现明显问题。

**涉及文件**：`src/core/i18n.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`tests/test_p2_coverage.py`、`tests/test_subagent_frontend.py`、`docs/APP_JS_SPLIT_PLAN.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 19:40 · Codex

### 删除旧浏览器 Agent 编排链，完成前端执行层瘦身

- **不可达代码清理**：从 `app.js` 删除旧 `runAgentLoop`、浏览器工具执行、子任务委派、并发映射、重复工具抑制、旧自动压缩分支及相关辅助函数；同时移除已无写入入口的消息队列、排队渲染、停止回填和状态字段，共减少约千行旧执行代码。
- **单一所有权固化**：正式主任务和同会话后台任务继续只进入服务端 AgentRun。结构测试改为明确禁止 `runAgentLoop`、`executeToolWithDelegation`、`executeToolCall`、`mapWithConcurrency`、`mergeDelegatedUsage` 和 `messageQueue` 回归，避免未来重新形成浏览器/服务端双重消费。
- **视觉能力迁移**：保留原浏览器循环的图片工具能力，将 `read_file` 图片结果改由服务端 AgentRun 在下一模型轮次展开为 `image_url`。持久消息只保存工具调用 ID 标记，base64 仍以单份工具执行结果恢复，避免视觉消息再复制一份大数据；PNG/base64 与标记轻量化均有回归覆盖。
- **测试同步**：把并发、授权、用量、网络退避、SSE 原子收束、上下文压缩和图片视觉测试更新为当前 Server Agent 边界；JavaScript 语法、`git diff --check` 与专项回归通过，最终全量回归为 `548 passed, 25 subtests passed`。

**涉及文件**：`app.js`、`server.py`、`tests/test_concurrency.py`、`tests/test_frontend_modules.py`、`tests/test_image_vision_and_browser_refresh.py`、`tests/test_p0_stability.py`、`tests/test_p2_coverage.py`、`tests/test_subagent_frontend.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 19:09 · Codex

### 将同会话后台消息迁入持久 AgentRun，完成旧浏览器循环入口退役

- **后台任务服务端化**：主任务输出期间再次发送的消息不再调用浏览器 Agent 循环，而是创建独立服务端 AgentRun；后台任务继承当次模型、权限、工具预设、思考参数、图片输入和截止时间，但移除 `task` 与 `request_user_input`，不会再次委派或打开独立问卷。
- **幂等创建与恢复**：前端为每条后台消息保存稳定 `clientRequestId`，服务端据此生成确定性 AgentRun ID，并在内存和持久记录中双重查重。即使创建响应丢失、页面刷新或服务重启，也会重新附着原任务而不是发起第二次上游请求；会话 `backgroundRuns` 检查点保存恢复所需信息，终态消息落盘后才清除。
- **主后台状态隔离**：主任务与后台任务分别持有运行状态、授权投影、截止时间、结果和用量；后台授权不会替换主任务检查点，后台完成或失败只合并一次消息与用量，切换会话、新建会话和刷新不会打断任一执行链。
- **端到端独立计时**：主任务和每条后台消息都从用户发送时刻计时，到各自结果落入会话时结束，后台排队、模型、工具与刷新重连均计入用户感知耗时。起点随主检查点或后台检查点持久化，刷新恢复时先写回 `taskStartTime` 再启动流式状态；成功与失败结果均保存独立 `_responseTime`，解决先完成任务显示 `0s`、主任务刷新后重新起算的问题。
- **完成顺序与回复关联**：用户消息继续按发送顺序显示，主任务和后台结果按实际完成顺序排列。后台正文不再强制拼接“后台处理 + 完整提示词”，改为基于稳定任务 ID 的单行“回复”引用；点击引用会滚动并高亮对应用户消息，相同提示词、刷新恢复和完成顺序变化都不会串联。
- **人工端到端验证**：自动模式下多次执行主任务与后台逐秒输出，覆盖不刷新和运行中刷新。最终验证后台先完成显示 `7s` 并先呈现，主任务后完成显示 `15s` 并随后呈现；两条结果各出现一次、用量独立、主任务未被打断，后台回复引用与正文简化显示正确。
- **自动化验证**：Python 编译、JavaScript 语法检查和 `git diff --check` 通过；AgentRun 定向回归 `108 passed, 13 subtests passed`，扩展回归 `191 passed, 19 subtests passed`，最终前端/计时定向回归 `95 passed`，全量回归 `553 passed, 25 subtests passed`。

**涉及文件**：`server.py`、`agent-runtime.js`、`app.js`、`styles.css`、`tests/test_agent_runtime.py`、`tests/test_concurrency.py`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`tests/test_subagent_frontend.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 17:55 · Codex

### 退役持久旧浏览器检查点恢复，封闭主任务的浏览器回退入口

- **旧检查点停止重放**：迁移前保存为 `executionOwner=browser` 的活动任务在恢复时停止所有流式消息、保留已有会话内容、写入明确失败说明并持久化为 `legacy-browser-retired`；不再根据检查点时间自动调用旧模型/工具链，避免重复执行可能已经发生的写入或命令。
- **主任务入口收口**：主任务统一执行入口现在只接受服务端 AgentRun，“继续”操作也经过同一入口；如果未来代码错误地传入浏览器所有权，会明确报错而不是静默退回旧循环。
- **保留边界**：审计确认“同一会话输出中再次发送消息”仍直接启动浏览器后台子任务，因此本阶段未删除旧循环。下一阶段先迁移这一独立入口，再清理旧模型、工具和子任务编排代码。
- **自动化验证**：JavaScript 语法检查、旧检查点/继续入口定向回归 `18 passed` 通过；最终全量回归 `539 passed, 25 subtests passed`。

**涉及文件**：`app.js`、`tests/test_p0_stability.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 17:42 · Codex

### 将自动模式切换到服务端 AgentRun，完成全部新任务的单一所有权迁移

- **自动模式所有权**：界面现有“自动”入口现在与只读、计划和接受编辑一致，为新任务创建服务端 AgentRun；自动模式仍按原产品语义直接执行允许的编辑、写入、删除和命令，不增加授权弹窗，但继续经过服务端安全检查、幂等与取消协议。
- **历史兼容边界**：恢复任务时继续优先采用检查点已保存的 `executionOwner`。迁移前明确记录为 `browser` 的活动任务仍走旧链路，不会在中途切换所有者；新任务的四种有效权限全部选择 `server-agent`。
- **人工端到端验证**：已确认自动模式直接写入与删除无需授权、长命令在页面刷新后继续并返回结果、停止中的命令不会在刷新后自行恢复，测试文件完成清理。
- **自动化验证**：JavaScript 语法检查、`git diff --check`、AgentRun/前端定向回归 `74 passed, 13 subtests passed` 通过；最终全量回归 `537 passed, 25 subtests passed`。

**涉及文件**：`app.js`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 17:24 · Codex

### 将计划与接受编辑正式切换到服务端 AgentRun 单一执行所有权

- **正式所有权切换**：`read`、`plan` 和 `accept` 现在统一进入服务端 AgentRun；`bypass` 暂时保留原浏览器链路。创建与恢复任务时均按任务自身权限档位和工具预设生成工具集合，避免刷新后误用界面当前选项；计划档位不会因“完整工具”预设获得命令或直接文件变更能力。
- **真实授权投影**：前端不再把所有服务端等待伪装成 `propose_edit`，而是按 `apply_edit`、`write_file`、`delete_file` 或 `run_command` 展示正确的动作、路径、命令和 diff 统计。授权请求与 diff 卡进入会话检查点，刷新后可以继续批准或拒绝同一个 AgentRun。
- **结果卡闭环**：计划模式的编辑提案以“仅方案”卡片展示且不落盘；接受模式的直接写入、删除和编辑批准复用原授权卡承接“等待批准 → 处理中 → 已应用/已拒绝”，避免为同一 `tool_call_id` 生成重复工具结果。子任务代理授权会读取嵌套子任务结果，并在父任务完成时收束直接文件操作状态。
- **人工端到端验证**：已确认计划提案不修改文件、接受模式写入授权在刷新后仍可恢复、删除授权能够完成测试文件清理、运行中停止不会自行续跑。
- **自动化验证**：JavaScript 语法检查、`git diff --check`、AgentRun/前端定向回归 `74 passed, 13 subtests passed` 通过；最终全量回归 `537 passed, 25 subtests passed`。

**涉及文件**：`app.js`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 16:46 · Codex

### 为同轮子任务建立有界并发调度和确定性结果顺序

- **并发上限**：父 AgentRun 遇到同一模型轮次连续的多个 `task` 调用时，最多同时启动 3 个持久 Child AgentRun；第 4 个及后续调用保持排队，只有活动子任务进入终态后才占用释放的空位，避免无界线程和上游请求扩张。
- **协议顺序**：子任务可以按实际完成时间落盘结果与用量，但发送给父模型的 `tool` 消息、`tool_completed` 事件和待调用移除顺序始终遵循原始工具调用顺序，防止并发完成顺序改变模型上下文。
- **恢复与授权兼容**：批调度器复用既有 Child AgentRun ID、单次用量合并、取消传播和父级授权代理；多个子任务同时等待授权时按父工具调用顺序逐项展示，已在运行的兄弟任务可以继续，但暂停期间不启动新的排队子任务。
- **迁移边界**：服务端 AgentRun 的工具与子任务能力已经覆盖完整；正式 `plan` / `accept` / `bypass` 仍未切换所有权。下一阶段进入前端单一所有权切换及刷新、会话切换、停止和授权恢复的人工端到端验证。
- **验证结果**：新增 4 子任务压力用例，验证前三个并发、第四个排队、最大活动数始终为 3、四个结果和父工具消息顺序稳定、累计用量正确；AgentRun 定向回归 `37 passed, 13 subtests passed`，最终全量回归 `531 passed, 25 subtests passed`，Python 编译与 `git diff --check` 通过。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 16:32 · Codex

### 将顺序子任务迁入持久 Child AgentRun，打通授权、取消与重启复用

- **持久子任务协议**：将 `task` 以 `effect=delegation`、`idempotent=true`、`background=true` 加入服务端工具注册表，仅向 `plan` / `accept` / `bypass` 提供。每个父工具调用创建独立 AgentRun，并持久化 `parentAgentRunId`、`parentToolCallId` 与深度；子任务继承父任务模型、权限和允许工具，同时移除 `task` 与 `request_user_input`，禁止权限提升、孙级委派和子问卷。
- **单一执行与崩溃恢复**：父工具检查点先保存 Child AgentRun ID，再启动子任务；父任务或服务重启后按原 ID 恢复活动子任务或复用终态结果，不发起第二次子模型请求。子任务结果、轮次、工具统计和用量写回父工具结果，用量通过持久 `childUsageMerged` 标记只累计一次。
- **父级授权代理**：子任务在 `accept` 下遇到写入、删除、命令或编辑授权时，父 AgentRun 生成稳定代理授权 ID，并把安全的 action、path、diff 或 command 信息投影到原 `waiting_authorization` 协议。用户决定转发到原 Child AgentRun，父子任务均转入凭据恢复后继续，API Key 不进入任一运行记录。
- **取消传播**：取消父 AgentRun 会递归取消所有活动 Child AgentRun 及其模型轮次/命令；子任务失败或取消形成明确的父工具结果，不遗留独立后台执行。
- **迁移边界**：本阶段只实现确定性的顺序子任务，不切换正式 `plan` / `accept` / `bypass` 前端所有权。下一阶段补齐同一模型轮次多个 `task` 调用的有界并发和结果排序，再进行正式界面端到端切换。
- **验证结果**：新增权限筛选、父子元数据/工具继承、用量单次合并、子写入授权代理、父级取消传播及完成子任务重启复用回归；AgentRun/HTTP 定向回归 `91 passed, 19 subtests passed`，最终全量回归 `530 passed, 25 subtests passed`，Python 编译与 `git diff --check` 通过。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`tests/test_routes.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 16:03 · Codex

### 将直接写入与删除迁入持久 AgentRun，建立授权后执行与崩溃恢复闭环

- **共享文件变更服务**：将 `/api/tools/write_file` 和 `/api/tools/delete_file` 的路径校验、备份与变更逻辑抽成 `execute_write_file_tool` / `execute_delete_file_tool`，加入 `SERVER_TOOL_REGISTRY` 并声明为 `effect=file_mutation`、`idempotent=true`、`background=true`。原 HTTP 路由和 AgentRun 现在共用同一实现。
- **持久授权语义**：`read` / `plan` 不获得直接文件变更工具；`accept` 遇到写入或删除时生成稳定授权 ID，先持久路径、diff 预览和工具状态。批准只将执行记录标为 `authorized`，待凭据重新注入后才发生文件变更；拒绝直接补成工具结果且不触碰项目。`bypass` 可由后台直接执行。
- **写入恢复**：`write_file` 串行读取原内容、生成稳定备份、原子替换目标并验证写后内容。若服务在写入完成后、工具结果落盘前退出，原参数恢复会识别目标已是最终内容，返回 `replayed=true`，不会重写文件或生成第二份备份。
- **删除恢复**：`delete_file` 在移除目标前先按稳定操作 ID 落盘文件备份和删除收据；服务重启遇到已不存在的目标时，只有路径匹配的本次收据才会被认定为重放成功，从而区分“已删除”和“调用前就不存在”。文件备份保留原始字节，空目录也具有收据。
- **目录边界**：模型工具集本来就没有独立的建目录工具；写入服务按原语义创建父目录，其余目录操作由已迁移的受控命令承担。`/api/mkdir` 仍是文件选择器 UI 接口，没有错误混入 Agent 工具注册表。
- **迁移边界**：本阶段未切换正式前端的 `plan` / `accept` 执行所有权，子任务仍由浏览器编排；下一阶段聚焦子任务持久协议。
- **验证结果**：新增工具筛选、批准后延迟执行、拒绝零变更、HTTP 共享服务、写入不重复备份、删除收据重放、凭据不落盘、路径安全和并发回归；文件/AgentRun/安全定向回归 `227 passed, 16 subtests passed`，最终全量回归 `530 passed, 22 subtests passed`，Python 编译和 `git diff --check` 通过。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`tests/test_routes.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 15:46 · Codex

### 将项目记忆写入迁入持久 AgentRun，建立可安全恢复的幂等语义

- **共享记忆服务**：将原 `/api/tools/save_memory` 处理器内的独立写文件逻辑抽成 `execute_save_memory_tool`，并加入 `SERVER_TOOL_REGISTRY`，声明为 `effect=memory_write`、`idempotent=true`、`background=true`。HTTP 路由和 AgentRun 现在使用同一校验、项目绑定与写入实现。
- **原子写入与幂等重放**：记忆文件先写入同目录临时文件，再原子替换目标；目标的名称、描述、项目和正文与本次请求一致时，直接返回 `replayed=true`，不重写文件或刷新修改时间。这覆盖了“文件已替换、工具完成状态尚未落盘”的崩溃窗口。
- **AgentRun 权限与恢复**：`read` / `plan` 不获得项目记忆写入工具，`accept` / `bypass` 可由后台直接执行；工具参数、状态、结果和重放事件随 AgentRun 持久化，API Key 仍仅存内存。服务重启遇到 `running` 记忆写入时可按原参数恢复，已产生的相同文件被识别为原执行结果。
- **迁移边界**：本阶段未切换正式前端的 `plan` / `accept` 执行所有权，也未改动项目文件直接写入/删除和子任务协议；下一阶段聚焦直接写入/删除。
- **验证结果**：新增注册表权限筛选、真实 HTTP 共享服务、无浏览器 AgentRun 写入、崩溃后幂等重放、文件修改时间不变及凭据不落盘回归；记忆/HTTP/AgentRun 定向回归 `266 passed, 16 subtests passed`，最终全量回归 `524 passed, 18 subtests passed`，Python 编译通过。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`tests/test_routes.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 15:34 · Codex

### 建立 AgentRun 命令授权、增量输出、取消和不可重放协议

- **共享命令服务**：将原 `/api/tools/run_command` 的安全校验与 PowerShell 执行抽成 `execute_run_command_tool` 并加入 `SERVER_TOOL_REGISTRY`，声明为 `effect=command`、`idempotent=false`、`background=true`；HTTP 路由和 AgentRun 共用同一实现，保留危险命令拦截，并新增受服务端上限约束的超时参数、准确的原生命令退出码和 stdout/stderr 截断标记。
- **权限与授权**：`read` / `plan` 不会获得命令工具；`accept` 遇到命令后生成稳定授权 ID 并进入 `waiting_authorization`，批准只持久化为 `authorized`、不会在决定提交请求中立即执行，待凭据恢复后才启动一次；拒绝不创建进程，直接补成原工具调用结果。`bypass` 可按现有语义直接执行，但正式前端尚未切换所有权。
- **运行检查点**：活动命令以独立进程运行，后台读取 stdout/stderr，并持续将最近 `20,000` 字符、累计字符数与最后输出时间写入 AgentRun 工具检查点；公开快照可观察进度，最终结果继续经过提示注入扫描并保留退出码、超时与截断状态。
- **取消与恢复安全**：停止 AgentRun 会终止当前 PowerShell 及其进程树，并把工具执行标为已取消。若服务在命令已启动但完成状态尚未落盘时退出，恢复层会把 `running` 检查点转换为 `interrupted + unknownState + notReplayed` 的失败工具结果；即使命令可能已经产生外部效果，也不会自动执行第二次。
- **迁移边界**：本阶段没有改动正式前端的执行所有权和命令授权界面；下一阶段处理直接写入/删除与 `save_memory`，之后再迁移子任务。复核工具策略时补记 `save_memory`，避免未来切换 `plan` / `accept` 时静默丢失现有能力。
- **验证结果**：新增权限筛选、批准后单次执行、拒绝零进程、运行输出落盘、取消进程、重启不重放、HTTP 共享服务、超时和非零退出码回归；命令/安全/恢复/并发定向测试 `202 passed, 6 subtests passed`，AgentRun 定向测试 `24 passed, 2 subtests passed`。首次全量运行因本地模拟上游一次不完整 JSON 读取出现原编辑用例偶发失败，单例及 AgentRun 全集复跑通过，随后完整回归 `520 passed, 14 subtests passed`，Python 编译和 `git diff --check` 通过。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`tests/test_routes.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 15:12 · Codex

### 将网络与 Skills 只读能力迁入持久 AgentRun

- **共享工具服务**：将 `web_fetch`、`use_skill` 和 `read_skill_resource` 从 HTTP Handler 抽成可直接调用的服务函数，并加入 `SERVER_TOOL_REGISTRY`，统一声明为 `effect=read`、`idempotent=true`、`background=true`；现有 `/api/tools/*` 路由与 AgentRun 现在共用同一实现，不再存在浏览器接口和后台任务两套执行逻辑。
- **后台闭环**：AgentRun 可按任务允许的工具集合连续完成“模型 → 加载 Skill → 读取 Skill 资源 → 抓取网页 → 模型”，工具开始、结果和调用指纹沿用原持久检查点；浏览器完全不轮询时任务仍可完成，服务重启后的已完成结果继续遵循通用回放协议。
- **迁移边界**：本阶段没有扩大正式“只读分析”入口的产品工具集合，也没有切换 `plan` / `accept` 的执行所有权；计划/接受编辑仍由浏览器编排，下一阶段处理命令的持久输出、取消和不可重放边界，然后再迁移直接写入/删除和子任务。
- **Skill 资源安全**：`read_skill_resource` 现在同时校验 Skill 名称、资源一级目录和解析后的真实路径，只允许读取 Skill 包中的 `scripts/`、`references/`、`assets/`，拒绝通过 Skill 名称、`..` 或目录回退读取包外文件；Skill 根目录不存在时统一返回可预期错误。
- **凭据与回归**：新增真实 HTTP 注册表一致性、三工具无浏览器 AgentRun、多工具结果持久化、API Key 不落盘及 Skill 路径穿越回归；Python 编译、JavaScript 所有权边界测试和 `git diff --check` 通过，定向回归 `111 passed, 10 subtests passed` 与 `71 passed`，最终全量回归 `512 passed, 12 subtests passed`。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`tests/test_routes.py`、`tests/test_p2_coverage.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 07:51 · Codex

### 将持久编辑授权接入正式审查卡片：刷新恢复、会话隔离与原任务续跑

- **正式界面投影**：服务端 AgentRun 进入 `waiting_authorization` 后，前端会以稳定授权 ID 将 `pendingAuthorization` 投影为现有 diff 审查卡片和授权面板；文件路径、增删统计与“查看”定位沿用原交互，服务端管理的提案从首次绘制起就显示为等待授权，不会短暂出现可绕过服务端的本地应用按钮。
- **决定提交与续跑**：授权面板支持异步提交服务端 `approved` / `rejected` 决定；提交成功后同步更新提案卡片状态，清除待确认项，并让当前 `runServerAgentLoop()` 继续同一个 AgentRun。原有浏览器本地授权仍走原 Promise 结果，批量允许/全部拒绝可同时处理两类请求。
- **刷新恢复**：会话检查点新增可序列化 `authorizationRequest`，保存稳定授权 ID、AgentRun、工具调用、提案卡片和选择状态，不保存 Promise、AbortSignal 等内存对象。页面刷新后即使原等待 Promise 已不存在，用户仍可直接提交决定；前端随后把检查点转为 `resuming` 并恢复同一个 AgentRun，不伪造或重复执行工具结果。
- **会话与取消边界**：恢复授权按 `sessionId` 隔离，只在当前会话展示对应卡片；切换会话不取消后台等待。停止任务会移除授权项并把提案标为未应用，网络提交期间禁用重复操作；服务端决定已经成功时，即使会话保存暂时失败也不会阻塞原任务继续。
- **所有权审计**：确认 `plan` / `accept` 当前还依赖网络、Skills、命令、直接写入/删除和子任务，而服务端尚未覆盖这些协议。本阶段明确保留这两档的浏览器执行所有权，只完成持久授权界面；不通过缩减模型工具列表提前切换，避免已有核心能力静默回退。
- **验证结果**：新增服务端授权客户端请求体、持久卡片/恢复路径和所有权边界回归；会话持久化、AgentRun、P0 稳定性及子任务定向回归 `87 passed`，JavaScript 语法与 `git diff --check` 通过，最终全量回归 `509 passed, 6 subtests passed`。

**涉及文件**：`app.js`、`tests/test_frontend_modules.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 07:27 · Codex

### 建立服务端编辑授权与幂等写入协议：持久等待、冲突保护和崩溃回放

- **编辑服务统一**：将原 Handler 内的模糊片段定位、提案构建和应用逻辑抽成可复用服务，`/api/tools/propose_edit`、`/api/tools/apply_edit` 与 AgentRun 共用同一实现；`propose_edit` 正式加入工具注册表并声明为 `effect=proposal`、`idempotent=true`、`background=false`。
- **权限档位语义**：AgentRun 创建协议新增 `permissionProfile`；`read` 不获得编辑工具，`plan` 只接收可审查提案，`accept` 在提案后进入新的 `waiting_authorization`，`bypass` 通过同一受保护应用服务执行。正式界面的计划/接受编辑档位本阶段仍由浏览器编排，避免在授权卡片接入前产生双重执行或命令能力回退。
- **持久授权决定**：运行记录和公开快照新增 `pendingAuthorization`，以 AgentRun、工具调用和提案指纹生成稳定授权 ID；新增 `POST /api/agent/runs/{id}/authorization`，只接受匹配请求的 `approved` / `rejected`。决定会补成原 `tool_call_id` 的正式工具结果，再进入 `waiting_credentials` 恢复同一任务。
- **幂等与并发保护**：编辑提案记录原文件内容哈希、mtime 和目标内容哈希；批准时在进程内串行核对状态，先备份，再通过同目录临时文件原子替换并做写后校验。文件在等待期被其他任务修改时返回冲突而不覆盖；若进程在写入后、完成状态落盘前退出，`accept` 的重复批准或 `bypass` 的自动恢复都会复用持久提案并按最终内容哈希识别为回放，不重复写入或生成第二份备份。
- **恢复与凭据边界**：`waiting_authorization` 与问卷一样可跨服务重启保持可操作，等待时清空内存 Key；公开授权快照不暴露完整新文件内容和内部哈希，持久记录不包含 API Key。浏览器运行时客户端已支持提交授权决定和识别授权等待状态，为下一阶段正式界面投影做好协议准备。
- **文档与测试**：同步更新 README、迁移计划、架构记忆和 TODO，将下一步收敛为授权卡片投影及 `plan` / `accept` 单一执行所有权切换。新增批准、拒绝、计划只提案、陈旧文件冲突、服务重启、`accept` / `bypass` 写后崩溃回放和真实 HTTP 端点回归；Python/JavaScript 语法检查、`git diff --check` 通过，最终全量回归 `507 passed, 6 subtests passed`。

**涉及文件**：`server.py`、`agent-runtime.js`、`app.js`、`tests/test_agent_runtime.py`、`tests/test_frontend_modules.py`、`tests/test_routes.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 07:02 · Codex

### 完成只读 AgentRun 的持久问卷闭环：服务端暂停、刷新恢复与原任务续跑

- **暂停型交互协议**：服务端工具注册表新增 `request_user_input`，明确声明为 `effect=interaction`、`idempotent=true`、`background=false`，不会进入普通后台工具执行器；AgentRun 新增 `waiting_user_input` 状态和 `pendingInput` 快照，模型提出问卷后先持久化问题、工具调用和事件，再暂停运行。
- **回答校验与续跑**：新增 `POST /api/agent/runs/{id}/input`，按持久问题逐项校验问题 ID、单选/多选值、自定义答案、必填项和取消状态；合法答案补成原 `tool_call_id` 的正式工具结果，非法或过期提交不会改变运行状态。回答完成后任务进入 `waiting_credentials`，由前端重新注入仅存内存的 Key 并继续下一轮模型调用。
- **重启与凭据边界**：服务重启后 `waiting_user_input` 保持可回答，不会被错误转换为普通模型恢复；活动模型/工具任务仍按原协议进入 `waiting_credentials`。等待问卷时主动清空 Key，AgentRun 文件、事件和公开快照均不包含凭据。
- **正式界面接入**：“只读分析”现在向模型暴露四个只读工具和问卷控制工具；前端复用现有逐题问卷面板，将稳定的 `requestId`、`agentRunId` 和进度写入会话检查点。页面刷新、切换会话或服务重启后可继续回答；提交成功后恢复同一个 AgentRun，不在浏览器本地伪造或重复执行工具结果。
- **迁移边界保持**：计划、接受编辑和自动模式继续使用浏览器 Agent 循环；写入、删除、命令、网络、权限确认和子任务没有提前迁入服务端。下一阶段聚焦副作用权限决定和写入幂等协议。
- **验证结果**：新增持久问卷、非法答案拒绝、服务重启恢复、真实 HTTP 提交续跑和前端恢复路径回归；Python/JavaScript 语法检查、`git diff --check` 通过，相关定向回归 `235 passed, 4 subtests passed`，最终全量回归 `499 passed, 6 subtests passed`。

**涉及文件**：`server.py`、`agent-runtime.js`、`app.js`、`tests/test_agent_runtime.py`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`tests/test_routes.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 06:25 · Codex

### 将只读 AgentRun 接入正式界面：单一执行所有权、流式投影与持久恢复

- **显式只读入口**：权限选择器新增“只读分析 / Read only”，严格只暴露 `list_files`、`read_file`、`search_files`、`glob_files` 四个无副作用工具；该档位将整次任务交给服务端 AgentRun，计划、接受编辑和自动模式继续使用原浏览器 `runAgentLoop()`，不做静默降级，避免同一工具调用被前后端重复消费。
- **任务客户端协议**：扩展 `agent-runtime.js`，补齐 AgentRun 创建、游标长轮询、服务重启凭据恢复和父任务取消；事件处理串行完成后才推进游标，网络抖动继续使用有界退避并在原状态栏展示重连状态。
- **保持 SSE 流畅度**：服务端每个模型轮次产生 `model_started` 后，前端只附着该轮已有的 `runtimeRunId` 并复用现有 SSE 解析/渲染，不额外请求模型；若短期子运行时已过期，则由持久 `model_completed` 事件回填完整思考、回答、工具调用和用量。
- **持久事件投影**：模型和工具事件按序映射为正式会话消息，以 `agentRunId + 事件类型 + seq` 去重；会话检查点新增 `executionOwner`、`agentRunId`、`agentEventCursor` 和活动子运行 ID，事件游标与对应消息快照进入同一有序保存链，异常退出后不会出现游标领先于消息的缺口。持久 `model_completed` 回填会拆分思考/回答，并以服务端 `completedAt` 补齐模型消息时间戳。
- **恢复与会话隔离**：只读任务不再生成浏览器侧恢复提示，刷新后直接续接 AgentRun；服务重启进入 `waiting_credentials` 时由前端重新注入内存态 Key。切换会话和 `beforeunload` 保存不再清空活动检查点，后台任务完成时也不会误用前台会话标题。
- **统一取消语义**：停止任务会先取消 AgentRun 父任务，再取消当前子模型运行并中止本地轮询；服务端终态取消继续保持幂等，页面切换与新建会话不触发取消。
- **文档同步**：更新项目 README、服务端循环迁移计划、架构记忆和 TODO，将下一阶段收敛为服务端权限/问卷等待协议、写入工具幂等迁移和子任务调度。
- **验证结果**：`app.js` 与 `agent-runtime.js` JavaScript 语法检查、AgentRun/模型运行时/会话恢复定向测试和 `git diff --check` 通过；新增客户端游标顺序、显式所有权、检查点恢复、持久消息时间戳与父子取消回归，最终全量回归 `495 passed, 6 subtests passed`。

**涉及文件**：`agent-runtime.js`、`app.js`、`index.html`、`tests/test_frontend_modules.py`、`tests/test_p0_stability.py`、`tests/test_subagent_frontend.py`、`README.md`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 06:02 · Codex

### 建立持久化只读 AgentRun：服务端可独立完成多轮模型与工具循环

- **任务级状态机**：新增独立 `/api/agent/runs` 运行层，持久化模型选项、消息、轮次、累计用量、事件游标、待处理工具和最终结果；状态覆盖 `model`、`tools`、`waiting_credentials`、`completed`、`failed`、`cancelled`，模型轮次继续复用原有流式运行时，不改变正式前端 SSE 链路。
- **只读闭环执行**：服务端注册表补全四个只读工具的函数定义，AgentRun 只会向模型暴露同时满足 `effect=read`、`idempotent=true`、`background=true` 的 `list_files`、`read_file`、`search_files`、`glob_files`；已验证在浏览器不轮询的情况下自动完成两轮“模型 → 读文件 → 模型”。
- **持久化恢复与幂等**：工具执行前记录调用 ID、规范化参数和 SHA-256 指纹，执行完成后先落盘结果再补模型工具消息；服务重启时非终态任务转为 `waiting_credentials`，恢复后复用已完成工具结果且不会重复执行，同一调用 ID 在后续轮次重现时仍补齐协议消息。
- **接口与取消语义**：新增创建、游标查询/长轮询、凭据恢复和取消端点；活动 AgentRun 暴露当前子模型运行 ID 供后续流式投影，取消会同步关闭当前模型请求，终态取消保持幂等，模型轮次上限默认 `12`、最高 `50`。
- **凭据边界**：API Key 仅存在于运行内存并在所有终态清空，不进入快照、事件或 `data/agent-runs/*.json`；显式 Base URL 禁止携带用户名/密码，模型请求选项中顶层或嵌套的凭据字段会直接拒绝，错误文本会按当前 Key 脱敏。
- **迁移边界保持**：正式 `app.js` 尚未切换到 AgentRun，原有会话切换、后台输出、刷新续接、权限与问卷行为保持不变；下一步先让会话检查点保存 `agentRunId` 并建立前端事件投影/单一执行所有权，再迁移有副作用工具。
- **验证结果**：新增 `7` 项 AgentRun 定向测试，覆盖无浏览器续跑、HTTP 生命周期、重启恢复、幂等复用、重复调用 ID、主动取消、轮次上限和凭据拒绝；运行时/路由/会话恢复/并发/安全定向回归 `183 passed, 4 subtests passed`，最终全量回归 `488 passed, 6 subtests passed`，Python/JavaScript 语法与 `git diff --check` 通过。

**涉及文件**：`server.py`、`tests/test_agent_runtime.py`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`README.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 05:16 · Codex

### 推进服务端 Agent 循环下沉：结构化轮次结果与只读工具注册表

- **确认真实架构边界**：复核模型运行时、恢复检查点和前端 `runAgentLoop()` 后确认，v0.5.4 服务端只持有单次上游模型流；浏览器刷新可续接当前 SSE，但模型返回工具调用后仍必须由浏览器执行工具并发起下一轮，因此浏览器完全关闭后的多轮续跑尚未成立。
- **结构化模型轮次结果**：服务端在保留原始 SSE 事件和游标重放协议的同时，增量聚合 `content`、`reasoning`、`tool_calls`、`finish_reason` 与 `usage`；支持 OpenAI 兼容流中的分片函数名/参数、完整 `message.tool_calls` 以及 Anthropic/Responses 风格文本增量，运行快照新增稳定的 `result` 字段。
- **流式与凭据不变量**：聚合发生在原有事件追加的同一临界区，不增加整轮缓冲、网络等待或额外上游请求；结束后仍立即清空 API Key 和请求 Payload，运行快照只包含模型输出与工具参数，原有前端无需切换即可继续消费 `events`。
- **首批共享工具注册表**：将 `list_files`、`read_file`、`search_files`、`glob_files` 从 HTTP Handler 抽成可直接调用的服务函数，集中注册到 `SERVER_TOOL_REGISTRY`，并声明 `effect=read`、`idempotent=true`、`background=true`；现有 `/api/tools/*` 路由与未来服务端 AgentRun 现已共用同一实现。
- **迁移路线与架构记忆**：新增 `docs/SERVER_AGENT_LOOP_PLAN.md`，明确当前/目标所有权、五阶段迁移顺序、权限与幂等约束及阶段 1 API；重写过期的 `data/memory/code-architecture.md`，TODO 更新为下一步建立可消费只读注册表的持久化 `AgentRun` 状态机。
- **当前阶段边界**：本次完成的是安全下沉所需的协议和首批工具执行层，没有提前宣称浏览器关闭后已能完整续跑；写入、命令、问卷和子任务仍由前端编排，待持久化状态机和副作用幂等协议完成后迁移。
- **验证结果**：模型运行时定向测试 `3 passed`，运行时/会话恢复/并发/安全回归 `119 passed`，工具路由与注册表一致性 `48 passed, 4 subtests passed`；最终全量回归 `476 passed, 6 subtests passed`，JavaScript 语法、Python 编译和 `git diff --check` 通过。用户重启实际 Code 服务后完成 `list_files`、`read_file`、`search_files`、`glob_files` 四项只读界面验收，结果正常且未产生意外写入。

**涉及文件**：`server.py`、`tests/test_model_runtime.py`、`tests/test_routes.py`、`docs/SERVER_AGENT_LOOP_PLAN.md`、`data/memory/code-architecture.md`、`README.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 04:53 · Codex

### 完成 Code v0.5.4 GitHub Release 发布

- **代码与标签**：发布提交 `8c84237f0e18003a8f50b8bfe8c622dce2ca547d` 已推送到 `master`，注解标签 `v0.5.4` 指向同一提交；仓库远端同步改为正式地址 `https://github.com/fhy-A/Code.git`。
- **Release 状态**：已创建 [Code v0.5.4 — 从 Agent Lite 到 Code](https://github.com/fhy-A/Code/releases/tag/v0.5.4)，状态为公开、非草稿、非预发布，并成为仓库 Latest Release；本次只发布 Code 品牌资产，不提供 AgentLite 命名的兼容包。
- **线上资产核验**：唯一资产 `Code-v0.5.4.exe` 上传状态为 `uploaded`，大小 `30,859,501` bytes；GitHub 返回摘要 `sha256:be333df1187d30d61111f2edadf2948bace16c2cd611b1ea7433b07a05623ae4`，与本地构建产物逐字一致。
- **发布内容核验**：线上正文已确认包含 `24` 个提交、`182` 个文件、`473 passed, 2 subtests passed`、完整 SHA-256 和八部分详细更新内容；根 README 已作为新的项目级入口随发布提交上线。
- **标签保持不变**：本条为发布完成后的记录，只追加到 `master`，不移动或重写已经公开的 `v0.5.4` 标签。

**涉及文件**：`CHANGELOG.md`

---

## 2026-07-18 04:39 · Codex

### 发布 Code v0.5.4：完成品牌迁移与运行时、会话和流式界面重构

- **正式版本迁移**：版本号与 Windows 文件元数据统一升级到 `0.5.4`，发布文件正式使用 `Code-v0.5.4.exe`；README、构建输出和 GitHub Release 文档同步切换到 Code 品牌，不再发布 AgentLite 命名的过渡包。
- **大版本说明**：新增 `docs/releases/v0.5.4.md`，按品牌与欢迎页、后台任务续接、JSONL 会话存储、SSE 投影、问卷与文件预览、Skills/Token 优化、前端模块化和配套平台八个部分整理 `v0.5.3..v0.5.4` 的 24 个提交、182 个文件变更，并单列升级提示、安装步骤、构建校验与文件摘要。
- **项目级 README 重写**：根 README 改为 Code 的正式项目入口，补全产品定位、核心能力、运行架构、EXE/源码启动、模型与项目配置、数据隐私、后台任务与 JSONL 会话机制、目录结构、开发验证、发布检查和当前边界；品牌图按系统主题自动选择黑白 SVG，并链接版本说明、迁移文档、架构计划与路线清单。
- **更新资产选择**：当前版本检查只接受与 Release 标签精确对应的 `Code-v{version}.exe`，避免同一 Release 中其他 `.exe` 资产被误选；构建脚本在 PyInstaller 失败时立即返回失败，并输出实际版本化产物路径。
- **验证与发布产物**：定向回归 `165 passed`，全量回归 `473 passed, 2 subtests passed`；`app.js`、`agent-runtime.js` 及拆分模块 JavaScript 语法检查、核心 Python 编译、SVG XML 解析和 `git diff --check` 通过。使用 Python `3.12.10` 与 PyInstaller `6.21.0` 构建 Windows x64 单文件 `dist/Code-v0.5.4.exe`，大小 `30,859,501` bytes（`29.43 MiB`），文件/产品版本均为 `0.5.4`，SHA-256 为 `BE333DF1187D30D61111F2EDADF2948BACE16C2CD611B1EA7433B07A05623AE4`；签名状态为 `NotSigned`。

**涉及文件**：`VERSION`、`file_version_info.txt`、`README.md`、`server.py`、`build_exe.py`、`tests/test_server.py`、`docs/releases/v0.5.4.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 04:21 · Codex

### 重构中转站 Code 专题页并规范定制部署包

- **专题页正式重构**：将确认后的独立 HTML 草稿迁入 `new-api-source` 正式 React 路由，改为面向用户的四段式产品页面；接入 Code 黑白标志、深浅主题真实界面截图、响应式布局和中英文国际化，统一修正顶部 `Code` 品牌被翻译为“代码”的问题。
- **下载与平台连接**：首屏和页尾下载按钮通过 GitHub Release API 自动选择最新 `.exe`，失败时回退到最新 Release 页面；源码按钮指向 Code GitHub 仓库，页面不再展示容易过期的固定版本号。
- **认证类型修复**：删除 `/code/connect` 对已不存在的 `auth.isLoading` 字段的判断；认证用户继续由 Zustand 从 `localStorage` 同步恢复，未登录跳转规则保持不变，TypeScript 全量类型检查恢复通过。
- **部署产物规范化**：统一由 `new-api-source/build-deploy.ps1` 输出到工作区根目录 `output/`，每次打包先清理生成目录；定制包只保留本地二进制对应的 `docker-compose.deploy.yml`，不再混入会拉取公开镜像的普通 compose 文件。
- **部署配置与说明更新**：Compose 新增加载 `.env` 和日志目录参数，修复 systemd 模板中的无效行尾注释、服务名和默认路径；新增中文 `DEPLOYMENT.md`，覆盖 Docker、systemd、HTTPS/SSE、更新回滚与排查流程，并由打包脚本作为正式源文件复制。
- **交付与验证**：正式前端构建、Code 页面定向 lint、TypeScript 类型检查、国际化 JSON 解析、Compose 结构检查和 PowerShell 脚本语法检查通过；最新 Linux amd64 部署包为 `output/new-api-dev-20260718.zip`，SHA-256 为 `46164666630F36C662C39DF525B5AB677B58B51BB0BA1F96E5A502F4B9CDCE49`。

**涉及仓库/文件**：`new-api-source/web/default/src/features/code/*`、`new-api-source/web/default/src/i18n/locales/*`、`new-api-source/build-deploy.ps1`、`new-api-source/docker-compose.deploy.yml`、`new-api-source/new-api.service`、`new-api-source/DEPLOYMENT.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 03:16 · Codex

### 新增项目 Python 统计脚本

- **新增脚本**：创建 `tools/project_summary.py`，递归统计项目内 Python 文件数量、非空非注释代码行数和 AST 函数数量，并忽略 `.git`、`.venv`、`build`、`dist`、`data` 目录。
- **输出报告**：运行脚本生成 `data/project-summary.md`，记录当前统计结果：Python 文件 `31` 个、代码行 `9515` 行、函数 `763` 个。
- **验证结果**：执行 `python tools/project_summary.py` 成功，退出码 `0`，报告文件已写入。

**改动文件**：`tools/project_summary.py`、`data/project-summary.md`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 02:04 · Codex

### 让欢迎页刷新保持前台视图且不影响后台会话

- **根因修复**：新增独立的 `code-foreground-view` 前台视图标记，区分用户最后停留在欢迎页还是某个会话；启动时只有前台标记为会话页才恢复 `code-last-session`，欢迎页刷新不再被最近会话覆盖。
- **竞态隔离**：为前台 `loadSession()` 增加独立导航序列；进入欢迎页或删除当前会话会使尚未完成的旧前台加载失效，避免迟到响应重新选中会话。序列更新放在原有 `300ms` 防连点判断之后，不改变快速切换行为。
- **后台链路保持不变**：没有修改 `resumePersistedRuns()`、`resumePersistedSessionRun()`、会话运行缓存、消息队列、`AbortController`、SSE 续接或任务检查点；切换会话和新建会话只改变前台投影，正在输出的其他会话继续运行。
- **验证结果**：使用同一有效 `last-session` 实测：前台标记为 `welcome` 时刷新保持欢迎页且无活动会话行，标记为 `session` 时继续恢复原会话；页面无异常。并发定向测试与 `app.js` 语法检查通过，全量回归 `477 passed, 2 subtests passed`。

**改动文件**：`app.js`、`tests/test_concurrency.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 01:37 · Codex

### 将命令光标品牌动效接入正式欢迎页

- **正式接入而非仅保留预览**：移除欢迎页原有的静态几何 Logo 展台，将无字体依赖的 `Code` SVG 字标、标语与真实输入框组成同一套命令光标接力；四个字母按节奏逐个生成，光标随后扫出标语并移动到正式 `textarea`，不再只存在于 `design/` 演示页面。
- **真实输入接管**：末段路径根据字标、标语和输入框的实时 `getBoundingClientRect()` 计算，移动 caret 精确落到输入框 `17px / 15px` 的内容起点并保持 `240ms`；落点期间隐藏原生 caret，输入框先取得焦点，再无缝切换为原生 caret，动画结束后无需点击即可直接输入。用户提前点击、聚焦或输入时会立即结束装饰动画，不阻塞操作。
- **排版与响应式修正**：品牌名和标语改为同一行按可见底边对齐，桌面字标保持 `130 × 54px`，窄屏缩为 `112 × 47px`；去除窄屏跳过光标移动的例外，最终移动时长继续按实际距离限制在 `440–600ms`，不同窗口大小均落到真实输入位置。
- **主题与无障碍兼容**：字标、命令提示符、移动 caret 和原生 caret 全部继承 `--text`，标语继承主题弱化文字色，浅色与深色模式自动反色；`prefers-reduced-motion` 下直接显示最终品牌状态，不播放位移动画。
- **验证结果**：浅色正式页实测移动 caret 与输入内容起点坐标完全一致，落点时输入框已获得焦点；深色主题字标与标语正确反色。`app.js` 语法、前端定向测试、`git diff --check` 通过，全量回归 `476 passed, 2 subtests passed`。

**改动文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-18 01:06 · Codex

### 定稿无字体依赖的 Inter Tight 轮廓字标

- **字形定稿**：在 Segoe UI、Inter Tight、Space Grotesk、Sora 与 IBM Plex Sans 五组真实字体对比后，选择 `Inter Tight 800`；按确认后的 `54px` 字号与 `-0.035em` 字距将 `C / o / d / e` 分别转换为 SVG 路径，保留逐字生成所需的独立字母边界。
- **运行时零字体依赖**：新增 `assets/code-wordmark.svg`，正式欢迎页通过内联 `currentColor` SVG 渲染品牌名，不再等待 Web Font、依赖系统字体或因不同设备字形回退产生宽度变化；浅色与深色主题继续自动继承文字色。
- **动效一致性**：命令光标品牌预览改用同一组字母路径，重新校准四次光标跳位、标语底边与整体宽度；标语到输入框的末段移动按实际距离自适应为 `440–600ms`，桌面与窄屏继续使用各自的响应式节奏。
- **验证结果**：`app.js` JavaScript 语法检查、SVG/页面视觉检查与 `git diff --check` 通过；全量回归 `476 passed, 2 subtests passed`。

**改动文件**：`app.js`、`styles.css`、`assets/code-wordmark.svg`、`design/code-welcome-command-brand/preview.html`、`design/code-wordmark-fonts/preview.html`、`design/code-custom-wordmarks/preview.html`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 23:07 · Codex

### 将欢迎页重构为极简品牌入口

- **内容收敛**：移除“理解项目 / 修复问题 / 实现功能”三张任务模板、工作区状态、操作提示及对应的点击填充逻辑和 i18n 文案；欢迎页只保留 Logo、`Code` 品牌名、一句“把想法变成可运行的代码”标语与现有输入框。
- **品牌化几何**：在正式双圆 Logo 后使用两个低对比度完整圆和一条中心轴展示构造关系，不引入新颜色、插画或额外信息卡；浅色/深色主题继续使用自动黑白反色。
- **布局调整**：品牌区改为居中纵向布局，输入框收敛为最大 `680px`、`16px` 圆角和轻量阴影；桌面保持充足留白，`640px` 窄屏缩小构造图并保持输入框完整可用。
- **验证结果**：无头 Chrome 在 `1400×900` 和 `640×800` 下确认页面仅包含一组品牌信息和输入框，无任务模板、横向溢出或遮挡；全量回归 `471 passed`，`app.js` / `agent-runtime.js` JavaScript 语法与 `git diff --check` 通过。

**改动文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 22:47 · Codex

### 定稿双圆对话环 Logo，并支持主题自动反色

- **几何标志定稿**：正式 Logo 改为纵向同轴的两个等半径圆，经中线裁切后仅保留上圆右半和下圆左半；采用 `160 × 160` 母版、`R40` 半径、`14` 环宽、`54` 中心距和 `26` 交叠量，不再包含自由曲线、渐变或装饰元素。
- **黑白主题适配**：侧栏与欢迎页使用内联 SVG 的 `currentColor`，新增 `--brand-mark` 主题变量；浅色主题固定为纯黑 `#000000`，深色主题固定为纯白 `#FFFFFF`，跟随系统时复用现有主题监听自动切换。
- **品牌资产统一**：新增黑白 SVG/PNG 导出文件，重写图标导出脚本；系统级 PNG/ICO 使用白色标志与黑色容器，保持浅色和深色桌面背景下的可见性；针对 `16–24px` 做独立光学校正，将圆心各向内收 `7` 个母版单位并把环宽从 `14` 调整为 `13`，让最小尺寸保留接近 `2px` 的中央负空间，避免两段 C 被抗锯齿粘连；PyInstaller 同步打包 `assets/`，favicon 增加版本标记以绕过浏览器旧图标缓存。
- **验证结果**：全量回归 `471 passed`；`app.js` / `agent-runtime.js` JavaScript 语法、导出脚本 Python 语法、SVG 解析和 `git diff --check` 通过；无头 Chrome 实测浅色侧栏/欢迎页显示黑标、深色侧栏显示白标。

**改动文件**：`index.html`、`app.js`、`styles.css`、`assets/code-logo*.svg`、`assets/code-logo*.png`、`assets/code-icon.png`、`code-icon.png`、`code-icon.ico`、`build_exe.py`、`design/logo-concepts/export_selected_logo.py`、`design/code-logo-stacked-circles/*`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 20:46 · Codex

### 重新设计 Code 品牌 Logo 与欢迎页

- **全新品牌标志**：以蓝色圆角工作区为底，使用白色 `C` 形循环表达 Code / 当前工作区，并用浅蓝命令提示符表达“从理解到执行”；替换侧栏旧 A 图形及应用 SVG、PNG、ICO 资源。
- **资源链统一**：新增根目录与 `assets/` 下的 PNG，重写可重复执行的图标导出脚本，同步更新 favicon、托盘/EXE ICO、系统通知 PNG 和 PyInstaller 资源清单；品牌方向预览新增 `07 · Code Workspace · Selected`。
- **欢迎页重构**：空会话页改为开放式品牌布局，展示“本地工作区已就绪”、核心主张和产品能力说明；新增“理解项目 / 修复问题 / 实现功能”三个快捷任务入口，点击只填充输入框并触发原有输入状态更新，不会自动发送。
- **响应式与主题**：欢迎区和输入框统一为最大 `720px` 内容列，浅色/深色主题使用相同层级；在窄屏切换为单列快捷入口，并保留键盘焦点、无横向溢出和可滚动能力。
- **真实页面验证**：无头 Chrome 在 `1400×900` 下确认欢迎区宽 `720px`、快捷入口 `3` 个且提示词正确写入；在 `640×800` 下确认单列布局、页面和工作区均无溢出；PNG、SVG、ICO 三类资源通过 `127.0.0.1:3010` 返回 `200`。
- **测试结果**：前端定向测试 `14 passed`，全量 `476 passed, 2 subtests passed`；JavaScript/Python 语法检查与 `git diff --check` 通过。

**改动文件**：`app.js`、`index.html`、`styles.css`、`assets/code-logo.svg`、`assets/code-icon.png`、`code-icon.png`、`code-icon.ico`、`build_exe.py`、`design/logo-concepts/*`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 20:29 · Codex

### 将模型名分隔线延伸到会话内容列右侧

- 将模型名伪元素从固定 `24px` 短线改为 `flex: 1 1 auto` 弹性填充，并保留 `24px` 最小宽度、`1px` 高度和原有低对比度。
- 分隔线只占满 `.msg` 会话内容列，不会越过消息宽度延伸到侧栏或整个视口；模型名较长时会自动压缩剩余线段。
- 无头 Chrome 在 `1400px` 视口实测消息列与模型名行宽均为 `760px`，`deepseek-v4-pro` 后的分隔线计算宽度约 `647px`，正确抵达内容列右缘。
- 定向测试 `13 passed`，全量 `475 passed, 2 subtests passed`；JavaScript 语法检查和 `git diff --check` 通过。

**改动文件**：`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 20:23 · Codex

### 优化最终回答模型名的分隔样式

- **节标题化**：模型名调整为 `12px / 1.4 / 600` 的轻量节标题，使用主文字与弱化色混合后的中等对比度，并增加细微字距，使其比正文更紧凑但仍清晰可辨。
- **短线分隔**：模型名右侧增加 `24px × 1px` 的低对比度短线，不使用胶囊、背景或额外文案；它只强化“最终回答从这里开始”的含义，不改变思考摘要和正文的统一排版。
- **显示边界**：短线仅跟随非空的最终回答模型名显示；pending 阶段的隐藏模型名和无标题的思考块均不会产生装饰节点。
- **真实页面验证**：无头 Chrome 在浅色、深色环境检查计算样式与实际布局，确认模型名仅出现 `1` 次、思考块角色节点为 `0`，短线尺寸、间距和对比度符合预期。
- **测试结果**：定向测试 `13 passed`；全量测试首次受 Windows 临时文件锁竞争影响出现 `1` 个无关并发用例失败，单独复跑通过，随后全量复跑为 `475 passed, 2 subtests passed`；JavaScript 语法检查和 `git diff --check` 通过。

**改动文件**：`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 20:15 · Codex

### 统一思考摘要与最终回答样式，仅用模型名分隔

- **正文样式统一**：将思考摘要从弱化的 `13.5px / 1.72 / muted` 调整为与未分类流、最终回答完全一致的 `14.5px / 1.76 / text`，保留思考摘要的独立分段结构和 `.65em` 段间距。
- **唯一分隔标记**：思考块继续不显示“思考过程”标题和模型名；只有最终回答显示模型名，因此流内容从 `pending` 归类为思考或回答时不会再发生字体、字号、行高或颜色跳变。
- **真实页面验证**：无头 Chrome 直接加载 `127.0.0.1:3010`，确认 pending、thinking、final 三种投影的计算样式均为 `14.5px`、`25.52px` 行高、相同字体/字重/主文字色；思考块角色节点数为 `0`，最终回答模型名正常显示。
- **测试结果**：`app.js` / `agent-runtime.js` 语法检查通过，定向测试 `13 passed`，全量 `475 passed, 2 subtests passed`，`git diff --check` 通过。

**改动文件**：`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

---

## 2026-07-17 19:53 · Codex

### 移除思考过程标题并彻底取消空思考 DOM

- **标题移除**：思考摘要不再渲染“思考过程 / Thinking”角色标题，并删除对应 i18n 键与专用标题样式；思考和最终回答改由字号、颜色、分段结构及最终回答模型名区分。
- **空块不入 DOM**：没有有效摘要时 `renderThinkingProjection()` 直接返回空字符串，不再依赖 `display:none` 隐藏空块，因此标题或空容器均不存在绘制机会。
- **首段挂载**：空工具轮的首个有效摘要增量到达时执行一次结构渲染，创建思考块；后续内容继续复用原节点做帧级增量补丁。
- **真实页面验证**：无头 Chrome 确认思考摘要块中角色标题节点数量为 `0`；摘要使用 `13.5px` 弱化色，最终回答保留模型名、`14.5px` 正文和主文字颜色，层次仍然明确。
- **测试结果**：`app.js` / `agent-runtime.js` 语法检查通过，定向测试 `13 passed`，全量 `475 passed, 2 subtests passed`，`git diff --check` 通过。

**改动文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 19:44 · Codex

### 修复工具调用晚到导致的模型标题与空思考块闪现

- **真实会话复核**：检查用户最新两次测试会话，确认多轮工具调用先产生 `0` 字可见摘要，另有工具轮先流出 `38–62` 字普通 `content`，随后才收到 `tool_calls`；因此问题独立于 `<think>` 解析。
- **未分类流投影**：新建 assistant 流默认标记为 `pending`；工具调用到达前继续增量显示普通文本，但不提前显示模型名。确认工具轮后原子切换到 `thinking`，已有文本保持可见；确认最终回答后才显示模型标题。
- **空思考块延迟显现**：空的 streaming thinking article 保持在 DOM 中供增量补丁复用，但使用 `is-empty` 隐藏整块；首个有效摘要到达后原地解除隐藏，因此“思考过程”不会先出现再消失。
- **节点与流畅度**：未增加网络等待、定时缓冲或全量流式重渲染；增量内容仍由原有帧队列更新，状态栏维持同一节点。
- **真实页面验证**：无头 Chrome 确认 pending 文本不带模型名、切换工具轮后文本不消失、空思考块不可见且有效摘要到达后原地显示；状态栏节点身份保持不变。
- **测试结果**：`app.js` / `agent-runtime.js` 语法检查通过，定向测试 `13 passed`，全量 `475 passed, 2 subtests passed`，`git diff --check` 通过。

**改动文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 19:33 · Codex

### 修复流式 `<think>` 原始推理与模型标题闪现

- **增量标签解析**：重写 `splitThoughtContent()`；检测到 `<think>` 开始标签后，在 `</think>` 到达前将后续内容持续归入隐藏 `thought`，不再作为可见回答渲染。
- **跨分片保护**：对 SSE 包尾部的 `<t`、`<thi` 等未完整开始标签暂存最多 6 个字符，下一包确认后再分类，防止半个标签及随后的长推理短暂泄漏。
- **正常流式保持**：闭合标签后的真实回答仍立即进入 `content` 并通过原有 `requestAnimationFrame` 增量补丁显示，没有新增网络等待或全量消息重渲染。
- **回归验证**：新增直接执行实际 JavaScript 解析函数的行为测试，覆盖半标签、未闭合标签、完整标签、大小写标签和普通回答；无头 Chrome 确认未闭合长推理期间模型标题与正文均隐藏，真实回答到达后正常显示，状态栏节点保持稳定。
- **性能与测试**：浏览器中约一万字符输入连续解析 1000 次约 `3.3ms`；`app.js` / `agent-runtime.js` 语法检查通过，定向测试 `13 passed`，全量 `475 passed, 2 subtests passed`，`git diff --check` 通过。

**改动文件**：`app.js`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 19:26 · Codex

### 收紧思考过程与最终回答的块间距

- 将 `.thinking-process` 的底部间距从 `28px` 调整为 `20px`，仅影响思考过程与其后最终回答之间的距离。
- 前端回归测试新增块间距断言；定向测试 `12 passed`，`git diff --check` 通过。

**改动文件**：`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 19:25 · Codex

### 收紧思考过程分段间距

- 将连续 `.thinking-summary-item` 的段间距从 `1.15em` 调整为 `.65em`，保留原有 `1.72` 行高以及思考块与其他消息之间的整体间距。
- 前端回归测试新增精确间距断言；定向测试 `12 passed`，`git diff --check` 通过。

**改动文件**：`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 19:18 · Codex

### 状态栏去除工具阶段与胶囊样式

- **取消分阶段状态**：删除 `_taskPhase`、`setTaskPhase()` 及模型轮和工具执行循环中的阶段切换调用；状态栏在整个任务生命周期内恒定显示“处理中 · 累计时间”，不再短暂闪现工具名。
- **轻量活动提示**：运行状态改为透明、无边框的单行提示，由脉冲圆点、固定状态文案和蓝色计时组成；模型名继续由思考或最终回答自身标题展示，不在状态栏重复出现。
- **空回答标题处理**：流式最终回答尚无正文时隐藏孤立的模型标题，正文首个增量到达后由增量补丁显示标题，避免状态提示下方提前出现空的 Assistant 区块。
- **稳定性保留**：状态栏仍使用唯一稳定 DOM 节点和当前任务锚点；计时更新、正文增量和任务运行期间均不重建状态栏。
- **真实页面验证**：无头 Chrome 加载 `127.0.0.1:3010`，确认状态文案为“处理中”、不存在模型或阶段节点、背景透明且无边框；空回答标题先隐藏、正文到达后显示，状态栏外层与内部节点身份保持不变。
- **测试结果**：`app.js` / `agent-runtime.js` JavaScript 语法检查通过；定向前端测试 `12 passed`；全量 `474 passed, 2 subtests passed`。

**改动文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 18:58 · Codex

### 运行状态栏固定到当前思考过程上方且保持无闪烁

- **位置调整**：为当前运行任务生成 `data-active-run-anchor`，锚点固定插在该任务的用户消息之后，因此 DOM 顺序稳定为“用户消息 → 状态栏 → 思考过程 → 最终回答”，状态栏不再落到消息列表末尾或紧贴输入框。
- **节点稳定性**：保留唯一的 `#activeRunBanner` 实体；消息投影需要原子重建时，先把状态栏同步移到 `.messages` 停放位，重建后再在同一个 JavaScript 任务内挂回新锚点，不重建状态栏、计时器或动画节点。
- **布局收敛**：锚点复用消息列宽并提供固定下间距，状态栏自身改为占满锚点宽度，不使用绝对定位、位移或基于输入框高度的定位逻辑。
- **真实页面验证**：无头 Chrome 加载 `127.0.0.1:3010`，确认状态栏位于思考过程和最终回答之前；思考内容重渲染及“思考中 → 执行工具”切换后，外层状态栏和内部状态节点身份均保持不变，页面内锚点与状态栏都只有 `1` 个，且不与 composer 重叠。
- **测试结果**：`app.js` / `agent-runtime.js` JavaScript 语法检查通过；定向前端测试 `12 passed`；全量 `474 passed, 2 subtests passed`。

**改动文件**：`index.html`、`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 18:47 · Codex

### SSE 实际页面修复：清除幽灵消息 + 状态栏回归消息流

- **真实数据诊断**：核对 `127.0.0.1:3010/app.js` 与工作区 SHA-256，两者一致；读取截图对应会话 `f51fc728aad84c30`，持久化消息中只有 `1` 条最终回答和 `4` 条非空工具轮总结，确认截图中的重复回答、重复阶段文字和空模型标题都是 DOM 幽灵节点，不是模型重复请求或会话数据重复。
- **取消消息节点复用**：移除 `renderMessages()` 中对 streaming assistant article 的 detach / replace 逻辑；新增稳定 `#messageList` 投影根，工具轮重分类、流式完成等结构变化时都从 `state.messages` 原子重建该子树，旧流式 article 不再可能被留在最终回答之后。
- **防御性清理**：新增 `pruneStaleStreamingNodes()`，每次渲染前按会话、消息索引、streaming 状态和 `answer` / `thinking` 投影类型清除失效或重复节点，即使命中渲染缓存也会清理异常 DOM。
- **状态栏布局**：`#activeRunBanner` 移入 `.messages` 滚动区，作为 `#messageList` 之后的稳定兄弟节点；改为普通文档流布局，宽度复用 `--conversation-content-width` 并与 Assistant 左边缘对齐，不再使用 `absolute + bottom: 134px` 覆盖输入框。
- **动态输入框避让**：新增 `ResizeObserver` 监测 composer 实际高度，通过 `--composer-safe-bottom` 动态调整消息滚动区底部，支持多行输入、图片缩略图和问卷面板导致的 composer 高度变化。
- **真实页面验证**：无头 Chrome 直接加载 `127.0.0.1:3010`及上述实际多轮会话，确认最终回答 `1` 份、阶段总结 `4` 条、手工注入的幽灵节点可清除；状态栏与 Assistant 左边缘误差 `0px`，与 composer 间距 `87px`，消息滚动区与 composer 保留 `18px` 安全间距。
- **测试结果**：`app.js` / `agent-runtime.js` JavaScript 语法检查通过；定向 `14 passed`；全量 `474 passed, 2 subtests passed`。

**改动文件**：`index.html`、`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 18:12 · Codex

### SSE 接力修复：工具轮摘要流式化 + 原子归类 + 稳定状态栏

- **接力核查**：复查了昨日已实施的思考投影分离、`280` 字截断、流式节点 detach/复用、任务级计时和固定状态栏，确认原实现仍缺少工具轮摘要的独立增量投影，且工具轮完成时会先短暂按最终回答渲染再重分类。
- **完整流式摘要**：SSE 首次收到 `tool_calls` 增量后，将当前 assistant 标记为 `thinking` 投影；`patchStreamingAssistantMessage()` 按 `answer` / `thinking` 类型增量更新最终回答或当前轮摘要。
- **不再硬截断**：移除每轮 `280` 字的前端截断，保留模型输出的完整阶段总结；每轮仍使用独立 `.thinking-summary-item` 分段和 `1.15em` 间距。
- **原子归类**：新增 `finalizeStreamingAssistantMessage()`，先同时写入完整文本和 `toolCalls` 元数据，再只渲染一次，消除工具轮摘要短暂闪入最终回答的中间态；流式 DOM 仅在消息索引和投影类型都一致时复用，避免重分类后残留重复气泡。
- **状态栏稳定性**：模型名、阶段文案和计时器改为更新固定 DOM 节点，阶段切换不再重建内层 HTML；后台会话同步保留阶段，切回运行会话时恢复状态和计时，后台任务结束后正确清理任务起始时间。
- **测试补强**：`tests/test_frontend_modules.py` 新增工具轮流式投影、无截断、原子归类、投影类型 DOM 复用和状态栏稳定节点回归断言。
- **验证结果**：`app.js` / `agent-runtime.js` JavaScript 语法检查通过；定向测试 `13 passed`；无头 Chrome 真实 DOM 冒烟测试确认摘要流、最终回答流、无重复和状态栏节点稳定；全量 `473 passed, 2 subtests passed`。

**改动文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`。

---

## 2026-07-17 17:00 · Claude Code

### New API 部署体系：一键构建 + 打包 + 部署流程

为 New API（API 中转站）建立了从源码到部署包的完整构建体系。

**产物**：

| 文件 | 位置 | 说明 |
|------|------|------|
| 构建脚本 | `../new-api-source/build-deploy.ps1` | 一键：前端构建 → Go 交叉编译 → 打包 zip |
| Dockerfile | `../new-api-source/Dockerfile.deploy` | 从预编译二进制构建最小容器镜像 |
| docker-compose | `../new-api-source/docker-compose.deploy.yml` | 简单容器部署配置 |

**构建流程**：
1. `bun run build`（RSbuild 构建 React 前端 web/default）
2. `GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build`（交叉编译，embed 嵌入前端）
3. 打包 binary + .env.example + docker-compose + Dockerfile + systemd 服务文件 → zip

**部署包内容**（约 35MB zip）：
- `new-api-linux`：Linux amd64 二进制（~118MB，单文件，无依赖）
- `.env.example` / `Dockerfile.deploy` / `docker-compose.deploy.yml` / `new-api.service`
- 开发者拿到后 10-15 分钟可完成部署

**三环境架构**：本地开发（new-api-dev）、本地网关（new-api-gateway）、服务器生产，三套实例独立数据库、独立配置、互不影响。

**本次同步完成**：
- `new-api-source` 源码提交（Agent Lite → Code 品牌改名，`f56a57f`）
- 前端重新构建、Go 重新编译
- 部署包已产出：`output/new-api-dev-20260717.zip`

---

## 2026-07-17 07:07 · Claude Code

### SSE 渲染全面重构：固定状态栏 + 阶段化 + 思考摘要

经过多轮迭代（8 个 commit），从临时修补到架构级重构。参考 Claude Code / Codex / OpenCode
设计后确定最终方案。

**调研结论**：
- Claude Code：一条连续流，spinner 模式随事件切换（thinking → tool-use → responding）
- Codex：底部常驻 footer + 内联 spinning，StatusEngine 提案支持阶段化
- OpenCode：结构化 parts 模型（text/reasoning/tool-use 独立 start/delta/end 事件）
- Code 约束：多 SSE 请求架构不可改，需在 UI 层用固定 DOM + 阶段状态模拟连续流

**已完成改动总览**：

| 层 | 改动 | 效果 |
|----|------|------|
| 消息投影 | 仅 toolCalls 中间消息入思考区 | 最终回答不重复 |
| 消息投影 | 280 字截断 + thinking-summary-item 分段 | 简洁分段摘要 |
| CSS | 旧 thought 样式 → thinking-summary-list/item | 间隙 1.15em |
| 防闪烁 | innerHTML 前 detach 流式节点，后 replaceWith | DOM 不销毁，动画不重启 |
| 生命周期 | taskStartTime 独立于 responseStartTime | 跨轮次计时不重置 |
| 生命周期 | startLiveTimer 改用 taskStartTime 驱动 | 工具间隙计时持续 |
| 固定状态条 | index.html 新增 #activeRunBanner（absolute+z-index） | 不入消息 DOM 流 |
| 阶段化 | run._taskPhase + setTaskPhase() | 思考中 / 执行工具 |
| 流式消息 | 移除 role div 中 thinking badge | 消除重复 |
| i18n | 新增 executingTool 中英文键 | 执行工具标签 |

**当前状态栏生命周期**：
```
发送消息 → 思考中（绿色）→ 执行工具·read_file（黄色快动）→ 思考中
→ 执行工具·write_file → 思考中 → 最终回答流式开始 → 消失
```

**已知待处理**（用户将在下一轮反馈）：

---

## 2026-07-17 18:00 · Claude Code + Codex

### SSE 渲染修复：思考摘要分离 + 流式节点防闪烁

**问题诊断**：两个根因：
1. 所有带 `toolCalls` 的 assistant 文本都被收入”思考过程”，导致最终回答可能重复出现在思考区
2. 状态条（模型名 + 思考中 + 计时）绑定在单次流式消息上，DOM 重建时销毁，导致闪烁

**Codex 改动**（消息投影层）：
- `renderMessages()`：仅收集带 `meta.toolCalls` 的中间 assistant 消息进入思考投影块，最终回答不再混入
- `renderFinalAssistantProjection()`：移除 `data-stream-part=”thought”` 独立思考展示区，加 `data-stream-session` 属性
- `patchStreamingAssistantMessage()`：移除 thought 节点增量更新，去掉全量 render 回退
- `renderThinkingProjection()`：重构为 `<thinking-summary-list>` + `<thinking-summary-item>` 独立段落结构
- `styles.css`：删除 `.streaming-thought-output` / `.completed-thought-output` 样式，新增 `.thinking-summary-list` / `.thinking-summary-item` 样式，段落间隙 1.15em

**Claude Code 改动**（DOM 防闪烁层）：
- `renderMessages()`：innerHTML 前先用 `node.remove()` 将流式节点从 DOM 拆下，innerHTML 后再 `replaceWith` 装回；避免销毁导致 CSS 动画重启和计时文本丢失
- `renderThinkingProjection()`：增加 280 字符截断，超长摘要以 `…` 收尾，保持每轮摘要简洁
- 测试变量名 `activeStreamingNodes` → `preservedNodes`，与代码同步

**测试结果**：前端模块 9/9 + 全量 466 passed + 2 subtests passed
**改动的文件**：`app.js`、`styles.css`、`tests/test_frontend_modules.py`、`CHANGELOG.md`、`TODO.md`

- 工具调用间隙、下一轮模型请求之间，”模型名 + 思考中 + 计时”持续可见不闪烁
- 测试：全量 466 passed + 2 subtests passed，零回归

## 2026-07-16 15:22 · Codex

### app.js 模块化：通知服务

- 新增 `src/services/notifications.js`，统一封装页面 Toast 与浏览器系统通知。
- `app.js` 改为从 `window.Code.services.notifications` 使用 `showToast` 和 `notify`；任务完成、权限待确认和问卷等业务触发条件继续留在原主流程中。
- `index.html` 将通知服务固定在核心模块之后、运行时与主应用之前加载；正式 EXE 已通过现有 `src/` 资源规则自动包含该模块。
- 扩充 `tests/test_frontend_modules.py`，覆盖通知模块文件、加载顺序、服务导出、主文件代理及重复定义。
- 验证结果：前端模块定向测试 7 项通过；全量测试 469 项及 2 个子测试通过；新增模块与 `app.js` JavaScript 语法检查通过。

## 2026-07-16 14:46 · Codex

### app.js 模块化：第一批核心基础模块

- 新增 `src/core/namespace.js`，建立 `window.Code.core/services/features/agent/ui` 统一命名空间。
- 将图标路径表与 `uiIcon()` 抽离至 `src/core/icons.js`；将 HTML 转义、紧凑数字、数字、耗时格式化及 token 估算抽离至 `src/core/utils.js`。
- `app.js` 改为从 `window.Code.core` 读取接口并删除对应旧定义；暂时保留两个既有 `formatSize()`，避免在结构拆分提交中混入行为清理。
- `index.html` 固化 `namespace → icons → utils → agent-runtime → app` 的加载顺序。
- `build_exe.py` 补充 `agent-runtime.js` 与完整 `src/` 资源，避免正式 EXE 缺少拆分模块。
- 新增 `tests/test_frontend_modules.py`，覆盖模块文件、加载顺序、命名空间、重复定义与打包资源。

## 2026-07-16 12:30 · Claude Code

### 品牌重命名：Agent Lite → Code

- **Code 项目**（53 文件，398 处）：
  - 核心源码：`server.py`、`app.js`、`launcher.py`、`build_exe.py`、`index.html`
  - class 名：`AgentLiteHandler` → `CodeHandler`、`AgentLiteTrayIcon` → `CodeTrayIcon`
  - env var：`AGENT_LITE_*` → `CODE_*`
  - 数据目录：`~/.agent-lite/` → `~/.code/`
  - EXE 名：`AgentLite-v*.exe` → `Code-v*.exe`
  - localStorage：40 个 key 从 `agent-lite-*` → `code-*`，含自动迁移函数
  - 图标：`agent-lite-icon.ico` → `code-icon.ico`
  - 桌面快捷方式：`AgentLite.lnk` → `Code.lnk`
  - 批处理文件：`启动AgentLite.bat` → `启动Code.bat`
- **老用户数据迁移**：`launcher.py` 新增 `migrate_old_data_dir()`，启动时自动将 `~/.agent-lite/` 数据迁移到 `~/.code/`；`app.js` 新增 localStorage 迁移函数，自动拷贝旧 key 值到新 key。
- **New API 中转站**（8 源文件 + 3 目录）：
  - Go 后端：`controller/agent_lite.go` → `controller/code.go`，函数 `AgentLiteAuthorize` → `CodeAuthorize`，路由 `/agent-lite/authorize` → `/code/authorize`，参数 `agent_lite_token` → `code_token`
  - React 前端：路由 `/agent-lite` → `/code`，页面组件 `AgentLite` → `Code`，导航标题更新
  - `routeTree.gen.ts` 自动生成路由树全部更新
- **Claude Code memory**：24 文件重命名，内部引用路径全部更新到新项目路径。
- **Docker**：`new-api-custom:dev` 镜像重建（`docker commit`），Compose 接管容器管理，`new-api-custom-dev` 正常启动。
- **教训**：已有 Dockerfile/Compose 配置时应先用 `docker build --pull=false`，不应绕过直接装本地工具。见 [[docker-build-rules]]。
- **测试结果**：457 passed, 2 subtests passed，零回归。

## 2026-07-16 02:30 · Claude Code

### 思考合并 + 消息持久化简化 + tool_calls 防御 + read_skill_resource

- **思考过程合并**：`renderMessages` 中所有轮次 assistant 的思考合并为一个块，中间轮次（带 tool_calls 无实质内容）只贡献思考不渲染独立气泡，最终回复 thought 从 `renderFinalAssistantProjection` 移除（流式期间仍实时显示）。
- **消息持久化简化**：移除 delta 增量追加（`_persistedMsgCount` 等），改为流结束/切会话/关页面时全量写入 JSONL。流式期间 `saveSessionState` 只写 meta JSON。彻底消除最后一条消息丢失。
- **tool_calls 防御**：`buildMessages` 中任何非 tool 消息跟在带 tool_calls 的 assistant 后时自动剥离未匹配 tool_calls，遍历结束最终 pass 清理。历史消息不配对也不会 API 400。
- **`read_skill_resource` tool**：原生工具让模型按需读取 skill 内 scripts/references/assets。Server handler + tool definition + permission + i18n。
- **已知问题**：流式 UI 思考中/模型名/计时偶尔消失，刷新恢复，记入 TODO.md。

## 2026-07-16 01:00 · Claude Code

### Skills 渐进式加载 + 会话索引分层

- **Skills**：`list_skills(brief=True)` 只返回元数据；`GET /api/skills/{name}` 按需加载 body；`GET /api/skills/{name}/file` 读取资源文件。
- **会话分层**：`YYYY/MM/DD/{id}.json` 分层；`index.jsonl` 独立索引；`get_sessions()` O(1)；全 CRUD 自动同步索引；启动迁移 + 孤儿清理。`SESSION_INDEX_PATH` 改为函数支持 mock。

## 2026-07-15 22:30 · Claude Code

### 会话存储 JSON → JSONL 迁移

- **双文件存储**：每个会话拆为 `{id}.json`（元数据：title、stats、runState、messageCount、lastMessageTime）和 `{id}.jsonl`（消息逐行追加，7 字段：role、content、thought、meta、_images、_model、_time）。
- **Server 端**：新增 `read_jsonl`、`write_jsonl`（atomic temp+replace）、`append_jsonl`（受 `_json_write_lock` 保护）、`count_jsonl_lines`、`read_last_jsonl_line`、`messages_path` 六个函数；新增 `POST /api/sessions/{id}/messages` 增量追加端点；改造 8 个 session CRUD 函数（create/save/get/list/delete/branch/archive/summary）适配双文件。
- **前端 delta 持久化**：`saveSessionState` 只将新消息增量追加到 JSONL（`slice(persisted, -1)`，排除正在流式输出的最后一条）；`clearRunCheckpoint` 流结束时 flush 最后一条完整消息；`cacheActiveSessionState` 切会话前 flush 剩余；`beforeunload` + `sendBeacon` 兜底；`loadSession` 重置 `_persistedMsgCount` 追踪。
- **compaction 兼容**：compaction 只插 `meta.kind: "compact-summary"` 标记，不缩减消息数组。delta 追加模式天然兼容，无需全量覆写。
- **消息不丢失**：流式期间最后一条 assistant 消息不在 delta 中落地（因内容原地增长），流结束由 `clearRunCheckpoint` 一次性写入完整内容。
- **旧数据清理**：147 个旧测试会话 JSON 全部删除，新格式零兼容负担。
- **额外修复**：`renderMessages()` 两个 return 路径末尾补 `scheduleMessagesScrollToBottom`，修复用户发新消息后不自动滚到底的已有 bug。
- **测试结果**：全量 **457 passed, 2 subtests passed**（新增 11 项 JSONL 专项测试，更新 1 项并发测试适配新格式）。
- **改动的文件**：`server.py` +170 行，`app.js` +100 行，`tests/test_session_persistence.py` +80 行，`tests/test_routes.py` +20 行，`tests/test_branch.py` +12 行，`tests/test_concurrency.py` ~5 行修改，`docs/session-jsonl-migration.md` 方案文档新增。

## 2026-07-16 01:00 · Claude Code

### Skills 渐进式加载 + 会话索引分层

**Skills 三层渐进式加载（对标 Codex）**：
- `list_skills(brief=True)` 只返回 name、description、keywords、tools、dir，不含 body（Level 1）
- 新增 `GET /api/skills/{name}` — 按需加载单个 skill 完整 body + 资源列表（Level 2）
- 新增 `GET /api/skills/{name}/file?path=...` — 按需加载 skill 内资源文件 scripts/references/assets（Level 3）
- 前端 `loadSkills()` 用 `?brief=1` 只取元数据；`ensureSkillBody(skill)` 懒加载 body
- `getMatchedSkillPrompts()` 改为 async，匹配后按需拉取 body；`getSystemPrompt()` 改为 async
- 系统提示词不再包含全部 15 个 skill body，仅 name + description 列表
- `showSkillDetail` / `showSkillDetailInSettings` 点击时懒加载完整 body
- token 估算路径（calcStats）使用 `briefSkills=true` 跳过 body 加载

**会话索引 + 目录分层（对标 Codex）**：
- `session_path` / `messages_path` 改为 `YYYY/MM/DD/{id}.json` 分层存储
- 新增 `data/sessions/index.jsonl` 独立会话索引（id、title、updatedAt、messageCount、_parentId、_branchDepth）
- `get_sessions()` 读索引 O(1) 列表，不再 glob 扫描
- create/save/delete/branch/append_messages 全自动同步索引
- 启动时 `_migrate_sessions_to_hierarchy()` 将旧扁平文件迁移到分层目录并重建索引
- archive_dir 保持扁平不变

**测试结果**：全量 457 passed, 2 subtests passed

## 2026-07-15 22:30 · Claude Code

### 会话存储 JSON → JSONL 迁移

- 双文件存储：`{id}.json`（元数据）+ `{id}.jsonl`（消息逐行追加）
- 前端 delta 持久化：流式期间排除最后一条、流结束 flush、beforeunload sendBeacon 兜底
- compaction 兼容：只插 marker 不缩数组，delta 模式天然兼容
- 滚动修复：renderMessages 末尾补 scheduleMessagesScrollToBottom

## 2026-07-15 19:29 · Codex

### 扩大用户消息操作区的悬停命中范围

- **交互修复**：将用户消息气泡、时间戳和复制按钮包裹为统一悬停区域，并在气泡下方增加 `30px` 透明衔接区，鼠标从气泡移向操作按钮时不再因短暂离开气泡而隐藏控件。
- **范围收敛**：悬停命中宽度跟随实际消息气泡，不扩展到整行空白区域，避免误触发时间戳和复制按钮。
- **可点击性**：透明衔接区接收鼠标事件，操作控件通过层级保持可见和可点击。
- **验证结果**：浏览器确认新样式规则已加载；`app.js` 语法检查通过；P0 稳定性回归 12 项通过。

## 2026-07-15 18:08 · Codex

### 优化断网重连提示语义
- **计时核验**：使用可控断网测试确认浏览器轮询第 1～5 次失败约发生在 `0.02s / 0.54s / 1.55s / 3.57s / 7.58s`；计数未被重复轮询叠加，第 5 次较快出现源于 `0.5s / 1s / 2s / 4s` 的快速退避设计，不是计数错误。
- **文案修正**：中文提示改为“网络连接已中断，正在自动恢复 · 已尝试 N 次 · Ns 后重试”，英文同步调整，明确数字表示累计尝试次数而非当前等待轮次。
- **策略保持**：不修改快速探测及第 5 次后每 8 秒持续重连的行为，避免牺牲短暂断网时的恢复速度。

## 2026-07-15 17:40 · Codex

### 已完成断网重连状态提示

- **断网可见反馈**：浏览器与本地运行流失联时，在当前回答内容下方显示“网络异常，重新连接中（第 N 次），倒计时 Ns”，避免输出静止被误认为卡死。
- **恢复联动**：重连成功后自动移除提示；模型名旁的“思考中 + 总用时”持续保留，不再被网络状态替换。
- **状态隔离**：区分浏览器长轮询断线与上游模型请求重试，保持既有 5 次模型退避策略和后台任务连续性不变。
- **验证结果**：`app.js` 与 `agent-runtime.js` 语法检查通过；P0 稳定性回归 12 项通过；完整测试 451 项及 2 个子测试全部通过。

## 2026-07-15 16:33 · Codex

### 已完成会话刷新后的滚动位置修复

- **根因修复**：将历史会话恢复后的滚动定位从时间线渲染中拆出，避免只有一条用户消息、时间线不显示时缺少滚动到底部的逻辑。
- **布局兼容**：会话内容渲染后等待两帧再定位到底部，兼容 Markdown、diff 等内容完成布局后的实际高度。
- **并发保护**：延迟滚动前校验当前会话 ID，防止快速切换会话时旧会话的滚动任务影响新会话。
- **职责收敛**：时间线仅负责消息导航，不再隐式控制对话区滚动位置。

---

## 2026-07-15 15:38 · Codex

### New API 开发环境数据库恢复与备份

- **开发库全量同步**：将生产网关 `3000` 的 SQLite 数据库完整复制到开发网关 `3001`，使开发环境继承用户、管理员、2FA、渠道、令牌、额度、模型、分组和系统设置；复制完成后两套数据库继续独立管理。
- **登录验证**：使用生产库管理员身份成功登录 `3001`，并在新版前端完成部分开发环境设置调整。
- **持久化确认**：`3001` 继续使用 `new-api-source-runtime/data/one-api.db` 的宿主机目录映射，容器重启不会删除该数据库。
- **安全备份**：短暂停止 `new-api-custom-dev` 后生成 `new-api-source-runtime/backups/one-api-dev-20260715-153500.db`，文件大小 `4.15 MB`，SHA-256 为 `B187257F3D655B6B47073084C27916B161EDF4AC3D6C5D1FF026DDEDBE2569FE`。
- **验证结果**：备份与源数据库 SHA-256 一致；开发容器恢复运行后 `http://localhost:3001/` 返回 HTTP `200`。

---

## 2026-07-15 12:23 · Codex

### 模型运行时桥接与刷新续接

- **运行时客户端拆分**：新增 `agent-runtime.js`，把模型运行的创建、长轮询续接、取消和 SSE 适配从 `app.js` 中独立出来，作为后续模块化的第一步。
- **服务端托管模型流**：新增 `/api/runtime/runs` 运行接口，由本地服务持有上游请求、缓存 SSE 事件并分配 `runId`；浏览器刷新后可重新读取同一事件流，不会再次向上游发起模型请求。
- **会话恢复**：运行检查点持久化 `runtimeRunId`；刷新后复用原有流式 assistant 消息并重放事件，完成、失败、取消和重试时统一清理运行标识。
- **取消链路**：停止回答时同时中止浏览器读取和服务端上游连接，避免后台请求继续消耗 token。
- **敏感信息边界**：API key 与请求正文只在服务端运行期间保存在内存中，不写入运行事件或状态响应，并在任务进入终态后清除；终态事件保留 30 分钟用于短时刷新续接。
- **子 Agent 文本清理**：`server.py` 的子 Agent 工具描述、执行结果和 API 错误统一为英文，移除服务端工具结果中的硬编码中文，降低编码异常风险。
- **实现边界**：本次仅将模型请求和事件流下沉到本地服务；工具、权限、问卷及子任务调度仍由浏览器端 Agent 循环负责，完整后台 Agent 循环继续保留在 `TODO.md`。
- **验证结果**：`server.py`、`app.js`、`agent-runtime.js` 语法检查通过；运行时刷新重放测试确认同一任务只调用上游一次且 API key 不进入状态响应；全量 `444` 项测试与 `2` 个子测试全部通过。

---

## 2026-07-15 08:59 · Codex

### Claude Code 改动审查与稳定性修复

- **审查结论**：保留项目日志治理、问卷工具互斥、会话恢复等有效改动；重点修复自动压缩、跨会话统计和并发保存中的不稳定点。
- **上下文压缩持久化**：以持久化 `compact-summary` 消息作为模型上下文边界，替代只在运行时生效的 `_compactPrefix` / `_compactCutoff`；刷新或重启后仍能保持压缩结果，且边界在过滤后台消息后计算。
- **多会话用量隔离**：按会话保存并恢复 `lastUsage`，防止一个会话的 token 统计污染另一个会话；手动或自动压缩后清除旧用量基线。
- **上下文窗口识别**：统一模型上下文上限判断，支持 Claude 点号和连字符版本名，并修复 Claude 4.6+ 1M 上下文分支不可达的问题。
- **并发保存稳定性**：会话读改写统一置于文件锁内；Windows 临时文件占用时对原子替换进行短暂退避重试，避免后台保存线程静默失败。
- **测试补强**：增加会话用量持久化、文件替换重试、并发保存异常捕获、压缩边界持久化与模型上下文识别测试；同步更新已被新实现替代的旧源码断言。
- **验证结果**：`app.js` 语法检查通过；全量 442 项测试通过，未出现 `PermissionError`、后台线程异常或 traceback。

---

## 2026-07-15 · Codex

### 项目文档治理

- 确立 `CHANGELOG.md`（已完成历史）与 `TODO.md`（待办计划）为项目统一的人类可读记忆。
- 新增 Claude Code 与 Codex 的项目入口说明，要求任务开始前读取、重要改动完成后同步更新。
- 校正流式 token 计数状态，并补全 P0 问卷工具互斥说明。

---

## 2026-07-15 · Claude Code

### Token 用量优化

- **系统提示词精简**：`defaultSystemPrompt` 从 611 tokens 压缩至 199 tokens；移除冗余的"可用工具列表"和"文本协议"（tool schema 已定义）；3 条合并为 1 条；"回复风格"8 条压缩为 4 条；删除 `Tool preset` + `Allowed tools` 提示。固定开销 **-45%（~510 tokens/轮）**
- **工具结果截断**：`truncateForDisplay` 12K→6K chars；`run_command` 改为头尾保留模式（头 15 行 + 尾 60 行）；`web_fetch` 限 4K chars
- **历史消息裁剪**：新增 `trimOldToolResults()`，每轮自动折叠 >3K chars 的旧工具结果为一句话摘要，保留最近 4 条完整
- **上下文压缩**：keepCount 2→5；改为只发送压缩版给模型，完整历史保留在 `ctx.messages` 供 UI 显示（`_compactPrefix` + `_compactCutoff` 机制）
- **流式 token 计数校准**：`calcStats` 优先使用 API 返回的真实 `prompt_tokens`，回退到旧估算

### 对话问卷

- **P0 全部完成**：Codex 实现 request_user_input tool + 基础 UI
- **P1 全部完成**：每题独立取消、消息流决策记录、刷新恢复、通知体系统一
- **P2 全部完成**：决策记录索引（上下文识别）、子 Agent 上报决策（`[DECISION_POINT]` 标记 + 提示词约束）、Wizard 合并至规划任务能力
- **问卷触发策略优化**：参考 mattpocock/skills 四原则（grilling/to-spec/domain-modeling/wizard），加"扫描历史决策不重复提问"约束
- **UI 完善**：
  - 逐题显示（单题卡片 + 右上角进度徽章），不再挤一个面板
  - 面板锚定输入框上方（移入 composer，`bottom: 100%`）
  - radio/checkbox 自定义渲染（`appearance: none`，实心圆选中态）
  - 纯文本题去掉"其他"输入框，多选题标明"(多选)"
  - 摘要宽度对齐聊天气泡（复用 `.msg` 类）
  - 按钮文字简洁化（"确认此题"→"确认"）
  - 问卷焦点不触发 composer 高亮（`:has(#userInputPanel:not(.hidden))`）

### 图片消息

- 图片缩略图点击放大预览
- 模型不支持多模态时自动降级：去掉图片 → 纯文本重试（反向排除，仅跳过限流）
- 降级标注 i18n 化：`imageDroppedHint`（中英双语，无 emoji）

### 会话稳定性

- 修复非 abort 错误后 `isStreaming` 永久卡死（`chatForm` catch 分支缺 `setStreaming(false)`）
- 修复 `drainError` 抛出前未清 streaming 状态
- 多处 null guard：`renderTimeline`、`renderMessages`、`buildMessages`、`runAgentLoop`

### 通知系统

- 统一 `isUserAway()`：`visibilityState !== "visible"` 覆盖切标签页 + 最小化 + 锁屏
- 三个触发点全部收口：权限请求、任务完成、问卷弹出

### 平台集成

- 平台地址独立配置：账户面板加"平台地址"输入框，存 localStorage
- `getPlatformUrl()` 取代硬编码 `localhost:3001`
- server 端 `_handle_sync_keys` 从请求体读 `platformUrl`
- 模型 Base URL 含 `/v1` 时兼容去重（`proxy()` 方法）

### 其他修复

- 流式输出降级 bug：`rfile.read(n)` 不保证完整读取 → 循环读满
- 默认记忆清理：只保留 `code-architecture.md`
- 记忆写入由"静默写入"改为"先询问用户确认"（提示词约束）

---

## 2026-07-14~15 · Codex

### P0 稳定性功能

- 网络断开、超时、429/5xx、SSE 中断自动退避重试（最多 5 次）
- 运行状态保存到会话检查点
- 页面刷新后按会话自动续跑
- 多会话恢复使用独立锁

### 会话切换不阻塞

- 移除旧兜底逻辑（"请等待当前回答完成后再新建会话"）
- 新建会话不中止原会话的 AbortController
- 切走前缓存原会话消息和统计
- 分支标记修复（普通会话误显示"已从「」创建分支"）

### 富文件预览

- 图片：适应窗口、缩放、1:1、拖拽
- Markdown：渲染/源码切换
- PDF：浏览器原生预览
- CSV/TSV：表格预览、分页、源码切换
- 大文件拖拽性能优化（requestAnimationFrame 限流）
- 源码乱码修复（高亮器基于原始文本分词）

### UI 改进

- 左下角设置齿轮图标 + 版本更新红点提醒
- 红点点击后消失，按版本号记录已读状态
- 右侧预览栏自动换行
- 预览栏文本/代码自动换行

### P0 对话问卷

- 原生 `request_user_input` tool calling
- 单选、多选、自由文本，单轮最多 3 题
- 每题独立确认/取消 + 填写替代想法
- 全部处理完后自动恢复原任务
- 问卷结果作为摘要插入消息流
- 刷新页面后恢复未完成问卷
- 按会话隔离
- 子 Agent 禁止直接发起问卷
- 问卷调用与其他工具调用互斥，避免任务挂起期间继续产生副作用

### Skill 系统

- 3 个内置 Skill：skill-creator、find-skills、hyperframes
- 补齐 Code 所需的 name/description/keywords/tools frontmatter
- 中英文关键词 + 组合关键词匹配
- `/` 命令由 Skill 名称动态生成

---

## 2026-07-13 · Claude Code

### 稳定性修复

- 第三方 API Base URL 含 `/v1` 时模型检测失败（double path）
- 大请求体导致流式输出降级为批量（body 不完整读取）
- 图片消息自动降级为纯文本重试
- 非 abort 错误后会话 isStreaming 卡死

### UI

- 图片输入缩略图点击放大预览
- 多项 null guard 防 JS 崩溃
- i18n 覆盖新增的降级提示

### 项目

- README.md 创建
- TODO.md 创建
- 默认记忆清理为 code-architecture 唯一项

---

_格式：按日期 + 贡献方分组。新的改动追加在日期区块内，新的一天插入到最上方。_
