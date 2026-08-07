# H4-6C 同轮双工具生命周期与顺序

## 1. 阶段结论

H4-6C 在隔离 Chromium 中为默认 bundle 补齐同一模型轮两个成功只读工具的真实生命周期证据。固定合成上游依次声明：

- T1：`read_file({"path":"fixture.txt"})`
- T2：`read_file({"path":"fixture.txt","startLine":1,"endLine":1})`

两次调用都继续经过现有只允许 `read_file("fixture.txt")` 的严格测试白名单；T2 只增加既有 `startLine=1/endLine=1` 参数，没有扩大 action、path、工具权限或生产能力。实现只修改 H4 隔离上游与 Playwright smoke，没有修改生产代码、协议、Session JSONL、持久化或 fixture 内容。

## 2. 第二工具执行闸门

新增固定测试闸门 `before-second-tool-execute`，仅在带 `startLine=1/endLine=1` 的 H4-6C T2 调用中生效。启动期工具边界 probe 和 T1 均不会进入该闸门。

闸门位于生产 AgentRun 已写入 T2 `tool_started`、但测试包装器尚未委托 `original_execute_registered_tool` 的边界。闸门达到时同时证明：

- T1 execution 已为 `completed/succeeded`，T2 为 `running`；
- 事件前缀严格为 `created → model_started → model_completed → tool_started(T1) → tool_completed(T1) → tool_started(T2)`；
- 上游 chat 为 1，生产工具委托为 1；
- 页面只有一个工具组，组内恰好两个工具项，顺序为 T1→T2；T1 已有唯一结果，T2 只有参数、尚无结果。

释放闸门后，T2 只委托生产执行器一次。第二轮终答继续复用 `before-tool-final-delta` 与 `before-tool-terminal`，因此正文 delta 和 terminal/stop 仍由现有确定性闸门控制，没有增加第二套测试状态机。

## 3. AgentRun、回执与 Session 闭合

完成态 AgentRun 固定为 11 事件：

`created → model_started → model_completed → tool_started(T1) → tool_completed(T1) → tool_started(T2) → tool_completed(T2) → model_pending → model_started → model_completed → completed`

`pendingToolCalls` 为空，终态请求计数为 AgentRun POST 1、Runtime POST 0、chat 2、生产工具执行 2。第一轮 Runtime 已完成，第二轮 Runtime 承担最终回答；随机 Run、Runtime 与 toolCall ID 只用于单场景内身份配对，不冻结为跨运行基线。

fixture 只有一行，因此两次读取的正文可以相同；测试不靠制造不同内容区分调用，而是按各自 toolCallId、agentRunId、arguments 和原始 receipt 精确闭合：

- T1：参数仅含 `path=fixture.txt`，result 为 `lineRange=null`、`size=26`、`truncated=false`；
- T2：参数另含 `startLine=1/endLine=1`，result 为 `lineRange={start:1,end:1}`、`size=26`、`truncated=false`；
- 两次 result 都保持受控文件内容，并分别只对应自己的 tool-call/tool-result 对。

Session 角色链固定为：

`user → assistant → tool-call(T1) → tool-result(T1) → tool-call(T2) → tool-result(T2) → assistant`

刷新前后，两对工具消息的 toolCallId、agentRunId、arguments、result、lineRange、size 和 truncated 均保持，声明顺序、执行顺序、结果顺序一致。

## 4. DOM 生命周期、刷新与零重执行

运行中页面始终只有一个工具组和两个工具项，顺序为 T1→T2。用户真实展开外层工具组后，释放第二工具闸门；T2 结果进入生产投影并触发重绘时，`data-tool-process-key`、T1→T2 顺序及 open 状态保持，没有产生第二工具组、重复项或重复结果。继续释放终答正文与 terminal 闸门后，前端终态收敛使父 execution trace、工具组和两个单项恢复默认折叠。

完成态通过真实用户点击按父 trace→工具组→T1/T2 展开，两个参数和格式化结果分别可见，再按反向顺序折叠。刷新场景在完整 reload 前曾展开这四层；经生产 Session 恢复链重载后，父 trace、工具组、T1 与 T2 均默认折叠，再次展开仍保持单组双项、T1→T2 和详情唯一。

刷新前后 AgentRun、toolCall、11 事件、Session 投影、稳定 process key 与 DOM 语义一致；刷新增量 AgentRun POST、Runtime POST、chat、工具执行全部为 0。

## 5. 前端异步收敛窗口

首轮定向运行确认服务端闸门已经闭合 T1 completed、T2 running 与六事件前缀时，浏览器端仍可能处于事件消费到 DOM 投影的短暂异步窗口。H4-6C 随后只在采集稳定语义快照前，用 Playwright 对既有 DOM 信号做自动等待：单工具组、双工具项、T1 succeeded 且有唯一结果、T2 running 且无结果。

该适配没有使用 sleep、手写 retry、额外超时，没有放宽结果计数或跳过 T1 result，也没有修改生产逻辑。它只避免把瞬时未收敛状态写入稳定哈希。自动证据证明的是节点、状态、顺序、身份和唯一性；它不能证明人眼感知的整片闪烁、布局跳动、滚动抖动已经解决。

## 6. 固定语义哈希

H4-6C 固定以下不含随机 ID、时间、端口、原始记录字节或完整 HTML 的 SHA-256：

- lifecycle：`f5445145789b337ffba49dcec350a483981be281d52e9144f23fefd8cde3307d`
- refreshLifecycle：`9421bf68cdb674d5dff228bb173db82772af2806f9881f52437d60b763e673de`
- eventProjection：`6e81cc9ad5662a25862ffd3384de2d53481d75e427695391eedd4e8a7aac1342`
- receiptProjection：`35e8de4147a9991325091f30dedb701ab0676979af6db122ccee9ed3e56042c1`
- sessionRoleContent：`033743ab31d1b95e7e33aefc1c74515a01cc2fb65cebd4830b2099f2c6a4e2f7`
- sessionToolMeta：`23956f1cd5fdb148e94f6c224e7dff3326ec0e4f6aff01342512fa9fc8ab842e`
- activeDom：`3fd7fd4774195b01136297bb63f88e348b18eac5fac40ace73ffe8f88c1ca0d0`
- terminalDom：`9efb0070a8125ede3c69abf4f4c530ac5076979d480febd63d5df7a7230753cb`

H4-6A/H4-6B 的六个既有领域哈希保持原值：lifecycle `de27ce93297dad0a99c9215080d8ffd891d893ad30a2ed88884ecbeaeff31487`、refreshLifecycle `0712a70b1ad23f9d33ab31b780df8c48deebbeaae784e80a4976daf0e7452ec8`、eventProjection `36658361b00ce7bff3f3464099e27fe81273845e2ab85a62c0229814128b9d48`、sessionRoleContent `c6b7c90baeafb1c29e38d431bdbaf28a1ca282d54d47ac2d024601ad3d3e442a`、sessionToolMeta `587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9`、terminalDom `71a1ebdf6f609fc44a8408f20d15659626e8b6d11bf033b3665be510bf470712`。

## 7. 验证结果

- 场景 A/B 在哈希冻结前后各 `1 passed`；
- H4 infra 自检通过；
- 连续两轮标准 `npm run test:h4:e2e` 均为 `19 passed`、零 retry，Playwright 为 54.7/53.7 秒，完整命令为 62.8/61.8 秒；
- H4-6A/H4-6B 既有四场景为 `4 passed`，六个领域哈希不变；
- 既有多工具 AgentRun 定向为 `2 passed`；
- 前端/P0 为 `199 passed`；
- 完整 Python 回归为 `1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check`、H4 子进程/端口/临时根/output 清理均通过。

收口文档完成后仅复跑 H4-6C A/B、H4-6A/H4-6B 四场景和 infra；两个测试文件哈希不变时，上述两轮标准 H4、前端/P0、完整 Python 与前端构建结果按同一实现/测试输入沿用。

## 8. 完成边界与回退

本阶段只证明默认 bundle、同一模型轮两个成功的受限 `read_file`、真实工具组生命周期、T1→T2 顺序、运行中重绘保持展开、终态折叠，以及同进程刷新默认折叠与零重执行。它不覆盖 classic 多工具、异构 action/path、工具失败、取消、长输出、跨进程 active 恢复、工具外部副作用 exactly-once、问卷/授权、压缩、图片、队列/并行/Child，也不证明主观视觉闪烁、布局跳动或滚动体验已经通过。

独立回退只需撤销 `tests/e2e/h4/isolated_host.py`、`tests/e2e/h4/smoke.spec.cjs` 的 H4-6C 增量及本阶段收口文档；不涉及生产回退、数据迁移或协议兼容动作。
