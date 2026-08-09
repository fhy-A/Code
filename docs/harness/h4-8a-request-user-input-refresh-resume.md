# H4-8A `request_user_input` 等待态刷新、单次提交与同 Run 恢复

## 完成范围与生产修复

H4-8A 冻结一个确定性的真实浏览器生命周期：模型首轮返回唯一 `request_user_input`，AgentRun 进入耐久等待态；页面在用户作答前完整刷新，随后通过生产 UI 选择固定答案并只提交一次；同一 AgentRun 恢复、完成第二轮模型请求并形成唯一终答；终态再次完整刷新时不产生重放。默认 bundle 与 `/dist/frontend/index.classic.html` direct classic 复用同一参数化 helper、生产 UI/API 和隔离 loopback 假上游。

生产根因位于 server-agent 问卷提交后的保存边界：答案摘要先由 `appendUserInputSummary()` 写入当前内存消息，但启动 resolver 或 `resumePersistedSessionRun()` 之前的既有 `saveSessionState()` 没有持久化完整 messages；后续服务端 Session 重载会用耐久消息覆盖内存，使摘要在终态或刷新后丢失。修复只在 `finishServerAgentUserInputRequest()` 中，把该既有 awaited save 改为 `persistMessages: true`，仍保持“提交答案 → 追加摘要 → 更新 runState → 保存 → render → resolver/恢复”的原顺序。没有重写问卷、恢复或消息投影状态机。

## 兼容性与回退

修复复用既有 Session serializer、JSONL 记录和消息 `meta`：没有新增字段、版本、迁移、AgentRun/Runtime/工具协议或问卷交互格式，也不回写历史会话。新保存的 `user-input-summary`、tool call/result 与 final 仍是现有消息格式；撤销本阶段四文件即可独立回退，已经写入的旧格式消息继续可读，不需要数据迁移或清理。

## 固定证据场景

隔离假上游只为固定 marker 返回一个 required single-choice 问题：一个问题、两个固定选项、`allowOther=false`。测试在等待态刷新后，重新建立隔离 H4 的假上游配置，通过真实 radio 与确认按钮选择固定选项 B，并只提交一次；该配置重建只属于测试环境，不证明产品会持久化 base URL。场景使用 Chromium 与 loopback 假上游，不调用真实模型、外部网络、凭据或注册工具执行器。

等待态刷新发生在用户选择答案之前，因此只证明 pending questionnaire 元数据、同一 AgentRun/request 与问卷 DOM 的恢复，不证明已选答案跨刷新保存。等待态完整 reload 后：

- AgentRun、`requestId`、pending input、tool owner 和问卷表单均保持唯一；
- AgentRun POST、Runtime POST、上游 chat、`/input`、`/resume`、注册工具委托/执行和 interaction execution 的刷新增量均为 0；
- 不产生第二个 AgentRun、第二份问卷、模型重发、工具重放或自动 resume。

## 单次提交、同 Run 恢复与终态

真实 UI 提交后的固定计数为：

| 观察层 | 计数 |
|---|---:|
| AgentRun POST 总数 | 1 |
| `/input` POST | 1 |
| `/resume` POST | 1 |
| 耐久 Runtime 总数 | 2 |
| 上游 chat 总数 | 2 |
| 注册工具 delegation | 0 |
| 注册工具 execution | 0 |
| 耐久 native interaction execution | 1 |

两个 Runtime 都由同一 AgentRun 的生产链创建并完成；浏览器没有创建第二个 AgentRun，也不把 Runtime GET/观察请求误记为 Runtime POST。AgentRun 的 12 个事件严格为：

```text
created → model_started → model_completed → tool_started
→ user_input_required → user_input_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

其中 `waiting_credentials` 是当前生产恢复链的耐久事件名，不表示本场景使用了真实凭据；用户作答前的问卷等待态仍是 `waiting_user_input`。

终态 pending input 清空，同一 AgentRun completed。Session 消息顺序严格为：原始 user → assistant tool owner → questionnaire tool call → `user-input-summary` → questionnaire tool result → final assistant。摘要是 `user` role，但保留既有 `_system=true` 与 `skipApi=true`，不作为普通模型用户消息；模型继续所需的原生回执由唯一 tool result 提供。tool owner 持有唯一非空 `request_user_input` 调用，final assistant 的 `toolCalls` 为明确空数组；摘要、回执和 final 各唯一。

终态 DOM 不再显示问卷 panel、pending、活动执行 trace、运行锁或重复问卷；原始 user、唯一 tool process/item、argument/result detail、问卷摘要和 final 均保持唯一。终态完整 reload 后，同一 AgentRun、两个 Runtime、Session 顺序、摘要/回执/final 以及 DOM 语义投影、数量和顺序保持；AgentRun POST、Runtime POST、上游 chat、`/input`、`/resume`、注册工具委托/执行和 interaction execution 的刷新增量全部为 0。

## 稳定语义哈希

随机 AgentRun/Runtime ID 与原始身份、时间、端口、完整提示、原始请求体、JSONL 字节和完整 HTML 均不进入投影；固定 request/tool identity 只以 match 布尔归一。最终 bundle 与 direct classic 的九项 SHA-256 精确相等：

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `6f07ddb587ba352d15f3b9d8608d3b89c475f3f3217ec713304b31b0e5a6da41` |
| `waitingSnapshot` | `722b86175ddd43f7306b459d5f6410a0a7c8a8f3ad5b8075cfb6dd2bc8506c3b` |
| `inputSubmissionProjection` | `1bc729f0df83ed708bbf5f1c397a6aaef4d73788d50ccfb7e45473859cd1bc27` |
| `runtimeProjection` | `c828f32c0eef8d43d9464fce985d82603cc6817b9f1ce948be2fd343e8c4652c` |
| `sessionRoleContent` | `ba570ba870a189929e69069ec42c83747102a292b8118a153900185c27686bf0` |
| `sessionInputMeta` | `30fbb18d20b9db9ab076b932eb1fa9fc11aeaf11f61249f7248db17380234559` |
| `waitingDom` | `f0586513d93fe803d143b3929fd4e56c13fa317de5dcd9dd6ce1d4f1fe351dad` |
| `terminalDom` | `37c2441c6730d71c5b4af6e34798778c004c163686bb5fcee31179cf1fd69f8b` |
| `refreshLifecycle` | `fe57c8d69de127f1cfd2b85d1bfb78878aaede36c381a19e2a1a616bba080629` |

## 验证事实

审批侧在上述精确实现/测试文件树下完成了全部门禁：

- H4 infrastructure 自检通过；
- 冻结后的 bundle 与 direct classic 单例均通过，九项哈希逐项相等；direct classic 首次出现一次业务前 `page.goto` 瞬态，证据保留且不计产品失败或通过，随后唯一获批的零代码重跑通过；
- 连续两轮标准 H4 均为 `53 passed`、单 worker、`retries=0`；
- 受影响的非浏览器定向回归为 `371 passed, 75 subtests passed`；
- 完整 pytest 为 `1131 passed, 751 subtests passed`；
- `npm run check:frontend`、Node/Python 语法和 `git diff --check` 通过；
- 结束时 H4 子进程、监听端口和 `code-h4-e2e-*` 临时根均为 0，所有失败、瞬态与成功诊断/evidence 原样保留。

本专题收口只执行文档、静态、diff、cached 白名单与本地提交门禁，不把上述长矩阵描述为文档提交后重新运行。

## 证明边界与统一归档状态

H4-8A 只证明固定单题、required single-choice、两个选项、`allowOther=false`、选择前等待态同进程完整刷新、一次提交、同 Run 恢复和终态完整刷新。它不证明多题、多选、文本输入、Other、optional、取消、重复或并发提交、多标签页、多个 pending input、`/input`/`/resume`/保存失败、崩溃窗口、服务重启或跨进程恢复、真实模型/网络/凭据、Firefox/WebKit、主观视觉或无障碍、通用 exactly-once、工具副作用、任意历史会话迁移，也不外推到 authorization、Child、queue、steer 或 detached 生命周期。

统一 TODO、开发日志与日志索引仍由并行 workbar 工作占用，本提交明确不修改这些共享事实源；因此本专题提交不是统一项目事实归档已经完成。待共享现场释放后，应另行补记 H4-8A 的完成事实，但不得为本次提交合并或覆盖协作者差异。
