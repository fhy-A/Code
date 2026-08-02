# Harness H0-1：现有事件与状态事实清单

> 基线提交：`d444921`
>
> 范围：只记录当前实现，不修改 API、AgentRun、会话 JSONL、前端 UI 或运行时行为。
>
> 机器可读清单：[`h0-1-fact-inventory.json`](h0-1-fact-inventory.json)

## 1. 结论先行

当前 Code 已经具备可恢复的服务端 AgentRun，但跨层契约仍由多组隐式事实共同组成：

- AgentRun 顶层共有 8 个状态：2 个活跃状态、3 个等待状态、3 个终态，其中 `waiting_credentials` 同时承担凭据恢复和服务重启恢复边界。
- 当前共有 24 类耐久事件。8 类由前端按事件正文直接投影，6 类对应的等待或终态主要由 AgentRun 快照驱动，另外 10 类目前只进入耐久记录，没有独立前端消费者。
- AgentRun 记录有 `version: 4`，事件使用独立的 `protocolVersion: 1` 信封。
- AgentRun 领域事件与模型原始 SSE 是两层不同事件流：前者写盘并用于恢复，后者是内存中的短期流式帧。
- 前端同时使用服务端快照、耐久事件、会话 checkpoint、消息投影、会话运行对象和 DOM 展开状态。它们各自有合理用途，但部分领域状态仍由消息和布尔字段推断。
- 当前恢复关键不变量已经存在：事件投影成功后才推进游标；稳定 `clientRequestId` 避免重复创建；服务重启时不重放状态未知的命令；凭据不进入 AgentRun 持久记录。

H0-1 只冻结上述事实。事件重命名、状态归一、reducer、夹具格式和生产代码适配均留到后续单独确认的阶段。

## 2. 事实源与边界

| 事实源 | 当前职责 |
| --- | --- |
| `server.py` | AgentRun 状态、事件生产、工具执行、授权、压缩、持久化与重启恢复 |
| `agent-runtime.js` | AgentRun HTTP 客户端、长轮询、游标推进、模型 SSE 适配 |
| `app.js` | AgentRun 创建与续接、事件投影、会话 checkpoint、计时、问卷与授权交互 |
| `src/core/state.js` | 会话运行态默认值、持久耗时和活动耗时计算 |
| `src/ui/messages.js` | 消息时间线、工具组、执行轨迹、压缩标记和完成状态投影 |

本清单不把以下内容误认为同一协议：

1. AgentRun 的耐久领域事件；
2. 模型 Runtime 的原始 SSE 帧；
3. 会话 JSONL 中的消息；
4. 浏览器内存里的交互状态；
5. DOM 中当前展开、滚动和焦点状态。

## 3. 两层运行事件流

### 3.1 AgentRun 耐久事件

生产函数 `_append_agent_event()` 写入：

```text
{ seq, type, data, createdAt }
```

特性：

- `seq` 在单个 AgentRun 内单调递增；
- 每次普通事件追加后立即持久化；
- 终态由 `_finish_agent_run()` 在持久化前直接追加，避免终态状态已设置后被普通追加函数拒绝；
- 快照只返回 `seq > cursor` 的事件，并给出 `nextCursor`；
- 事件内容会随 AgentRun 记录一起写入 `data/agent-runs/`；
- 当前事件信封使用独立的 `protocolVersion: 1`，未知未来事件仍按兼容策略保留并诊断。

### 3.2 模型 Runtime 瞬时事件

模型 Runtime 使用另一种信封：

```text
{ seq, data }
```

其中 `data` 是原始上游 SSE 文本。`agent-runtime.js` 会将较大的文本增量拆成少量视觉帧，再交给现有流式解析器。该流保存在内存 Runtime 中，状态只有 `running/completed/failed/cancelled`，不等同于 AgentRun 领域事件，也不应直接成为后续耐久事件契约。

## 4. AgentRun 顶层状态

| 状态 | 类别 | 进入方式 | 当前退出方式 | 前端处理 |
| --- | --- | --- | --- | --- |
| `model` | 活跃 | 新建运行、工具结束、恢复目标 | 模型返回工具调用后进入 `tools`；也可进入等待或终态 | `watchAgentRun()` 继续轮询；`model_started/completed` 更新消息投影 |
| `tools` | 活跃 | 模型产生工具调用、恢复待执行工具 | 工具完成后回到 `model`；交互工具可进入等待；失败或取消可进入终态 | `watchAgentRun()` 继续轮询；工具事件更新消息投影 |
| `waiting_credentials` | 等待 | 服务重启恢复；问卷或授权提交后主动丢弃 Key；子 Agent 需要凭据 | 前端重新提交 Key 和 base URL，恢复到 `model` 或 `tools` | 主任务与后台任务均自动调用 `resumeAgentRun()` |
| `waiting_user_input` | 等待 | `request_user_input` 或兼容性空响应继续请求 | 用户提交后写入工具结果，再进入 `waiting_credentials` | 快照的 `pendingInput` 创建问卷或自动续行 |
| `waiting_authorization` | 等待 | 命令、编辑、文件变更或子 Agent 需要决策 | 决策提交后写入结果，再进入 `waiting_credentials` | 快照的 `pendingAuthorization` 创建权限请求 |
| `completed` | 终态 | 最终模型回答或子流程正常结束 | 不可退出 | 快照结果结束主循环并清理 checkpoint |
| `failed` | 终态 | 模型、轮数、内容过滤、工具重试等不可恢复错误 | 不可退出 | 快照错误转为前端错误消息和失败 checkpoint |
| `cancelled` | 终态 | 用户取消、运行时取消或工作线程检测到取消 | 不可退出 | 转换为 `AbortError`，停止活动任务 |

说明：代码常量把状态分成 2 个活跃、3 个等待和 3 个终态，机器清单以这 8 个实际值为准。

## 5. 耐久事件生产与消费映射

### 5.1 直接按事件投影的 8 类

| 事件 | 主要载荷 | 生产点 | 前端投影 |
| --- | --- | --- | --- |
| `model_started` | `round`, `runtimeRunId` | 模型 Runtime 创建后 | `projectAgentModelStarted()` 创建流式 assistant，并附着到同一 Runtime |
| `model_completed` | 正文、思考、工具调用、usage、完成时间和 outcome | 模型轮完成后 | `projectAgentModelCompleted()` 完成或重建 assistant |
| `model_recovery` | 原因、尝试次数、Runtime ID | 空输出、仅思考或兼容恢复 | `projectAgentModelRecovery()` 删除空投影并更新恢复提示 |
| `tool_started` | 工具 ID、名称、参数、参数别名 | 工具执行前 | `projectAgentToolStarted()` 生成 `tool-call` 消息 |
| `tool_completed` | 工具结果、outcome、replayed | 工具或授权结果完成后 | `projectAgentToolCompleted()` 生成 `tool-result`，编辑类另走专用投影 |
| `context_compaction_started` | 压缩 ID、原因、估算、阈值和消息计数 | 自动压缩开始 | `projectAgentContextCompaction(..., "running")` |
| `context_compaction_completed` | 摘要、压缩前后估算、usage 和时间 | 自动压缩成功 | `projectAgentContextCompaction(..., "completed")` |
| `context_compaction_failed` | 错误和错误码 | 自动压缩失败 | `projectAgentContextCompaction(..., "failed")` |

### 5.2 由快照状态驱动的 6 类

这些事件会持久化，但前端并不读取其事件正文决定流程；流程由同一次或后续 AgentRun 快照的 `status/pending*/result/error` 驱动。

| 事件 | 当前快照消费者 | 备注 |
| --- | --- | --- |
| `waiting_credentials` | `runServerAgentLoop()`, `runBackgroundSubAgentJob()` | 前端使用快照状态恢复；事件中的 `reason/resumeStatus` 不直接显示 |
| `user_input_required` | `runServerAgentLoop()` | 前端读取 `snapshot.pendingInput`，不读取事件 data |
| `authorization_required` | 主任务和后台任务循环 | 前端读取 `snapshot.pendingAuthorization`，不读取事件 data |
| `completed` | 主任务和后台任务循环 | 前端读取 `snapshot.result` |
| `failed` | 主任务和后台任务循环 | 前端读取快照的 `error/errorCode` |
| `cancelled` | 主任务和后台任务循环 | 前端读取快照状态并转换为取消异常 |

### 5.3 当前只有耐久记录、无独立消费者的 10 类

| 事件 | 当前用途 | 后续检查点 |
| --- | --- | --- |
| `created` | 审计运行创建参数 | 载荷包含 cwd 与根路径，导出轨迹必须脱敏 |
| `resumed` | 审计恢复目标状态 | 前端只观察恢复后的快照状态 |
| `model_pending` | 标记工具结束后的下一模型轮 | 顶部提示目前由本地布尔字段推断 |
| `steer_submitted` | 审计同一运行接收后续引导 | 不保存引导正文，仅保存 ID、接收时状态和待处理数量 |
| `steer_consumed` | 标记引导已进入下一模型边界 | 不创建新的 AgentRun，也不直接生成界面提示 |
| `command_started` | 标记命令真正开始 | 命令内容不会作为独立消息投影 |
| `tool_retry_blocked` | 标记相同失败达到限制 | 用户最终通过 `tool_completed.result` 或终态错误感知 |
| `authorization_submitted` | 审计授权决策 | 前端提交端自行更新授权面板 |
| `user_input_submitted` | 审计问卷提交 | 前端提交端自行生成问卷摘要 |
| `child_agent_created` | 建立父子运行关联 | 主对话没有独立事件投影 |

“无独立消费者”不等于事件无用，只表示当前 UI 和控制流不会直接根据该事件正文变化。H1 应先决定其契约用途，再考虑适配或保留，不能在 H0 删除。

## 6. 事件载荷中的重复含义和未消费字段

以下是当前事实，不代表立即修改建议：

1. `model_completed.toolCalls` 与随后独立的 `tool_started` 都能形成工具调用投影；前端用工具 ID 合并两种来源。
2. `tool_completed`、`snapshot.toolExecutions` 和 AgentRun 内部 `toolExecutions` 都包含工具结果或状态；主消息投影当前主要消费事件。
3. 等待状态同时存在于顶层 `status`、对应事件和 `pendingInput/pendingAuthorization`；当前控制流以快照状态和 pending 对象为准。
4. 压缩结果同时存在于 `run.compactions`、完成事件和前端压缩消息投影；前端只显示状态与少量计数，不显示事件内完整摘要。
5. `model_completed.finishReason/outcome/forcedFinal` 当前不会直接改变前端消息样式；服务端已先用这些字段决定后续状态。
6. `created` 的运行配置、`command_started.command`、`tool_retry_blocked.failureCount`、提交类事件的决策字段目前没有直接 UI 消费者。
7. 模型 Runtime 的完整结果既通过短期 SSE 投影，也通过耐久 `model_completed` 重建；短期 Runtime 过期时，前端明确回退到耐久完成事件且不会再发一个模型请求。

## 7. 工具执行状态和权限

### 7.1 工具执行状态

当前 `toolExecutions[toolCallId].status` 可出现：

| 状态 | 含义 |
| --- | --- |
| `running` | 普通工具或命令正在执行 |
| `waiting_user_input` | 问卷等待用户回答 |
| `waiting_authorization` | 当前工具等待授权 |
| `applying_edit` | 已进入编辑 proposal 应用边界 |
| `authorized` | 决策已提交，等待继续执行授权后的动作 |
| `applying_file_mutation` | 幂等文件变更已开始 |
| `waiting_child` | 父工具等待子 Agent |
| `waiting_child_authorization` | 子 Agent 需要父级转交授权 |
| `completed` | 工具结果已固化 |
| `cancelled` | 活跃命令被取消 |

前端工具组并不直接读取这套完整状态机。`src/ui/messages.js` 主要根据 `tool-call`、`tool-result`、结果 meta、pending edit 和消息顺序推断 `pending/running/completed/succeeded/failed`。

### 7.2 权限档位

| 档位 | 服务端可选择的 effect | 当前行为 |
| --- | --- | --- |
| `read` | `read`, `interaction` | 只读工具与问卷 |
| `plan` | 上述 + `proposal`, `delegation` | 编辑只生成 proposal，不直接应用 |
| `accept` | 上述 + `command`, `memory_write`, `file_mutation` | 命令和变更经过授权边界 |
| `bypass` | 与 `accept` 相同 | 常规命令和变更直接执行；受管依赖安装仍需授权 |

服务端会再次按 registry 的 `effect/idempotent/background` 过滤工具，前端传入的 `allowedTools` 不是唯一安全边界。

## 8. 持久化与重启恢复

### 8.1 AgentRun 记录

当前记录版本为 4，保存请求选项、消息、工具定义、轮次、压缩、pending 对象、同轮引导及其幂等回执、工具执行、usage、结果、事件和序号。Key 不写入记录；加载时如果持久请求中出现凭据字段，会拒绝恢复。

恢复规则：

- 已终止运行保持原终态；
- 有效的 `waiting_user_input` 和 `waiting_authorization` 连同 pending 对象原样恢复；
- 其他非终态统一恢复为 `waiting_credentials`，并把原状态或待执行工具映射到 `resumeStatus`；
- 服务启动后追加 `waiting_credentials(reason=server_restarted)`，由前端补充 Key 后续行；
- 服务退出时仍在运行的命令被写成 `unknownState/notReplayed` 的失败结果，禁止自动再次启动；
- `clientRequestId` 存在时，运行 ID 由会话与请求 ID 稳定派生，重复创建返回同一 AgentRun。

### 8.2 前端 checkpoint

会话 `runState` 版本为 1，主要保存：运行状态与阶段、开始/更新时间、显式 `elapsedMs`、模型参数、执行所有者、稳定请求 ID、AgentRun ID、事件游标、模型轮、首次响应标记、后台运行和队列。

前端恢复规则：

- 只自动恢复 `running/waiting-network/resuming` 的会话运行；
- `executionOwner !== server-agent` 的旧浏览器运行不会自动重放，而是结束为兼容性失败提示；
- `agentEventCursor` 从 checkpoint 恢复；`watchAgentRun()` 只有在事件投影成功后才推进游标，因此刷新可以重放未完成投影；
- `findAgentProjectionMessage()` 使用 AgentRun ID、事件类型和序号抑制重复消息；
- 完成后先将总耗时写入最终 assistant，再清空运行 checkpoint。

## 9. 前端运行事实源与计时字段

| 层 | 主要事实 | 用途 |
| --- | --- | --- |
| AgentRun 快照 | `status`, pending 对象、result、error、events | 服务端运行事实和控制边界 |
| 会话 `runState` | checkpoint 字段、游标、elapsed、后台与队列 | 刷新和跨会话恢复 |
| `_sessionRuns[sessionId]` | 活跃布尔、起止时间、恢复、Runtime/Agent ID | 当前页面运行协调 |
| 会话消息 | assistant、tool-call、tool-result、压缩标记和 meta | 用户可见历史与执行轨迹投影 |
| UI transient Set | 展开的执行轨迹和工具组 key | 重绘期间保留用户展开选择 |
| DOM | 当前 open、滚动和挂载点 | 只用于采集瞬时交互，不应决定领域状态 |

计时当前组合如下：

- `taskStartTime`：本次任务总计时锚点；
- `responseStartTime`：当前响应阶段兼容锚点；
- `elapsedMs`：checkpoint 中已经累计的显式耗时；
- `taskElapsedBaseMs`：恢复时承接的累计耗时；
- `taskElapsedResumedAt`：恢复后继续累加的本地时间；
- `modelWaitStartedAt`：顶部“等待模型”提示分段阈值；
- `startedAt/updatedAt`：持久 checkpoint 时间；
- assistant `_responseTime`：任务结束后固化给用户的总耗时。

`persistedRunElapsedMs()` 优先使用合法的显式 `elapsedMs`，没有时才用 `updatedAt - startedAt`；`activeRunElapsedMs()` 优先使用恢复基数加恢复后的本地增量。这是当前避免刷新后把离线墙上时间错误计入任务的事实基础。

## 10. 当前前端推断状态

需要在 H1/H2 重点做影子比较、但 H0 不修改的推断点：

1. 顶部状态由 `hasFirstModelResponseStarted/modelRecovery/modelWaitStartedAt/modelResponseStarted` 推断，不直接来自统一领域状态。
2. 工具 outcome 由结果 meta、pending edit、结果是否存在和 call 是否存在推断。
3. 工具组是否活跃由组内是否存在 `running/pending`，以及渲染调用的 `activeStage` 共同推断。
4. 工具组活动标题取当前 `running/pending/最后一条` 工具；完成后按工具 family 和数量生成统述。
5. 一轮是否存在执行轨迹由消息角色、压缩标记、assistant toolCalls 和文本占位规则推断。
6. 最终回答轮由 assistant 内容、流式阶段、工具元数据和特殊标记推断。
7. 工具组与整轮轨迹的展开状态在重绘前从 DOM 收集到 Set，再传给纯消息投影；任务终态后活动工具组不再强制保持展开。

## 11. 首批脱敏轨迹候选

H0-1 只冻结场景和最小断言，不在此阶段决定最终夹具格式。H0-2 再确认 JSON 格式、兼容版本和脱敏检查器。

| ID | 场景 | 最小断言 |
| --- | --- | --- |
| `plain-text-final` | 单轮纯文本完成 | 一个最终回答、一个终态、无工具 |
| `single-read-tool` | 单工具后继续回答 | 工具调用和结果各一次，最终回答一次 |
| `multi-tool-stage` | 同阶段多个只读工具 | 活动时显示当前工具，阶段完成后显示统述 |
| `questionnaire-submit` | 问卷等待和提交 | pending ID 稳定，提交后不重复问卷 |
| `edit-authorization-accept` | 编辑授权通过 | proposal 只应用一次，刷新不重复 |
| `command-authorization-reject` | 命令授权拒绝 | 命令不启动，拒绝结果可重放 |
| `auto-compaction-success` | 自动压缩成功 | 开始/完成标记按时序出现，最终继续模型轮 |
| `auto-compaction-failure` | 自动压缩失败 | 失败标记可见，状态仍可诊断 |
| `cancel-during-model` | 模型阶段取消 | 单一取消终态，无最终回答伪造 |
| `cancel-during-command` | 命令阶段取消 | 进程停止，工具不重放 |
| `refresh-before-first-response` | 首次响应前刷新 | 不重复上游请求，计时承接 checkpoint |
| `refresh-during-tools` | 工具阶段刷新 | 游标续接，已完成工具不重复执行 |
| `server-restart-command-unknown` | 命令运行中服务重启 | 结果标记 unknown/notReplayed |
| `poll-disconnect-reconnect` | 长轮询断线恢复 | 从成功游标续接，无重复消息 |
| `model-non-action-recovery` | 空输出自动续行 | 最多一次恢复，随后完成或明确失败 |

脱敏底线：

- 全部轨迹使用构造会话 ID、运行 ID、工具 ID 和路径；
- API Key、Access Token、Authorization、Cookie 和真实 base URL 不进入文件；
- 命令只使用无副作用示例，输出截断到复现所需；
- 模型正文、思考、diff、cwd 和 workspaceRoots 使用短占位内容；
- 不复制真实 JSONL 或截图，只提取状态与顺序特征。

## 12. H0-1 发现项

以下只列为后续验证对象，不在本阶段修复：

1. 事件协议已经具有独立 `protocolVersion: 1`；新增事件必须继续遵守向前兼容与凭据拒绝边界。
2. `waiting_credentials` 同时表达安全凭据边界和服务重启恢复，语义较宽。
3. 10 类事件没有独立消费者，是否为审计事件、未来事件或冗余事件仍需按契约逐项评估。
4. 等待和终态的事件正文不驱动前端，快照才是控制事实；后续适配器必须保留这一差异。
5. 工具执行的服务端状态比前端可见状态更细，直接替换前端推断可能改变现有 UI。
6. 多层时间字段各自有效，但没有一份统一的阶段计时表。
7. 模型 SSE 与 AgentRun 事件都带序号，但作用域、耐久性和载荷完全不同，不能共享同一去重逻辑。
8. 活动工具组和执行轨迹的展开状态属于本地交互事实，不应被 reducer 持久成领域状态。

## 13. H0-1 验收边界

本阶段完成条件：

- 机器清单包含全部 8 个顶层状态和 24 类现有耐久事件；
- 文档标出每类事件的生产点、消费方式、关键载荷和无消费者情况；
- 工具状态、权限、重启恢复、前端事实源和计时字段有明确清单；
- 至少 10 条脱敏轨迹候选覆盖计划要求；
- JSON 可解析，事件名称可与源码扫描结果核对；
- 完整 Python 回归与发布前端门禁通过；
- Git 差异只包含 H0-1 文档、机器清单和开发日志。

H0-1 通过后，H0-2 才讨论夹具格式、AgentRun v1/v2/v3 与旧 JSONL 最小兼容样本、脱敏扫描脚本和首次发送/刷新/长会话性能测量方式。

## 14. 自动验证基线

采集时间：2026-08-02 19:27（Asia/Shanghai）。

| 门禁 | 结果 | 墙钟耗时 |
| --- | --- | --- |
| `python -m pytest tests/test_harness_inventory.py -q -p no:cacheprovider` | `5 passed, 12 subtests passed` | 定向运行 `0.25s` |
| `python -m pytest tests -q -p no:cacheprovider` | `919 passed, 255 subtests passed` | pytest `97.28s`；PowerShell 实测 `99.30s` |
| `npm run check:frontend` | bundle 构建、freshness、bundle 语法和经典回退产物均通过 | PowerShell 实测 `2.90s` |
| `git diff --check` | 通过 | 不适用 |

本次只建立离线事实清单，未启动浏览器或真实模型，因此首次发送、刷新恢复和长会话 replay 的用户体验耗时尚未采集；这些测量方式与假上游时序在 H0-2 单独确认，避免把人工环境噪声误写成 Harness 基线。
