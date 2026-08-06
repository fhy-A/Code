# H4-6A 工具详情展开、终态折叠与刷新唯一性

## 1. 阶段结论

H4-6A 在隔离 Chromium 中补齐默认 bundle、单个受限 `read_file("fixture.txt")` 的真实工具详情生命周期证据。测试侧为合成上游增加 `before-tool-final-delta` 与 `before-tool-terminal` 两个固定闸门，并在既有 H4 Playwright 场景中驱动真实 DOM；生产代码、AgentRun/Runtime/Session 协议、JSONL 和持久化实现均未修改。

两条场景分别证明：运行中用户展开的工具组在第二轮终答正文触发的真实重绘后保持展开，并在前端终态收敛后自动折叠；完成态曾手动展开三层后完整刷新，父级 execution trace、工具组和单工具详情均恢复默认折叠，重新展开仍能查看唯一、完整的参数与结果，且不会重新创建 Run、模型请求或工具执行。

## 2. 活动态与 Runtime 身份闭合

合成上游的第一轮模型声明唯一 `read_file("fixture.txt")`，工具结果完成后进入第二轮模型：

- 外层 `details.tool-process-stage` 初始为 closed，工具组、tool-call、tool-result 与 `data-tool-process-key` 各唯一；
- 用户真实点击展开外层工具组后，释放终答正文闸门；唯一终答 delta 触发生产消息区域真实 DOM 节点替换，同一 `data-tool-process-key=0:1` 与 `open` 状态保持，动作、路径和结果没有重复；
- 此时 AgentRun 精确状态为 `model`，事件前缀为 `created → model_started → model_completed → tool_started → tool_completed → model_pending → model_started`；
- 第二条 `model_started.runtimeRunId`、AgentRun `activeRuntimeRunId` 和控制面第二个 Runtime ID 三者一致；第一轮 Runtime 已 `completed(cursor 4)`，第二轮 Runtime 仍为 `running(cursor 0)`。

DOM 格式化结果与原始工具回执分层验证：浏览器结果文本包含 `fixture.txt`、`26 B` 和恰好一份受控正文；AgentRun `tool_completed`、`toolExecutions[].result` 以及 Session `tool-result.meta.result` 继续按原始结构严格等值，不把格式化 HTML 文本当成耐久 receipt。

## 3. 终态收敛与真实操作层级

释放 terminal 闸门后，测试先独立核对服务端 AgentRun：状态为 `completed`、`nextCursor=9`、`activeRuntimeRunId` 为空，事件顺序固定为：

`created → model_started → model_completed → tool_started → tool_completed → model_pending → model_started → model_completed → completed`

服务端 terminal 早于前端完成收敛属于正常窗口。测试随后等待四个现有前端事实同时闭合：active banner 消失、stop 按钮禁用、active execution trace 数量为 0、completed execution trace 数量为 1；只有之后才单次读取工具 DOM，并证明外层工具组和单工具详情均已自动折叠。完成统述 `Worked for` 的出现本身不作为前端终态信号。

完成态的真实用户操作具有三层层级：completed execution trace 默认折叠，先点击唯一直接 `[data-execution-trace-toggle]`，核对 `is-expanded` 与 `aria-expanded`；再依次展开工具组和单工具详情，查看 `read_file`、`fixture.txt` 与格式化结果；最后按单项、工具组、父 trace 的反向顺序逐级折叠。测试没有使用 force click、DOM `evaluate()` 点击、CSS 可见性规避或序号选择器掩盖重复节点。

## 4. 刷新、持久化与零重执行

第二条场景在完成态手动展开父 trace、工具组与单项，然后执行完整页面 reload，并通过生产 Session 列表和恢复链重新打开同一 Session。刷新后三层均恢复默认折叠，说明展开偏好是页面瞬时状态，不写入 Session；用户仍可按相同层级重新展开并看到原内容。

刷新前后保持：

- Session 角色链为 `user → assistant → tool-call → tool-result → assistant`；
- toolCallId、agentRunId、九事件、工具结果、`data-tool-process-key` 和 DOM 语义一致；
- user、阶段说明、tool-process、tool-result 与最终回答各一次且有序；
- 刷新增量为 AgentRun POST 0、Runtime POST 0、上游 chat 0、工具执行 0。

## 5. 固定语义哈希

下列 SHA-256 只覆盖无随机 ID、无时间的稳定语义投影：

- lifecycle：`de27ce93297dad0a99c9215080d8ffd891d893ad30a2ed88884ecbeaeff31487`
- refreshLifecycle：`0712a70b1ad23f9d33ab31b780df8c48deebbeaae784e80a4976daf0e7452ec8`
- eventProjection：`36658361b00ce7bff3f3464099e27fe81273845e2ab85a62c0229814128b9d48`
- sessionRoleContent：`c6b7c90baeafb1c29e38d431bdbaf28a1ca282d54d47ac2d024601ad3d3e442a`
- sessionToolMeta：`587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9`
- terminalDom：`71a1ebdf6f609fc44a8408f20d15659626e8b6d11bf033b3665be510bf470712`

## 6. 验证、边界与回退

最终测试文件形态下，场景 A/B 在哈希冻结前后各 `1 passed`；infra 自检通过；连续两轮标准 `npm run test:h4:e2e` 均为 `15 passed`、零 retry，完整命令分别为 52.1/50.1 秒。前端/P0 为 `199 passed`；完整 Python 回归为 `1113 passed, 739 subtests passed`；`npm run check:frontend`、Node/Python 语法、`git diff --check` 以及子进程、端口、临时根和 Playwright output 清理均通过。

本阶段只证明默认 bundle、单只读工具、当前页面手动展开、运行中生产重绘保持、终态自动折叠、同进程完整刷新默认折叠与零重执行。不覆盖 classic、多工具、失败/取消、长输出、队列/后台/Child、跨刷新持久化展开偏好、跨进程 active 恢复或工具副作用 exactly-once。

回退只需撤销 `tests/e2e/h4/isolated_host.py`、`tests/e2e/h4/smoke.spec.cjs` 的 H4-6A 增量和本阶段收口文档；不涉及生产回退、数据迁移或协议兼容动作。
