# H4-6K 相同 `read_file` 失败限流与强制终答

## 完成范围

H4-6K 只修改测试侧，在默认 bundle 与 direct classic 中复用 H4-6G 的固定 schema-valid 只读失败调用：

```json
{"path":"fixture.txt","startLine":2,"endLine":1}
```

该调用通过 JSON 解析与 schema 校验，并真实进入 `execute_registered_tool → execute_read_file_tool`，随后因 `endLine < startLine` 在生产执行器内部失败。生产重复身份由工具名与规范 arguments 指纹确定，不含 `toolCallId`；连续失败还要求 `errorCode` 与规范化错误文本签名一致。解析和 schema 校验发生在重复失败限流之前，因此 H4-6E、H4-6I 与 H4-6J 的执行前失败不触发本限流。

## 确定时间线与计数

同一规范调用使用四个唯一 toolCallId：

1. 前三次均真实委托生产执行器并失败，`failureCount` 依次为 1、2、3；第三次结果带 `retryLimitReached=true`。
2. 第四次模型以新 toolCallId 声明同一 action 与规范 arguments，生产以 `repeated_tool_failure`、`failureCount=3`、`retryBlocked=true` 阻断，并产生唯一 `tool_retry_blocked` 事件；该次没有进入执行器。
3. 第五轮模型请求不再携带 `tools` 或 `tool_choice`，并包含脱敏恢复指令事实；固定终答后父 AgentRun 进入 completed，`errorCode`、`forceFinalRound` 与 pending 状态均清空。

真实闭合计数为：

- 25 个 AgentRun 事件，`nextCursor=25`，耐久 `nextSeq=26`；
- 五个 Runtime 的 cursor 向量为 `[4,3,3,3,3]`；
- 模型请求 5 次；
- 生产工具委托与真实执行各 3 次；
- 耐久 execution 4 条；
- `tool_retry_blocked` 1 次；
- unsafe 请求 0 次。

Session 精确保存四对 `tool-call → tool-result`，并以 toolCallId、agentRunId、规范 arguments 与结果逐对闭合。UI 始终只有一个工具组和四个 failed 项，声明、执行、结果顺序与活动态/终态开合均稳定；完整 reload 后 AgentRun、Runtime、Session、工具结果与 DOM 保持唯一，AgentRun POST、Runtime POST、chat 与真实工具执行四项增量均为 0。

## DOM 与耐久机器事实的边界

DOM 只冻结用户真实可见的失败语义：前三项均可见 `startLine`/`endLine` 行范围失败，第四项可见同一调用连续三次失败后已被阻断且不应继续重复。`action`、`failureCount`、`retryLimitReached`、`retryBlocked` 与 `repeated_tool_failure` 仍由 AgentRun execution/event、第二轮及后续模型 tool receipt 和 Session meta 严格断言；本阶段不宣称这些机器字段会逐字显示在 DOM。

首次 bundle 取证曾因测试要求上述机器字段以字面 JSON 出现在页面而失败。该失败不计通过；修订只把 DOM 投影收窄到既有用户可见语义，未删除或放宽 AgentRun、模型回执和 Session meta 的机器字段断言，也没有修改生产、超时、worker、retry 或清理门禁。更早的沙箱内 Chromium `spawn EPERM` 没有进入产品路径，同样不计产品结果。

## 稳定语义哈希

以下 SHA-256 排除了随机 ID、时间、端口、完整错误文案、原始 JSONL、完整 HTML 与前端入口标记；bundle 与 direct classic 完全一致：

- `eventProjection`: `1d02e735ad701d3394a2dae9eec019d4d22e97fb6fb111de1b90eaf09096aa07`
- `retryExecutionProjection`: `c4f4a8432ad9be01f331e72be1c9b6bd709bb7eda508c3b00604a2967d8c31fe`
- `modelToolReceiptProjection`: `4d02940043fc3266a6e6bf6e2a94ab7e775dd539401e84f40255daa29ed1b721`
- `forcedFinalProjection`: `30387bd58028a9ceef0f9d0cae7b9421c283570773270c995cf972e60e088ced`
- `runtimeProjection`: `cfe81b1df3da02903778c0c761e9efed2ce3464788c50d7d0af5231517315c1c`
- `sessionRoleContent`: `b9a2d2b56e618c0b939b4bd29690bcf20580cba69954aaf8cf704dd31f1367a2`
- `sessionToolMeta`: `76c4d8cfbc85aefd48242eedea1a13b66314430e17860a837b345142e7e6b211`
- `terminalDom`: `062793b9555a641084d28f70b8b3028af45ed40847f60ac547222c85dcba36f7`
- `refreshLifecycle`: `ae09c60e831dec8ffd7295e9baef598b898a1061ac85250d61e2e1936cc6fc44`

## 验证

- bundle 在哈希固化前、固化后及 direct classic 定向均通过；
- H4 infrastructure：通过；
- 标准 H4 连续两轮：各 `35 passed`、单 worker、`retries=0`、exit 0；
- H4-6A～J 既有工具场景：`20 passed`，旧哈希保持；
- 重复失败生产定向：`3 passed`；
- 前端/P0：`199 passed`；
- 完整 Python：`1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源清理：通过。

文档收口只复验 H4-6K bundle/direct classic、三个重复失败生产定向、正式 infra、语法与 diff；在两份实现哈希不变的前提下，沿用上述同实现文件形态的完整矩阵结果。

## 证明边界与回退

本阶段只证明合成 fixture 上同一 schema-valid、只读行范围失败的三次真实执行、第四次阻断、第五轮强制终答，以及默认 bundle/direct classic 的同进程终态刷新零重执行。它不覆盖执行前 schema/parse 失败限流、不同参数或工具、错误交替、强制终答失败分支、跨进程 active、取消、长输出或真实外部副作用 exactly-once。

独立回退只需撤销 `tests/e2e/h4/isolated_host.py`、`tests/e2e/h4/smoke.spec.cjs` 的 H4-6K 测试增量及本专题/事实源更新；不涉及生产回退、数据迁移或协议兼容动作。
