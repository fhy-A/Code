# H4-6F direct classic `read_file` 参数校验失败对等

## 1. 阶段结论

H4-6F 只修改 Playwright smoke，把 H4-6E 的参数校验失败生命周期和完成态刷新流程参数化为 bundle/classic 共用 helper，并新增两条 direct classic 真实 Chromium 场景：

- `classic invalid read_file arguments fail before execution and complete with final answer`
- `completed classic invalid read_file receipt reloads uniquely without execution`

classic 通过 `/dist/frontend/index.classic.html` 直接进入生成页，精确断言 `data-frontend-runtime="classic-fallback"`、不存在 `data-code-frontend-ready`，URL 没有 fallback query。该入口不是 H4-4 的 `bundle-load`/`bundle-init` 自动故障降级，也没有注入 bundle 加载故障。

本阶段没有修改隔离 host、生产代码、AgentRun/Runtime/Session 协议、JSONL、工具 registry、action/path 白名单或 H4 配置。bundle 与 classic 复用同一固定上游分支、两个既有工具终答闸门及生产 AgentRun/Runtime/Session/DOM 链，没有建立 classic 专属状态机。

## 2. 生产失败语义与身份闭合

两种入口都使用 `read_file({"path":"fixture.txt","unexpected":true})`。`path` 合法，生产 schema 在执行器前以唯一 `additional_property` 拒绝 `unexpected`；它不是文件系统失败或工具执行器失败，H4 wrapper 没有主动抛错。

固定失败投影为 `errorCode=invalid_tool_arguments`、`failureCount=1`、`fieldErrors=[{field:"unexpected",reason:"additional_property"}]`。错误 message 只检查结构和非空，不冻结完整英文或本地化文案。`productionToolDelegations=0`、`toolExecutions=[]`、`unsafeToolRequests=0` 证明生产 `execute_registered_tool` 没有被委托。

父 Run 将失败回执送入第二轮固定模型回答并正常 completed。两种入口均闭合：

- 九事件：`created → model_started → model_completed → tool_started → tool_completed(failed) → model_pending → model_started → model_completed → completed`；
- `nextCursor=9`、耐久 `nextSeq=10`、`pendingToolCalls=[]`；
- AgentRun POST 1、Runtime POST 0、上游 chat 2、生产工具委托 0；
- 两个 Runtime 活动态 cursor 为 `4/0`，终态为 `4/3`；
- Session 角色链为 `user → assistant → tool-call → tool-result → assistant`，tool-call/result 以同一 toolCallId、agentRunId、arguments 和失败 result meta 闭合。

## 3. DOM 生命周期与刷新唯一性

终答正文释放前，工具组为 running、唯一工具项为 failed；用户真实展开后能看到唯一的合法 path、`unexpected` 字段和非空失败详情。终答正文进入生产投影、terminal 尚未释放时，工具组转为 failed，真实 DOM 重绘后 `data-tool-process-key` 和 open 状态保持。

服务端九事件终态闭合后，浏览器继续等待前端 banner 消失、stop 禁用、active trace 归零和 completed trace 唯一，再证明父 trace completed、工具组/单项 failed 且默认折叠。用户仍可按父 trace→工具组→单项逐层真实展开查看参数和失败详情。

完成态完整 reload 后，classic 再次从同一 direct classic 路径进入，并通过生产 Session 恢复链打开同一会话；不注入私有 state 或 localStorage。AgentRun、toolCall、九事件、失败回执、Session meta、process key 和 DOM 顺序保持唯一，父 trace/工具组/单项恢复默认折叠；刷新后的 AgentRun POST、Runtime POST、chat 和生产工具执行增量均为 0。

## 4. bundle/classic 八类语义哈希对等

入口 runtime 标记和页面路径单独断言，不进入领域哈希。classic 直接匹配 H4-6E bundle 的同一八类 SHA-256，没有新增或重基线 classic 期望：

- eventProjection：`860e9f45fe924f5a8a94ca031d2839264fd550dfcbef0c4a9a1bb89393bd6ef4`
- invalidReceiptProjection：`bf4ec29db9ac54505687e3fb3c2040ff5f4fa17aed715700c958317a3aa6c776`
- modelToolReceiptProjection：`1b94536a4cc63c2bc3b98c54eb14c329ac585b5ec65bf85c1ca7bbd080ab6c80`
- sessionRoleContent：`cbdcb15dad4b61b34bdf89556131827fc7fd973f88b9b9368e329bf61b1821fb`
- sessionToolMeta：`c62eca9c84fb4d3c94968c2423f8db13cff6ca254fd90eba9bb225c87d438285`
- activeDom：`3f718cb47d5fb90dcdc0bbc3a425718a43f1c0fe6ee082ce53e90a22cabc2ad4`
- terminalDom：`4cdf1271fd50f4060b985a2c9b579bad19b075e0b562881337cd2ddab42b161d`
- refreshLifecycle：`04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4`

H4-6A/H4-6B 六类旧哈希、H4-6C/H4-6D 八类旧哈希及 H4-6E bundle 八类哈希均保持原字面值。

## 5. 验证与历史外层超时

实现期的 bundle 两例、classic 活动态、classic 刷新态及四例合并均通过。首次标准矩阵第 1 轮为 `25 passed`；随后第 2 轮使用 120 秒外层命令执行预算时，在约 124.1 秒由外层执行器以 exit 124 截断，既没有 Playwright 完成摘要，也没有可保留的最后测试阶段。该轮不计为通过，也不判定为产品通过或产品失败；当时 H4 子进程、临时根和 output 最终归零。

补证据阶段只把外层 shell 预算提高到 240 秒，让完整命令有足够时间返回；Playwright 单 worker、`retries=0`、测试 timeout、host 5 秒控制命令上限、stop-time metrics 和严格清理门禁均未改变。相同 smoke SHA-256 下重新连续取得：

- 两轮标准 `npm run test:h4:e2e` 均为 `25 passed`、exit 0、零 retry，完整命令为 85.8/85.6 秒；
- H4-6A～H4-6D 八例与 H4-6E bundle 两例合计 `10 passed`，32.6 秒，旧哈希保持；
- `test_agent_rejects_invalid_tool_arguments_without_calling_executor` 为 `1 passed`；
- 前端模块/P0 为 `199 passed`；
- 完整 Python 回归为 `1113 passed, 739 subtests passed`，85.18 秒；
- `npm run check:frontend`、Node 语法、`git diff --check` 及 H4 子进程、端口、临时根和 output 清理均通过。

## 6. 完成边界与独立回退

本阶段只证明 direct classic 对同一“合法 path + 唯一额外字段”生产 `additional_property` schema 拒绝、失败回执进入第二轮、父 Run completed、真实失败 DOM 生命周期及同进程刷新零执行，与 H4-6E bundle 语义对等。

它不覆盖自动 bundle fallback 后的失败任务、缺少 path、JSON parse、文件系统/执行器失败、重复失败限流、取消、长输出、异构工具、跨进程 active 恢复或工具副作用 exactly-once。

独立回退只需撤销 `tests/e2e/h4/smoke.spec.cjs` 的 runtime 参数化和两条 classic 变体，以及本阶段收口文档；不涉及 host 或生产回退、数据迁移或协议兼容动作。
