# H4-6P forced-final 不可用工具响应终态与零执行

## 完成范围

H4-6P 只冻结一个既有生产分支：固定 schema-valid、只读 `read_file` 行范围调用

```json
{"path":"fixture.txt","startLine":2,"endLine":1}
```

使用不同 `toolCallId` 连续声明同一工具名与完全相同的规范 arguments。前三次调用真实委托生产执行器并因 `endLine < startLine` 失败，`failureCount` 依次为 1、2、3，第三次带 `retryLimitReached=true`；第四次同指纹调用形成耐久 blocked execution 与唯一 `tool_retry_blocked`，但不再委托执行器。第五轮 forced-final 请求移除 `tools` 与 `tool_choice`，并携带既有“相同工具调用已阻断”的恢复指令。

隔离假上游在第五轮仍返回一个确定的 `read_file` 工具调用。生产 Runtime 正常解析该模型响应并记录 `model_completed`，但 forced-final 分支不接受它作为可用终答：该工具调用只停留在模型完成层证据（第五 Runtime result 与 AgentRun `model_completed`），绝不进入 pending、耐久 execution、`tool_started`、`tool_completed`、`tool_retry_blocked`、生产工具委托或执行器。父 AgentRun 最终以 `failed/repeated_tool_failure` 闭合。H4-6P 没有修改生产限流算法、工具协议、持久化格式、UI 或恢复策略，只用根测试和 bundle/direct classic H4 冻结现有行为。

## AgentRun、Runtime 与执行链证据

- AgentRun 共 25 个事件，`nextCursor=25`，耐久 `nextSeq=26`；末尾精确为第五轮 `model_completed → failed`。最终 snapshot 为 `status=failed`、`errorCode=repeated_tool_failure`、`forceFinalRound=false`、`pendingToolCalls=[]`，活动 Runtime 引用清空。
- 五个 Runtime 均完成，cursor 向量为 `[4,3,3,3,3]`。第五个 Runtime 为 `status=completed`、`nextCursor=3`、`finishReason=tool_calls`，并保存该不可用工具调用；它本身不是模型传输失败。
- chat 固定为 5 次；生产工具委托与真实执行各 3 次；耐久 execution 为 4 条，其中第四条为 blocked；`tool_retry_blocked` 为 1；unsafe 为 0。第五轮工具调用不增加上述任何工具计数。
- 终态 Session 按既有失败回滚契约只保留 user 与唯一 `error-recovery` assistant，不伪保留失败前工具轨迹或第五轮工具调用。当前页与完整刷新后顶部耗时各唯一，assistant 页脚不重复计时。
- 完整 reload 后 AgentRun、五个 Runtime、失败消息、runState 与计时保持唯一；AgentRun POST、Runtime POST、chat 与真实工具执行四项增量全部为 0。

根契约 `test_agent_rejects_forced_final_tool_call_without_executing_it` 直接证明第五轮 payload 无 `tools`/`tool_choice`、恢复指令存在、上游返回工具调用、父 Run 失败，以及该调用 ID 不出现在 execution 或任一工具事件中。bundle 与 direct classic 复用同一 H4 生命周期 helper，并对 AgentRun、Runtime、Session、DOM 与刷新投影逐项对等。

## 稳定语义哈希

随机 AgentRun、Runtime、toolCall ID、绝对时间、端口、完整本地化错误正文、原始 JSONL 字节与完整 HTML 均不进入哈希。bundle 与 direct classic 的九项 SHA-256 完全一致：

| 投影 | SHA-256 |
|---|---|
| `eventProjection` | `b5ccf4a622600108de56687485f17642caab530651f31b1679d31840d45f2de2` |
| `retryExecutionProjection` | `c4f4a8432ad9be01f331e72be1c9b6bd709bb7eda508c3b00604a2967d8c31fe` |
| `modelToolReceiptProjection` | `4d02940043fc3266a6e6bf6e2a94ab7e775dd539401e84f40255daa29ed1b721` |
| `forcedFinalUnusableProjection` | `ca5df9b2f2375b7ccfca0d745b636c55e29224a28edad7d40aa08ca333baec0f` |
| `runtimeProjection` | `5544f1eb37db1be95f38a7ac373a3a83b8b1490ff2760ad6fe18880cb7547186` |
| `sessionRoleContent` | `431b4ed43aa1395a0c9b439806bcdc49d813b0cc0784d01086fccf64401d2e5b` |
| `sessionRunState` | `c40a0bc4034901d0d0085d53f1d2bc3a144dd957b34e9c8cca87ac16543b5784` |
| `terminalDom` | `3ede9770eb9cae435e6ad61a79676f550bae27c916a1aea6ad94742e8b533a06` |
| `refreshLifecycle` | `60b5a625b74c8855ddde66f04ff48057eb00146ceab75988db20144d2c067f78` |

## 验证与实现基线

累计实现提交为 `8178be99e8ede82d739902d6c8f37afc76846abb`。该最终树下已取得：

- H4-6P bundle/direct classic 对等通过，九项哈希逐项一致；H4 infrastructure 通过；
- 连续两轮标准 H4 均为 `51 passed`、单 worker、`retries=0`；
- 完整 pytest 为 `1131 passed, 751 subtests passed`；
- 相关 Agent Runtime 根契约、前端定向、`npm run check:frontend`、Node/Python 语法与 `git diff --check` 通过。

本专题收口只执行 Markdown、链接、哈希引用、diff 与三文件白名单检查；实现与测试 SHA-256 未变化，因此沿用上述同一最终树的完整矩阵，不把长测试描述为文档提交后重跑。

## 证明边界与回退

H4-6P 只证明固定字段顺序、同一 `read_file` 行范围失败指纹达到既有限流边界后，forced-final 模型仍返回工具调用时，该调用只停留在第五轮模型完成层证据，不会进入工具执行链，且同进程完整 reload 零重放。

本阶段不证明其他工具、其他 arguments 或错误签名、不同阈值、执行前 schema/parse 失败、其他模型响应错误、异常或孤儿历史记录、多并行失败、queue/steer、工具型后续对话、跨进程恢复、后台工具副作用 exactly-once 或主观视觉验收。尤其不能从只读 `read_file` 场景外推有外部副作用工具的安全性。

独立回退只需撤销 H4-6P 的根测试、隔离 host/H4 场景与本专题；没有生产代码、协议、持久化数据或历史记录迁移需要回写。
