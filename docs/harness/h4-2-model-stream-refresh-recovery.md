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
