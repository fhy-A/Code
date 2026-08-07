# H4-6D direct classic 同轮双工具对等

## 1. 阶段结论

H4-6D 只参数化 H4-6C 已有的同轮双工具 Playwright 流程，为 direct classic 新增活动态与完成态刷新两条真实 Chromium 变体。classic 通过 `h4.open("classic")` 直接进入生成页，精确核对 `data-frontend-runtime="classic-fallback"`，且不存在 `data-code-frontend-ready`；本阶段不是默认入口发生 bundle 故障后的自动降级测试。

两条 classic 变体继续复用同一 `MULTI_TOOL_USER`、两个受限 `read_file("fixture.txt")`、`before-second-tool-execute`、`before-tool-final-delta`、`before-tool-terminal` 三个既有闸门，以及相同的生产 AgentRun、Runtime、Session 和 DOM 链。没有增加 host 场景、工具 action/path 白名单、协议、持久化字段或生产逻辑，也没有复制 classic 专属状态机。

## 2. AgentRun、工具回执与 Session 顺序

活动态和终态均闭合到单一 AgentRun、两个 Runtime 和两个 toolCall。第一轮按 T1→T2 声明并执行：

- T1：`read_file({"path":"fixture.txt"})`
- T2：`read_file({"path":"fixture.txt","startLine":1,"endLine":1})`

完成态 AgentRun 固定为 11 个事件：

`created → model_started → model_completed → tool_started(T1) → tool_completed(T1) → tool_started(T2) → tool_completed(T2) → model_pending → model_started → model_completed → completed`

请求和执行计数固定为 AgentRun POST 1、Runtime POST 0、上游 chat 2、生产工具执行 2。Session 角色链固定为：

`user → assistant → tool-call(T1) → tool-result(T1) → tool-call(T2) → tool-result(T2) → assistant`

两对 tool-call/tool-result 分别通过 toolCallId、agentRunId、arguments 与 receipt 的 lineRange、size、truncated、result 闭合；声明、执行和结果顺序均为 T1→T2。随机 Run、Runtime 与 toolCall ID 只用于场景内身份同一性，不作为跨运行哈希输入。

## 3. DOM 生命周期与刷新零重执行

classic 活动态始终只有一个工具组和两个工具项，顺序为 T1→T2。用户真实展开工具组后，T2 结果和第二轮正文进入生产投影所触发的 DOM 重绘仍保持同一 `data-tool-process-key` 与 `open` 状态，没有第二工具组、重复项或重复结果。前端终态收敛后，父 execution trace、工具组和两个单项按既有规则折叠；用户仍可通过真实点击逐层展开并查看两项参数和格式化结果。

完成态刷新场景在 reload 前真实展开父 trace、工具组与 T1/T2；经生产 Session 恢复链重载后，四层均恢复默认折叠，再次展开仍保持单组双项、T1→T2 和详情唯一。刷新增量 AgentRun POST、Runtime POST、chat、工具执行全部为 0，AgentRun、事件、回执、Session 与 DOM 语义保持不变。

## 4. 与 bundle 对等的固定语义哈希

direct classic 精确匹配 H4-6C 默认 bundle 的八类稳定 SHA-256：

- lifecycle：`f5445145789b337ffba49dcec350a483981be281d52e9144f23fefd8cde3307d`
- refreshLifecycle：`9421bf68cdb674d5dff228bb173db82772af2806f9881f52437d60b763e673de`
- eventProjection：`6e81cc9ad5662a25862ffd3384de2d53481d75e427695391eedd4e8a7aac1342`
- receiptProjection：`35e8de4147a9991325091f30dedb701ab0676979af6db122ccee9ed3e56042c1`
- sessionRoleContent：`033743ab31d1b95e7e33aefc1c74515a01cc2fb65cebd4830b2099f2c6a4e2f7`
- sessionToolMeta：`23956f1cd5fdb148e94f6c224e7dff3326ec0e4f6aff01342512fa9fc8ab842e`
- activeDom：`3fd7fd4774195b01136297bb63f88e348b18eac5fac40ace73ffe8f88c1ca0d0`
- terminalDom：`9efb0070a8125ede3c69abf4f4c530ac5076979d480febd63d5df7a7230753cb`

H4-6A/H4-6B 的六类旧哈希也保持原值：lifecycle `de27ce93297dad0a99c9215080d8ffd891d893ad30a2ed88884ecbeaeff31487`、refreshLifecycle `0712a70b1ad23f9d33ab31b780df8c48deebbeaae784e80a4976daf0e7452ec8`、eventProjection `36658361b00ce7bff3f3464099e27fe81273845e2ab85a62c0229814128b9d48`、sessionRoleContent `c6b7c90baeafb1c29e38d431bdbaf28a1ca282d54d47ac2d024601ad3d3e442a`、sessionToolMeta `587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9`、terminalDom `71a1ebdf6f609fc44a8408f20d15659626e8b6d11bf033b3665be510bf470712`。

## 5. 验证结果

- 参数化后的 bundle H4-6C 两例为 `2 passed`，classic 活动态和刷新态分别为 `1 passed`、`1 passed`；
- H4 infra 通过；
- 连续两轮标准 `npm run test:h4:e2e` 均为 `21 passed`、零 retry，完整命令约为 69.7/69.2 秒；
- H4-6A/H4-6B 既有四例为 `4 passed`，bundle H4-6C 再验证为 `2 passed`；
- 既有多工具 AgentRun 定向为 `2 passed`；
- 前端/P0 为 `199 passed`；
- 完整 Python 回归为 `1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node 语法、`git diff --check` 与 H4 子进程、端口、临时根和 output 审计均通过。

验证过程中曾有一条带首尾锚点的 `--grep` 未匹配 Playwright 完整标题，结果为 `No tests found`；该命令没有启动浏览器 case，也不计入产品失败或通过轮次。随后使用唯一标题子串执行对应 classic 场景并通过。

## 6. 完成边界与独立回退

本阶段只证明 direct classic、同一模型轮两个成功受限读取、真实工具组生命周期、T1→T2 顺序，以及同进程完整刷新后的默认折叠与零重执行。它不覆盖自动 bundle 故障降级后的工具任务、工具失败/取消/长输出、异构工具、跨进程 active 恢复、工具外部副作用 exactly-once，也不构成人眼主观闪烁、布局跳动或滚动体验验收。

独立回退只需撤销 `tests/e2e/h4/smoke.spec.cjs` 的 H4-6D 参数化与两条 classic 变体，以及本阶段收口文档；不涉及生产回退、数据迁移或协议兼容动作。
