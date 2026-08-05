# Harness H3-2A：单 Run replay 夹具扩展

## 阶段定位

H3-2A 将 H2-3 真实验收中已经暴露并修正的两类跨层时序问题固化为脱敏、离线、确定性的单 Run replay 夹具。本阶段只扩展合成轨迹及其 fixture/replay 测试，不调用真实模型、工具、网络或浏览器，也不改变任何生产行为。

本阶段没有修改生产 reducer、前端、服务端、AgentRun、会话 JSONL、Runtime 生命周期、replay runner 或夹具 schema；多 Run 排队/并行、Child AgentRun、刷新恢复和发布门禁均不在本阶段范围内。

## 新增轨迹

### `cancel-multi-tool-terminal-closure`

- 共 8 个事件，4 个检查点，检查点位于 seq `3 / 5 / 7 / 8`；
- 第一模型轮通过同一个 `model_completed` 声明 `run_command` 与 `read_file` 两个工具；
- 命令产生一次 `tool_started / command_started` 和一次失败 `tool_completed`；
- 未开始的读取工具不产生 `tool_started / command_started`，只产生一次带 `result.cancelled: true` 与 `cancelledBeforeStart: true` 的 `tool_completed`；
- 两个已声明工具各有且只有一个完成事件，最后只有一个 Run `cancelled` 终态。

### `command-failure-model-recovery`

- 共 10 个事件，4 个检查点，检查点位于 seq `3 / 6 / 8 / 10`；
- 第一模型轮只声明一个命令，命令只产生一次开始和一次失败完成事件；
- 合成失败结果固定为退出码 `23` 和 stderr 标记 `synthetic-command-failure-marker`；
- 失败结果后进入第二模型轮，只生成一次合成最终回答和一个 Run `completed` 终态。

## 两层证据与边界

### replay / View Model 检查点

两条轨迹的阶段检查点断言状态、`terminalStatus`、模型轮次、工具数量、工具 ID、工具状态与 outcome、事件顺序和 `pendingKind`。统一 runner 继续证明：

- 所有检查点恢复后的终态与从头回放一致；
- 每个事件重复投递不改变终态；
- 相同轨迹和整套轨迹重复回放得到相同确定性哈希；
- 删除、乱序或错误改写关键事件时报告首个事件与状态路径。

### 原始夹具契约

`tests/test_harness_fixtures.py` 直接核对 `model_completed` 声明的工具 ID 与 `tool_completed` 集合完全对应、未启动读取工具没有开始事件、取消结果字段，以及命令失败的固定退出码和 stderr 标记。这些字段未进入当前规范 View Model，因此不以 View Model 检查点替代原始事件契约。

`pendingKind: ""` 只证明规范 View Model 没有授权、问卷或凭据等待态，不能证明服务端 `pendingToolCalls` 已清空。当前投影不建模工具队列；本阶段只通过声明工具与完成事件集合闭合、唯一终态，以及 H2-3 已取得的真实服务端证据共同支撑工具终态闭合结论，不为此扩展 reducer 或 schema。

## 关键变异诊断

| 新轨迹 | 变异 | 首差异事件 | 首差异路径 |
|---|---|---:|---|
| `cancel-multi-tool-terminal-closure` | 删除未开始读取工具的完成事件 | 8 | `$.events[6].seq` |
| `cancel-multi-tool-terminal-closure` | 改写读取工具 ID | 7 | `$.tools[1].toolCallId` |
| `command-failure-model-recovery` | 乱序第二模型轮 pending/started 事件 | 8 | `$.events[6].seq` |
| `command-failure-model-recovery` | 将失败 outcome 改写为成功 | 6 | `$.tools[0].outcome` |

这些测试直接变异两条 H3-2A 新轨迹，没有用旧轨迹的通用变异测试替代新路径证据。

## 最终基线与验证

H3-2A 收口后的统一基线为：

- 17 条合成轨迹；
- 124 个事件；
- 25 个检查点；
- 25 次检查点恢复；
- 4 个显式恢复点。

确定性结果：

- fixture suite hash：`c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc`；
- replay hash：`166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。

最终验证：

```powershell
python scripts/verify_harness_fixtures.py
npm run verify:harness-replay
python -m pytest tests/test_harness_fixtures.py tests/test_harness_replay.py tests/test_run_projection.py -q -p no:cacheprovider
git diff --check
```

结果为 fixture/replay 全量通过，pytest `30 passed, 41 subtests passed`，`git diff --check` 通过。脱敏扫描没有发现真实命令、正文、用户路径、URL、Key 或 Token。

## 兼容、回退与后续边界

- 旧 AgentRun、会话 JSONL、工具协议、默认前端和经典回退页不受影响，无需迁移；
- 回退只需移除两条合成轨迹及对应 fixture/replay 测试预期，生产运行路径不变；
- H3-2B 的多 Run replay 设计需另行分析和确认，本阶段没有开始排队、显式 `/parallel` 或 Child AgentRun 结构设计；
- replay 接入发布门禁仍是后续独立阶段，本阶段未修改发布脚本。
