# H4-6B direct classic 工具详情对等

## 1. 阶段结论

H4-6B 在隔离 Chromium 中为 direct classic fallback 补齐与 H4-6A 默认 bundle 相同的单只读工具详情生命周期证据。两条 H4-6A 流程被整理为按 runtime 参数驱动的共享 helper；classic 通过 `h4.open("classic")` 直接进入生成页，精确核对 `data-frontend-runtime="classic-fallback"`，且不存在 bundle ready 标记。本阶段不是 bundle 加载失败后的自动降级测试。

两条既有 bundle 场景的名称、断言和六个领域语义哈希保持不变；两条 classic 变体复用相同的生产 `app.js`、`agent-runtime.js`、Session/AgentRun/Runtime 恢复链、`before-tool-final-delta` 与 `before-tool-terminal` 双闸门，以及唯一 `read_file("fixture.txt")` 工具调用。没有为 classic 复制第二套工具或刷新状态机，也没有修改生产代码、协议、JSONL、持久化或 H4 host。

## 2. direct classic 活动态与终态

classic 活动态与 bundle 使用同一事实闭合：

- 工具结果出现后外层工具组初始 closed，用户真实展开；
- 第二轮终答正文 delta 触发生产 DOM 节点替换后，同一 `data-tool-process-key=0:1` 与 open 状态保持，工具动作、参数和结果没有重复；
- AgentRun 精确状态为 `model`，第二条 `model_started.runtimeRunId`、`activeRuntimeRunId` 与第二个 Runtime 身份一致；第一轮 Runtime 为 `completed(cursor 4)`，第二轮为 `running(cursor 0)`；
- 服务端随后闭合为 completed 九事件链，前端 banner、stop、active/completed trace 四项终态信号闭合后，工具组自动折叠；
- 用户按 completed execution trace → 工具组 → 单工具详情的真实层级展开，可看到 `read_file`、`fixture.txt`、`26 B` 与恰好一份受控结果，再按相反顺序逐层折叠。

事件顺序继续固定为：

`created → model_started → model_completed → tool_started → tool_completed → model_pending → model_started → model_completed → completed`

## 3. 刷新、唯一性与零重执行

classic 完成态刷新场景先由用户展开父 trace、工具组和单项，再执行完整 reload，并经生产 Session 恢复链打开同一会话。刷新后三层均恢复默认折叠，重新展开仍可查看唯一内容；展开偏好仍是页面瞬时状态，不写入 Session。

刷新前后保持同一 AgentRun、toolCall、九事件、Runtime 轮次、Session 角色链 `user → assistant → tool-call → tool-result → assistant`、稳定工具 key 与 DOM 语义。user、阶段说明、tool-process、tool result 和最终回答各一次且顺序不变；刷新增量 AgentRun POST、Runtime POST、上游 chat、工具执行均为 0。

## 4. 固定领域哈希与验证

classic 与 bundle 共同通过 H4-6A 的六个稳定语义 SHA-256：

- lifecycle：`de27ce93297dad0a99c9215080d8ffd891d893ad30a2ed88884ecbeaeff31487`
- refreshLifecycle：`0712a70b1ad23f9d33ab31b780df8c48deebbeaae784e80a4976daf0e7452ec8`
- eventProjection：`36658361b00ce7bff3f3464099e27fe81273845e2ab85a62c0229814128b9d48`
- sessionRoleContent：`c6b7c90baeafb1c29e38d431bdbaf28a1ca282d54d47ac2d024601ad3d3e442a`
- sessionToolMeta：`587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9`
- terminalDom：`71a1ebdf6f609fc44a8408f20d15659626e8b6d11bf033b3665be510bf470712`

参数化后两条 bundle 定向场景通过，随后两条 classic 定向场景通过；连续两轮标准 `npm run test:h4:e2e` 均为 `17 passed`、零 retry，Playwright 分别为 58.5/57.3 秒，完整命令为 66.8/65.5 秒。前端/P0 为 `199 passed`；完整 Python 回归为 `1113 passed, 739 subtests passed`；`npm run check:frontend`、Node 语法、`git diff --check` 和 H4 资源清理均通过。

## 5. 完成边界与回退

本阶段只证明 direct classic fallback、单 `read_file("fixture.txt")`、运行中重绘保持展开、前端终态自动折叠、完成态三层真实交互，以及同进程完整刷新后的默认折叠与零重执行。它不证明自动 bundle 故障降级后的工具任务，也不覆盖多工具、失败/取消、长输出、问卷/授权、压缩、图片、队列/并行/Child、跨进程 active 恢复或工具副作用 exactly-once。

独立回退只需撤销 `tests/e2e/h4/smoke.spec.cjs` 的 H4-6B 参数化/两条 classic 变体及本阶段收口文档；不涉及生产回退、数据迁移或协议兼容动作。
