# H4-8E 问卷等待态与单项队列刷新顺序

## 目标与阶段性质

H4-8E 为既有问卷等待恢复与前台消息队列补齐一个固定组合的真实浏览器证据：主 AgentRun 处于 `waiting_user_input` 时，用户通过真实 composer 的一次 `Control+Enter` 排入唯一纯文本 follow-up；完整刷新保持同一问卷与 pending queue，回答固定选项 B 后仍由同一主 AgentRun 完成，随后队列只提升一次并形成独立 AgentRun；终态再次完整刷新时不产生业务重放。

本阶段是纯测试侧证据补全，不是生产修复。改动只位于隔离假上游与 H4 浏览器测试，没有修改生产代码、API、AgentRun/Runtime 协议、Session JSONL 格式、持久化结构、队列算法或交互语义。场景复用 H4-8A 的问卷 lifecycle 与稳定投影，没有复制第二套问卷状态机，也没有重基线 H4-8A/H4-8B 的既有哈希。

本专题按 [`Harness 第一轮完成线`](harness-round-1-completion-line.md) 关闭“问卷等待态 + 队列刷新顺序”的固定自动证据项；它不表示 Harness 第一轮已经完成，也不替代授权失败安全重试、`/parallel` 编辑授权恢复审计或最终整体验收门禁。

## 固定场景与真实排队入口

主任务使用与 H4-8A 相同的 required single-choice 问卷契约：唯一问题、两个固定选项、`allowOther=false`，用户最终选择 B。主 AgentRun 进入 `waiting_user_input` 后、第一次完整刷新之前，测试通过真实 composer 执行一次 `Control+Enter`，排入唯一固定纯文本队列消息；测试显式走 queue 行为，不依赖默认 steer，也不直接写浏览器 state。

排队提交边界严格证明：

- 真实 composer 只执行一次 `Control+Enter`，queue save/enqueue 恰好一次，`/steer` POST 为 0；
- queued user 的 `queuedDispatch.id`、Session `runState.queuedMessages[0].id` 与 `clientRequestId` 三者闭合；
- queue 身份与主 AgentRun、主 Runtime、问卷 `requestId` 和 tool call 身份不相交；
- 排队时没有新增 AgentRun、Runtime、上游 chat、`/input`、`/resume`、registered tool delegation/execution 或 queue promotion。

本场景只有一个 pending queue item，因此只证明该唯一身份跨等待刷新保持并在主任务结束后提升一次，不把它外推为多项 FIFO、优先级、公平性或通用 queue exactly-once。

## 等待态刷新与问卷身份恢复

排队后进行完整页面刷新。恢复后的主 AgentRun、问卷 `requestId`、tool call、pending input、queue id、`clientRequestId` 与 queued user 身份均与刷新前相同；queue 仍为唯一 `pending` 项，顺序没有变化，也没有提前提升。

等待态刷新允许正常的 Session、AgentRun 和 Runtime GET 恢复读取，但以下业务增量全部为 0：

- AgentRun POST、Runtime POST 与上游 chat；
- `/input`、`/resume` 与 `/steer` POST；
- enqueue、queue promotion；
- registered tool delegation/execution 与原生 interaction execution。

等待态 Session 顺序为主 user、assistant tool owner、questionnaire tool call、queued user；DOM 顺序为主 user、问卷 tool process、queued user。问卷仍可见且可作答，queue 仍显示 pending；两类身份没有错连。

## 单次作答、主任务终结与唯一提升

刷新恢复后，测试通过真实 radio 选择固定选项 B 并确认一次。生产链只发送一次 `/input` 与一次 `/resume`；原主 AgentRun 保持身份不变，在第二个 Runtime 中收到问卷回执并产生唯一主 final。

问卷属于生产原生 durable interaction：主 AgentRun 的 native interaction execution 总量恰好为 1。它不是 registered tool execution；全场景 registered tool delegation/execution 均为 `0/0`。不得将这两类计数合并描述为“所有工具执行为 0”。

队列在主任务仍 active、仍等待问卷或主 final 尚未耐久时都不会提升。观测到的因果顺序严格为：

```text
main-terminal-checkpoint-cleared → queue-promoted
```

主任务终态 checkpoint 清理已被观察到，随后唯一 queue promotion POST 恰好一次。冻结投影只记录“已观察到 checkpoint 清理”的布尔事实，不冻结底层 Session 保存次数。提升后的 queued user 从原位置移到主 final 之后，解除 `detachedFromMain`，以原 queue `clientRequestId` 创建第二个 AgentRun；queued Run 只创建一个 Runtime、发起一次上游 chat，并形成唯一 queued final。

## AgentRun、Runtime 与上游上下文

终态公共计数为：

| 观察层 | 计数 |
|---|---:|
| AgentRun / Runtime / upstream chat | 2 / 3 / 3 |
| `/input` / `/resume` / `/steer` POST | 1 / 1 / 0 |
| enqueue / queue promotion | 1 / 1 |
| native interaction execution | 1 |
| registered tool delegation / execution | 0 / 0 |

主问卷 AgentRun 的 12 个连续事件严格为：

```text
created → model_started → model_completed → tool_started
→ user_input_required → user_input_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

其中 `waiting_credentials` 是既有耐久恢复链的事件名，不表示场景使用了真实凭据；用户作答前的实际等待状态仍为 `waiting_user_input`。

queued AgentRun 的 4 个连续事件严格为：

```text
created → model_started → model_completed → completed
```

三个 Runtime 都为 `completed`，cursor 严格为 `[3,3,3]`：前两个属于主问卷 AgentRun，第三个属于 queued AgentRun。

隔离假上游只输出脱敏上下文投影，不记录完整请求体、正文或随机身份。三次模型请求依次证明：

1. 主任务首轮的 queued marker 数为 0；
2. 主任务问卷回执后的第二轮 queued marker 仍为 0，排队内容没有提前进入主模型上下文；
3. queued Run 的 questionnaire user、主 final 与 queued user marker 各为 1，稳定顺序为 `questionnaire-user → questionnaire-final → queued-user`，且主 final 位于 queued user 之前。

## 终态 Session、DOM 与刷新零重放

终态 Session 精确为 8 条消息，顺序为：

```text
initial user → assistant tool owner → questionnaire tool call
→ user input summary → questionnaire tool result → main final
→ queued user → queued final
```

终态 DOM 的六段稳定顺序为：

```text
main-user → tool-process → input-summary → main-final → queued-user → queued-final
```

queued user 的 dispatch 状态为 completed，`detachedFromMain=false`，Session queue checkpoint 已清空；两个 AgentRun、三个 Runtime、三个上游请求与两条 final 的归属保持唯一。

终态再次完整刷新后，AgentRun/Runtime 身份、事件、Session 八条顺序、DOM 六段顺序、queue/clientRequest 关系与上游上下文投影均保持。刷新允许正常 GET，但 AgentRun/Runtime POST、上游 chat、`/input`、`/resume`、`/steer`、enqueue、promotion、registered tool delegation/execution 和 native interaction execution 的业务增量全部为 0。

## 稳定语义哈希

H4-8E 为 bundle 与 direct classic 共用同一 lifecycle，冻结以下 12 项 SHA-256：

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `6f07ddb587ba352d15f3b9d8608d3b89c475f3f3217ec713304b31b0e5a6da41` |
| `waitingQuestionnaireSnapshot` | `722b86175ddd43f7306b459d5f6410a0a7c8a8f3ad5b8075cfb6dd2bc8506c3b` |
| `queueSubmissionProjection` | `8fa3b6d9e440913edceefca2c9e1855e7b7be51341fb68faffe7fef9d0269556` |
| `waitingQueueSession` | `225ef8c09bb0f7b09463209501568d754d2cd4a795bba060a7e667d2b8c01eeb` |
| `waitingDom` | `499509b21abbc0a3f6805561df5918183df04267737159089aa56aee7010bff6` |
| `waitingRefreshLifecycle` | `d114d05ecf65efe64f8c21b589dfde91e0f6dafd7c44616fa83eaeeb11076cd8` |
| `inputSubmissionProjection` | `53765f8c4d304eeeb2db40c7d74404d1db3f8838450d862660a28cfa243b434b` |
| `queuePromotionProjection` | `513394446016e85f76718ef0c65945b3f24a47867e39e04232f3968d4a18446a` |
| `runtimeProjection` | `f7f333b2b0573c96ee9b2a489019f32d7724c5273a5963896884378e1a9eb7ba` |
| `sessionRoleContent` | `e9a93e5e49bde42f63d3047001afa5f79c78373f1365378367311022d15f71ec` |
| `terminalDom` | `d2dc405690fcf7c80ad84ffaca0496aba43b40e2ebd528971a462a82ba9da90d` |
| `refreshLifecycle` | `1583ae3f119ccbc86c8ec055d7d486a7c3a607cfd79fd9728ecadd8907cf55e0` |

哈希只冻结稳定别名关系、顺序、计数、状态、marker 匹配和布尔因果；随机 AgentRun/Runtime/request/queue ID、端口、时间、绝对路径、完整正文、完整请求体与 HTML 不进入哈希。12 项只允许全部为空的 bundle bootstrap 或全部为小写 64 位 SHA-256；冻结后 bundle/direct classic 以及两轮完整 H4 均逐项相等。H4-8A/H4-8B 旧哈希与既有 lifecycle helper 未改动。

## 验证事实

- 首证据 bundle：`1 passed (6.1s)`；写入候选后 frozen bundle：`1 passed (18.0s)`；direct classic：`1 passed (5.8s)`。bundle/direct classic 的 12 项哈希与完整脱敏 evidence 对等。
- queue、questionnaire、Session、AgentRun、协议、route 与前端相关回归：`415 passed, 247 subtests passed, 1 warning in 34.34s`。
- H4-8A/H4-8B bundle/direct classic 邻接四例：`4 passed (14.3s)`，旧九项哈希未漂移。
- 最终文件树的两轮完整 H4 smoke 矩阵均为 `63 passed (3.7m)`，单 worker、零 retry、各 63 条 cleanup，A/B/C/D/E 冻结哈希跨入口、跨轮一致。第一轮由标准 H4 入口先运行 infra；第二轮先独立通过 infra，再直接调用内层 smoke 并使用专用 output，避免把两轮误写成完全相同的外层命令。
- 完整 `tests` pytest：`1126 passed, 751 subtests passed, 3 warnings in 97.39s`；三条 warning 来自既有损坏 TIFF 负测。
- Harness replay 保持 `17 fixtures / 124 events / 25 checkpoints / 25 checkpoint recoveries / 4 explicit recoveries`，哈希为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。
- frontend freshness、三项 Node 语法、Python AST、`git diff --check` 与最终资源门禁通过；H4 child、Chromium、隔离 host、监听端口、临时根、fixture、backup 与 pyc 均归零，既有 profile 未变化。

第一轮完整 H4 运行时，外层 npm 参数没有传入内层 Playwright，默认 `output/h4-playwright` 因而被清空并重建；五项既有 ignored questionnaire 失败诊断已无法恢复，用户已接受该损失。该轮 63 个测试及 cleanup 本身通过，但默认 output 最终只剩 passed `.last-run.json`。第二轮改用明确的专用 output，专用目录也只产生 passed `.last-run.json`，且默认 output 的文件集合、SHA 与 mtime 未再变化。这里不把旧诊断写成仍然保留。

## 证明边界

本阶段只证明同一 Session、单主问卷、单一 queued 纯文本消息、单标签页/actor、同进程完整刷新下的固定身份与顺序。它不证明：

- 多 queue item 的 FIFO、优先级、公平性、取消、重排、递归 pump 或任意内容；
- optional/mixed 新组合、取消问卷、返回修改答案、未确认草稿或重复点击；
- `/input`、`/resume`、Session save、模型请求或 queue promotion 失败后的安全重试；
- 多标签页、并发 actor、崩溃窗口、服务重启、跨进程恢复或通用 exactly-once；
- Child、background、detached、`/parallel` 或 authorization 与 queue/questionnaire 的组合；
- 真实模型、外网、凭据、Firefox/WebKit、主观视觉/无障碍验收或发布。

## 兼容性与回退

H4-8E 没有生产、API、协议、Session 格式、持久化结构、schema 或迁移变化，也不回写真实数据。回退只需撤销 `isolated_host.py` 与 `smoke.spec.cjs` 中的 H4-8E 测试增量并删除本专题；H4-8A/H4-8B 既有测试、哈希与生产问卷/队列行为保持原样。
