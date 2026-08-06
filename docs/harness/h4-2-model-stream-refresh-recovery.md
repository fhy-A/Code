# H4-2 模型流式刷新恢复

## 1. 阶段结论

H4-2 已闭合默认 bundle 在同一服务进程内的三条模型流式刷新生命周期：首个正文增量到达前刷新、已有两段正文后刷新并继续追加、已有两段正文后刷新再取消。三条场景都使用真实生产 `CodeHandler`、AgentRun、Model Runtime、前端 bundle 和浏览器 DOM；classic 只继续通过 H4-1 的纯文本基础冒烟，本阶段没有验证 classic 刷新。

本阶段没有修改 `server.py`、AgentRun/Runtime HTTP 协议、Session JSONL 顶层结构或 runState 字段。恢复事实源是同一服务进程内现有 Runtime 的快照、累计 `result` 和 `nextCursor`，不是新建刷新状态机，也不是离线重放。

## 2. 失败复现与根因

修复前的确定性闸门复现显示：页面刷新后顶部运行状态、累计计时和暂停入口能够恢复；Runtime 已经拥有前两段正文且 `nextCursor=2`，但新页面没有重新发起 Runtime GET，DOM 正文仍为空。活动 Session JSONL 按现有设计也没有部分正文；只有 terminal 闸门释放后，父 AgentRun 的耐久终态才让完整正文一次性出现。

根因分为两层：

- `app.js` 的恢复投影把持久化的非 streaming assistant 当作已经完成，未在确认当前 AgentRun 的 active Runtime 所有权后恢复其内存流式投影。
- `agent-runtime.js` 对既有 `runId` 仍从事件历史重新消费，没有先以 Runtime 快照的累计 `result` 追赶，再从快照 `nextCursor` 继续轮询。

## 3. 最小生产修复

`app.js` 只在父 AgentRun 快照和待处理 `model_started` 都确认同一个 active Runtime 时，复用当前 AgentRun 已有的 assistant，恢复内存中的 `streaming/_streamProjection` 并继续真实 Runtime 投影。非 active Runtime、其他 AgentRun、普通事件重放和已终态消息都不会被误复活；终态清理 active Runtime 所有权。恢复不会创建第二条 assistant，也不会把这两个临时字段写入 Session JSONL。

`agent-runtime.js` 对既有 Runtime 先执行一次 `cursor=0&wait=0` 快照读取，将快照累计 `result` 作为单次 catch-up seed，并从该快照的 `nextCursor` 继续长轮询。快照及后续事件仍由同一投影消费者串行收敛；`completed`、`failed`、`cancelled` 分别结束，失败或取消不会制造成功终答。该 seed 只存在于浏览器投影，不写回 Runtime 事件、AgentRun 或 Session 协议。

## 4. 三条浏览器证据

| 场景 | 刷新与 DOM | 请求、身份与终态 |
|---|---|---|
| `stream-refresh-before-first-delta` | 刷新前正文为空；刷新后顶部状态、累计计时和暂停入口立即恢复；后续正文只增长，最终三段各出现一次 | AgentRun POST 1、Runtime POST 0、chat 1、工具 0；刷新前后 AgentRun/Runtime ID 各唯一且相同；最终 completed、回答一次 |
| `stream-refresh-after-two-deltas` | 刷新前已有两段；刷新后首个非空样本以刷新前正文为前缀，后续每个样本都 `startsWith` 前一样本；第三段在 terminal 闸门释放前出现 | 同一 AgentRun/Runtime；不创建第二请求或重复 assistant；最终三段和最终回答各一次 |
| `stream-refresh-then-cancel` | 刷新前后保留前两段，取消后正文不被清空，只追加唯一 `[Output paused]` | AgentRun POST 1、Runtime POST 0、Agent DELETE 1、chat 1、工具 0；AgentRun/Runtime 均 cancelled，无 `model_completed` 或成功终答 |

三条场景共同冻结可见正文不得回退：首增量前场景从空前缀继续；两段后场景逐样本验证严格前缀关系；取消场景验证刷新前两段在取消终态仍原样保留。所有请求和 Run ID 证据均为脱敏计数或短哈希，不记录 Key、请求头、正文或真实路径。

## 5. Session JSONL 与 Runtime 证据边界

在 before-first 和 after-second 两个活动检查点，Session JSONL 都不包含三段部分正文，也不存在 `streaming` 或 `_streamProjection` 字段；after-second 同时由生产 Runtime 快照证明前两段已到达、`nextCursor=2`。因此刷新后的可见前缀来自 Runtime 累计 `result` 的 catch-up，而不是 Session JSONL 中的临时正文。成功终态后，完整三段正文才进入 Session JSONL，两个临时字段始终不存在。

这只证明服务进程仍存活时的 Runtime 快照追赶。它不证明服务重启、Runtime 原始事件持久化、跨进程恢复、浏览器离线后重放或第二台客户端接管。

## 6. 取消的在途片段边界

取消场景固定证明已有正文保留、唯一暂停说明、唯一 DELETE、AgentRun/Runtime 为 cancelled，且没有 `model_completed` 或成功终答。为解除本地合成上游阻塞，测试在 DELETE 已发出且生产取消信号已经设置后释放闸门；一个已经在途的第三片段可能在取消收敛前进入 Session JSONL。`inFlightThirdPersisted` 只记录该本地竞态的实际布尔值，不要求产品必须追加第三段，也不支持“点击取消后绝无新字节”的更强结论。

## 7. 验证基线

- `npm run test:h4:e2e` 连续两轮：infra 自检通过，均为 `6 passed`、`retries=0`；其中包含 H4-1 原三条冒烟和 H4-2 三条刷新场景。
- 两轮取消延迟分别为 242 ms、243 ms；每轮均为 AgentRun POST 1、Runtime POST 0、Agent DELETE 1、chat 1、工具 0、唯一 Run/Runtime ID。
- `npm run check:frontend` 通过；前端模块与相关 P0 为 `199 passed`。
- 完整 Python 基线为 `1113 passed, 739 subtests passed`。收口前 `app.js`、`agent-runtime.js`、`tests/test_frontend_modules.py` 和 `tests/test_p0_stability.py` 与该完整回归输入哈希一致。
- Node/Python 语法、`git diff --check`、H4 子进程/端口/临时根/output 清理审计通过。

## 8. 未覆盖边界与回退

H4-2 不覆盖 classic 刷新、工具流式刷新、问卷/授权、队列/显式并行/Child AgentRun、图片、压缩、真实 CDN/完整 Markdown、浏览器崩溃、服务或 Runtime 进程重启、跨进程恢复、EXE 或发布门禁。

独立回退只需撤销本阶段的 `app.js`、`agent-runtime.js`、四个 H4/前端测试文件及本次收口文档；不需要修改协议、迁移旧数据或撤销 H4-1 浏览器基础设施。

## 9. 真实 Code Dev 补充验收与启动时序修正

2026-08-07 的真实 Code Dev 人工验收暴露了隔离 H4 假上游未覆盖的启动阻塞：不刷新时流式正常，但首增量前刷新和已有正文后刷新都会只恢复运行状态/计时，直到任务终态才一次性出现完整回答；当时暂停也因恢复过晚而未能及时生效。真实页面网络时间线显示，Session 恢复后仍串行等待多次模型目录请求，首个 AgentRun GET 被推迟到约 20.6 秒，刷新页在此前没有 Runtime GET。

`app.js` 因此将既有 `sessionStartup.startRecovery()` 移到模型目录 `refreshModels()` 之前，仍保留在 `platformSyncPromise` 完成和 `authExpired` 检查之后。这只是调整现有恢复链的启动顺序：不新建恢复状态机，不绕过认证失效检查，也不改变队列和后台恢复的内部先后关系。

H4 假上游增加了有界、确定性的模型目录闸门。三条刷新场景都在闸门未释放时确认新的 Runtime GET 已经发生，首增量前场景已恢复流式正文，两段后场景已恢复前缀并追加第三段，取消场景已发出唯一 DELETE。每例仍为 AgentRun POST 1、Runtime POST 0、上游 chat 1，证明修正没有创建第二 Run、Runtime 或模型请求。

修正后真实 Code Dev 人工复验结果为：发送后立即刷新，页面短暂等待后恢复正常流式；已有正文后刷新，页面短暂等待后恢复已有正文并继续流式追加。用户确认当前行为基本满足需求。这不等于“刷新后瞬时恢复正文”：页面仍需完成 Session 恢复及至少一次 AgentRun/Runtime 本地请求；部分正文仍只存在服务进程内 Runtime 累计结果，不写入活动 Session JSONL。本轮人工验收重点复验了两条成功恢复路径；刷新后取消的及时性仍以隔离 H4 场景的 121 ms、唯一 DELETE 和 cancelled 终态为本次回归证据。

完整 Python 回归首次运行还发现一个与 H4 产品逻辑无关的 D3 跨日时钟缺口：手动压缩 VM 已使用 `FixedDate`，但被直接 `require()` 的消息 HTML 投影仍使用宿主日期，8 月 7 日会把 fixture 中 8 月 6 日的“今天”投影为“昨天”。定向测试现在仅在生产 `projectMessages()` 调用边界临时使用既有 `FixedDate`，并在 `finally` 恢复宿主 `Date`。19 个场景哈希及 suite hash `50ff1567e7477d6438bfc7e8175a3936f04177a089a4b4ae5acc0a93a0a2a657` 原样恢复，未修改 fixture 或重基线。
