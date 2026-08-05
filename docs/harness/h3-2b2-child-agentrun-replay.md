# Harness H3-2B2：Child AgentRun replay 关系契约

## 阶段定位

H3-2B2 在 H3-2B1 的多 Run 回放基础设施上增加严格的 fixture v2 和独立合成 suite，只覆盖 Child AgentRun 的静态父子身份、父工具调用映射、固定 schedule、每 Run 生产投影、复合恢复与重复投递幂等。现有 runner 通过显式版本分派兼容读取 v1/v2；默认不传 `--suite` 时仍运行 H3-2B1 的 v1 suite。

本阶段没有修改 v1 schema/suite、单 Run Harness、生产 reducer、AgentRun、会话 JSONL、Runtime、前端、`package.json` 或发布脚本。每个 Run 继续分别调用生产 `reduceRunProjectionInput` 与 `projectRunViewModel`；组合层仍只维护 `scheduleCursor`、各 Run 的 state/cursor 和不可变身份图，没有建立 Child worker、调度器、可变父子生命周期或 usage ledger。

## fixture v2 与身份分支

`multi-run-trace-suite-v2.schema.json` 使用 `multiRunFixtureVersion: 2`，并通过 `role` 分支严格约束两类身份：

- Root：`role: foreground`，父字段为空，`agentDepth: 0`，`clientRequestId` 非空；
- Child：`role: child`，`parentAgentRunId`、`parentToolCallId` 非空，`agentDepth: 1`，`clientRequestId` 为空。

Child 判断、父 Run 和父工具关系全部从该版本化身份图推导，不依赖 `P1 / C1 / C2` 命名约定。v2 场景不使用 queue item、background job 或 fact-marker，也不借这些字段推演业务生命周期。

## 独立基线

v2 基线与 B1 multi-run v1、单 Run 基线分别统计：

- 1 个场景：`child-agent-out-of-order-terminal-parent-results`；
- 3 个 Run：父 Run `P1` 13 个事件，Child `C1 / C2` 各 4 个事件；
- 合计 21 个事件、21 个 schedule 步骤、0 个 fact-marker；
- 6 个阶段检查点及 6 次 JSON 序列化恢复；
- 创建顺序 `P1 / C1 / C2`，全局终态顺序 `C2 / C1 / P1`；
- Child 终态顺序 `C2 / C1`，父工具结果顺序 `T1 / T2`。

确定性哈希：

| 对象 | SHA-256 |
|---|---|
| v2 fixture suite | `0ab4fb75adfd3a0818db55f1e57b02fa5aabdcf9b6c156fd8827dfb98e7255da` |
| v2 suite replay | `764f914012c0bb5c1e635725eac39b3b120374262a20d3b251c8b7645531c618` |
| v2 复合状态 | `176f9e3324d213fe6ac5c9a3bc12e78d7b3f6dd004b3124b7a188c36801158a0` |
| Run `P1` | `f88a0d3c606050608d2836f38fd2010f47f9a3243ff728b9d886dd40d869d065` |
| Run `C1` | `4c1c79fff9cd4cd04ab807bcdc4f572c6bba1c21ebb5091d8f7ca3c50bd5c46d` |
| Run `C2` | `472d381a1923b8060fbf3732b599b1ac334d1f89bc04de47b05aa3e06307c6cd` |

全 schedule 重复投递后的复合状态及三个 Run 哈希与上述值完全一致。

## 四方身份闭合与固定顺序

原始 fixture 契约独立核对以下四方事实：

1. 父 Run 第一模型轮依次声明 `T1 / T2` 两个 `task` 工具调用；
2. `C1` 闭合到父 Run/`T1`/depth 1，`C2` 闭合到父 Run/`T2`/depth 1；
3. 两个 `child_agent_created` 分别建立 `T1 → C1`、`T2 → C2` 映射；
4. 两个 `tool_completed.result.childAgentRunId` 按 `T1 → C1`、`T2 → C2` 对应，并保持父结果顺序 `T1 / T2`。

固定 schedule 中，`C2` 与 `C1` 分别在 step 13、15 终态，首个父工具结果位于 step 16，因此两个 Child 均终态前不能出现父工具完成。父 Run 随后在 step 18～21 进入第二模型轮，产生一个带正文且无工具调用的最终 `model_completed`，再产生唯一 `completed` 终态。`creation`、全局 `terminal`、`childCreated`、`childTerminal` 和 `parentToolResults` 分别派生并独立断言。

## 复合恢复

六个检查点位于 schedule step `3 / 10 / 13 / 15 / 17 / 21`。恢复继续只由序列化状态中的 `scheduleCursor` 驱动：

1. `scheduleCursor` 必须是 `0..schedule.length` 内整数；
2. 根据对应 schedule 前缀推导每个 Run 的预期 cursor；
3. 预期 cursor 必须同时等于 `runCursors[runKey]` 和 `runStates[runKey].cursor`；
4. `runStates`、`runCursors` 的 Run key 集合必须分别与场景精确匹配；
5. 续播后的复合投影、父工具投影和各 Run 哈希必须与从头回放一致，重复事件不能重复 Child、父工具或最终投影。

## 定向失败诊断

| 变异 | 首差异路径 |
|---|---|
| Child 错连父 Run | `$.identities.agentRuns.C1.parentAgentRunId` |
| 两个 Child 重复关联同一父 tool call | `$.identities.agentRuns.C2.parentToolCallId` |
| Child 关联错误父 tool call | `$.runs.P1.events[2].data.toolCalls[1]` |
| 遗漏 `child_agent_created` | `$.runs.P1.events` |
| `child_agent_created` 错写 Child ID | `$.runs.P1.events[4].data.childAgentRunId` |
| 父工具结果错写 Child ID | `$.runs.P1.events[7].data.result.childAgentRunId` |
| Child 终态顺序错误 | `$.orders.childTerminal[0]` |
| 父工具结果早于全部 Child 终态 | `$.schedule[13].eventSeq` |
| 父工具结果顺序错误 | `$.orders.parentToolResults[0]` |
| 重复 schedule 事件 | `$.schedule[13].eventSeq` |
| 恢复状态污染 | `$.checkpoints[3].resume.runs.P1.diagnostics[0]` |
| `scheduleCursor` 向前/向后/越界污染 | `$.checkpoints[3].resume.runCursors.C1` / `$.checkpoints[3].resume.runCursors.P1` / `$.checkpoints[3].resume.scheduleCursor` |
| 恢复状态增加 Run key | `$.checkpoints[3].resume.runCursors[2]` |

## 旧基线保护

H3-2B1 v1 基线仍为 1 个场景、3 个 Run、12 个事件、15 个 schedule 步骤、3 个 fact-marker、4 个检查点及 4 次恢复；fixture、suite replay、复合状态及 `F1 / B1 / F2` 哈希全部保持不变。默认 CLI 仍读取 v1 suite，v1 的身份验证、`deriveOrders` 输出、投影结构和哈希输入继续走原逻辑。

单 Run 基线仍为 17 条轨迹、124 个事件、25 个检查点、25 次检查点恢复和 4 个显式恢复点；fixture suite hash 为 `c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc`，replay hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。v2 数量不并入这两套旧基线。

## 验证结果

- v2 fixture/replay 定向测试：`24 passed, 59 subtests passed`；
- B1、B2、单 Run及生产投影组合回归：`76 passed, 131 subtests passed`；
- queue/background 既有回归：`64 passed`；
- Session accessor 与后台纯 helper 定向契约：`2 passed, 165 deselected`；
- Agent 事件协议：`10 passed, 155 subtests passed`；
- 既有 Child 持久化/用量合并与同轮并发顺序集成测试：`2 passed, 93 deselected`；
- 单 Run fixture/replay、v1/v2 CLI replay、Node 语法和 `git diff --check` 均通过。

## 完成声明边界与回退

H3-2B2 证明的是：合成固定 schedule 下的静态父子身份闭合、每个 Run 独立复用生产 reducer/View Model 后的投影、Child 终态与父工具结果的两种独立顺序、由保存 `scheduleCursor` 驱动的复合恢复，以及重复投递幂等。

本阶段不证明真实 Child worker 或并发调度、线程竞争、queue/background 生命周期、取消传播、重启复用、消息或 usage exactly-once、DOM、页面刷新、Runtime 原始事件恢复或发布门禁。既有生产集成测试继续作为真实 Child 创建、并发执行、父结果排序和用量合并的独立证据，不能由固定 replay schedule 替代。

回退时可删除 v2 schema/suite 和两份 v2 定向测试，并移除 multi-run runner 的 v2 分派与契约分支；v1 schema/suite、默认 CLI、单 Run Harness 和生产行为均无需迁移或回写。
