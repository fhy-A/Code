# Harness H3-2B1：多 Run replay 关系基础设施

## 阶段定位

H3-2B1 按路线 A 新增独立、严格版本化的多 Run 合成 suite、schema、runner 与定向测试，只覆盖 `queue-parallel-multi-run-relations` 的多 Run 回放基础设施和关系契约。它不改变 H3-1/H3-2A 的单 Run fixture、schema、runner、语义、计数或哈希，也没有修改生产 reducer、AgentRun、会话 JSONL、Runtime、前端或发布脚本。

本阶段的组合层只维护 `scheduleCursor`、各 Run 的状态/cursor 和不可变身份图。每个 Run 仍分别调用现有生产 `reduceRunProjectionInput` 与 `projectRunViewModel`；`fact-marker` 只参与固定 schedule 和关系断言，不修改任何 Run 业务状态。组合层没有建立可变 queue、background、UI messages 或 usage ledger，也没有复制队列泵、后台 dispatcher 或后台完成回调。

## 独立基线

多 Run 基线与既有单 Run 基线分开统计：

- 1 个场景：`queue-parallel-multi-run-relations`；
- 3 个 Run：`F1`、`B1`、`F2`；
- 12 个 Run 事件；
- 15 个 schedule 步骤，其中 3 个 `fact-marker`；
- 4 个阶段检查点，以及 4 次序列化恢复；
- 固定创建顺序为 `F1 / B1 / F2`，固定终态顺序为 `F1 / F2 / B1`。

确定性哈希：

| 对象 | SHA-256 |
|---|---|
| multi-run fixture suite | `710a3e5677281d3554f33a2b0fa11fd84a52270c6b90e0aa96e9b93da534880a` |
| multi-run suite replay | `095537b72121478d1ef35a143aa6ecd361c0ec557a4fcc9594e3b024e86aabf6` |
| 复合状态 | `5bfc185b1f31979e3802b1908d1b908c6f64d4ccc5ca882da158e7b840504e85` |
| Run `F1` | `996792e15f8182f3b7c7f04acd862efdb5fd5ba590cca34a20d03ab3708b112a` |
| Run `B1` | `2de637407b7156c3d32a94f95fa4e824c0a089c86436f9d78c600fd1340b817a` |
| Run `F2` | `2959cee047a402407bd8b8d29cc2b46fa8b00b7b3e2c17abb647cebc967e1d6a` |

全 schedule 重复投递后的复合状态及三个 Run 哈希均保持不变。

## 复合检查点恢复

每个检查点先经过 JSON 序列化/反序列化，再只由保存状态中的 `scheduleCursor` 决定续播位置，不以 fixture 外部的 `checkpoint.afterStep` 替代恢复游标。恢复入口执行以下核对：

1. `scheduleCursor` 必须是 `0..schedule.length` 内的整数；
2. 从 `scheduleCursor` 对应的 schedule 前缀推导各 Run 的预期 cursor；
3. 预期 cursor 必须同时等于 `runCursors[runKey]` 和 `runStates[runKey].cursor`；
4. `runStates`、`runCursors` 的 Run key 集合必须分别与场景身份图精确匹配，不能缺失或多出 Run；
5. 从保存的 `scheduleCursor` 续播后，复合状态和各 Run 终态必须与从头回放一致。

四个检查点分别位于 schedule step `6 / 10 / 13 / 15`，因此包含非末尾复合恢复以及终态恢复证据。

## 定向失败诊断

| 变异 | 首差异路径 |
|---|---|
| 将事件投递给错误 Run | `$.schedule[6].agentRunId` |
| 引用不存在的 Run 事件 | `$.schedule[0].eventSeq` |
| 制造 AgentRun 身份冲突 | `$.identities.agentRuns.B1.agentRunId` |
| 将 Run 错连到其他 Session | `$.identities.agentRuns.B1.sessionId` |
| 改写 Run 创建顺序 | `$.orders.creation[0]` |
| 改写 Run 终态顺序 | `$.orders.terminal[1]` |
| 污染 F2 恢复状态 | `$.checkpoints[2].resume.runs.F2.status` |
| 非末尾检查点 `scheduleCursor` 向前污染 | `$.checkpoints[0].resume.runCursors.B1` |
| 非末尾检查点 `scheduleCursor` 向后污染 | `$.checkpoints[0].resume.runCursors.F1` |
| `scheduleCursor` 越界 | `$.checkpoints[0].resume.scheduleCursor` |
| 删除 `runStates.F2` | `$.checkpoints[0].resume.runStates[2]` |
| 增加 `runCursors.EXTRA` | `$.checkpoints[0].resume.runCursors[1]` |
| 污染 `runStates.B1.cursor` | `$.checkpoints[0].resume.runStates.B1.cursor` |
| 重复 schedule 事件 | `$.schedule[7].eventSeq` |

## 既有基线与验证

旧单 Run 基线原样保持为 17 条轨迹、124 个事件、25 个检查点、25 次检查点恢复和 4 个显式恢复点；fixture suite hash 仍为 `c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc`，replay hash 仍为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。多 Run 数量没有并入该基线。

收口验证命令：

```powershell
python scripts/verify_harness_fixtures.py
npm run verify:harness-replay
node scripts/replay-agent-multi-run-traces.cjs --json
python -m pytest tests/test_harness_multi_run_fixtures.py tests/test_harness_multi_run_replay.py tests/test_harness_fixtures.py tests/test_harness_replay.py tests/test_run_projection.py -q -p no:cacheprovider
python -m pytest tests/test_message_queue.py tests/test_subagent_frontend.py tests/test_concurrency.py -q -p no:cacheprovider
python -m pytest tests/test_frontend_modules.py -k "state_module_isolates_session_domains_and_checkpoints or background_checkpoint_timing_and_usage_are_pure_module_behaviors" -q -p no:cacheprovider
node --check scripts/replay-agent-multi-run-traces.cjs
git diff --check
```

最终结果为：单 Run fixture/replay 验证均通过；Harness 组合回归 `52 passed, 72 subtests passed`；既有 queue/background 相关回归 `64 passed`；Session accessor、后台 helper 和确定性 AgentRun ID 所在的既有生产纯函数契约测试 `2 passed, 165 deselected`；Node 语法及 `git diff --check` 均通过。

## 完成声明边界

H3-2B1 证明的是：多个 Run 分别复用生产 reducer/View Model 后的独立投影、静态 Session/父子/queue item/background job 身份关系、固定 schedule 和不同终态顺序、由保存 `scheduleCursor` 驱动的复合检查点恢复，以及重复投递幂等。

Session accessors、后台 helper 和确定性 AgentRun ID 只按其现有直接函数契约测试。本阶段不证明真实 queue 提升、background 调度或完成、消息或 usage exactly-once、真实线程竞争、DOM、页面刷新、Runtime 原始事件恢复或发布门禁；`fact-marker` 也不是这些生产生命周期的测试替身。H3-2B2 的 Child AgentRun replay 尚未开始，仍需单独分析和确认。
