# Harness H3-2C1：上游失败与 non-action 恢复证据

## 阶段定位

H3-2C1 新增一套独立的上游失败与 non-action 恢复 suite，用于冻结 401、429、502、首响应超时、空响应恢复和 reasoning-only 恢复的当前生产证据。本阶段没有修改生产代码、默认单 Run schema/suite/runner、H3-2B1/B2、`package.json`、H4 或发布脚本。

新 suite 的事件部分继续使用现有单 Run fixture v1 payload，并额外声明严格版本化的 evidence profile：

- `id: h3-2c1-upstream-failure-non-action`；
- `version: 1`；
- `replayPayload: single-run-fixture-v1`；
- `productionEvidence: model-runtime-agent-run-integration-v1`。

因此，扩展的 `sourceFacts` 只属于该 evidence profile，不会被误认为默认 fixture v1 的通用字段。独立 schema 对 profile、本地假上游输入、Runtime 结果、AgentRun 错误码、事件顺序和 fallback 证据范围进行严格约束。

## 三层证据

| 层级 | 直接证据 | 能够证明 | 不能证明 |
|---|---|---|---|
| fixture/schema 契约 | 严格 evidence profile、原始规范 Agent 事件、`sourceFacts` 与 `runtimeInput` 对照 | 合成事实完整、字段关系闭合、事件顺序与预期一致 | 生产 Runtime 实际分类或真实上游行为 |
| replay/View Model | 现有 `replay-agent-traces.cjs`、生产 reducer 与 View Model | 合成事件的状态、轮次、终态、检查点恢复、重复投递及确定性哈希 | HTTP 分类、Key fallback、真实 Runtime 事件或浏览器生命周期 |
| 本地集成 | 同一 case 数据驱动本地假上游、Model Runtime 与 AgentRun | 当前 HTTP/超时分类、transient、AgentRun `errorCode`、规范耐久事件顺序，以及代表性 pre-event fallback | 真实网络、供应商重试、线程竞争、DOM、刷新或发布门禁 |

本地假上游输入使用独立的 `runtimeInput.httpStatus/httpMessage`；实际 Runtime 快照再与 `sourceFacts.upstreamStatus/runtimeErrorCode/runtimeTransient` 对照，避免把同一字段同时当输入和期望造成自我满足。成功 Runtime 当前会在终态快照中把 `upstreamStatus` 归零，因此两条 non-action case 明确记录输入 HTTP 200、Runtime 终态 `upstreamStatus: 0`，不将二者混写。

## 独立基线与轨迹

H3-2C1 数量不并入默认单 Run或 multi-run 基线：

- 6 条轨迹；
- 26 个事件；
- 16 个检查点及 16 次 JSON 序列化恢复；
- 0 个显式 `recoveryPoints`；两条 non-action 轨迹各包含一个真实 `model_recovery` 事件。

| 轨迹 | 当前生产事实 |
|---|---|
| `upstream-401-config-terminal` | 普通 401 正文分类为 `config_error`，非 transient；带模型无权标记的正文仍优先为 `model_access_denied` |
| `upstream-429-transient-terminal` | 429 分类为 `upstream_error`、transient，AgentRun 唯一失败终态 |
| `upstream-502-transient-terminal` | 502 分类为 `upstream_error`、transient；另以两个合成 Key 验证一次代表性 pre-event fallback |
| `model-first-response-timeout-terminal` | 首个有效内容截止前只有 keepalive 时分类为 `model_response_timeout`、transient |
| `model-empty-output-recovery-current` | 首轮 outcome 为 `empty`，直接产生 `model_recovery` 后进入下一次 `model_started` |
| `model-reasoning-only-recovery-current` | 首轮 outcome 为 `reasoning_only`，直接产生 `model_recovery` 后进入下一次 `model_started` |

两条 non-action 轨迹的当前顺序均为：

```text
created -> model_started -> model_completed -> model_recovery
        -> model_started -> model_completed -> completed
```

恢复后不插入 `model_pending`，成功轮 outcome 为 `completed`。默认 suite 中原有的 `model-non-action-recovery` 保持不变，它是早期历史投影样本，仍含 `model_pending` 且成功轮 outcome 为 `content`；当前生产精确顺序以 H3-2C1 新 suite 为准。

429 与 502 可以得到相同的 AgentRun 投影：`created / model_started / failed` 和 `upstream_error`。两者的 HTTP 状态差异只由 Model Runtime 集成层直接证明，不从 reducer/View Model 反推。

## fallback 证据范围

`upstream-502-transient-terminal` 另带一个明确的 fallback profile：两个合成 Key、两次本地假上游调用，第一次 502 发生在 Runtime 尚未产生事件时，第二个 Key 成功完成。AgentRun 最终只产生一个模型轮投影和一个完成终态。

该测试只覆盖一个代表性 502 状态，不证明 401、429、其他 5xx、连接异常或首响应超时均会采用同样 fallback，也不证明真实供应商或网关内部重试。

## 确定性哈希

| 对象 | SHA-256 |
|---|---|
| fixture suite | `3278b2cfed32b5d06d8c0e0b4c07f84b065b3c0f41803d13bbbe211c8879a6c1` |
| suite replay | `caa4f57850729a6d9452030418f914b42061fae0c64e410e839d892d38b97177` |
| 401 | `4ee23358e8e2263316e27fbfd2d55ab703dcb555f40b5412fe0a0899157d049e` |
| 429 | `5f76190e174310644acca65d82ece61d5334a5039ed45af6d2aa003e42db4088` |
| 502 | `2c924318f4433e84503fe3b4ff744075f9590dd87b9bb59c65aaecc1ca05bc9e` |
| 首响应超时 | `9920c097c0a31748b5b48a30eccd78b402a7add99b3928de77c85cc728569293` |
| empty 恢复 | `186644bcc433bd0fe9e16fc965ef7a9dfdc45cd4b7b6b9fff1fc5f8b15f1c0c5` |
| reasoning-only 恢复 | `29257088abe58ed97c3e9d4c9b337815556e38db4b6f0fc83e1007f4eb686456` |

默认单 Run 基线仍为 17 条轨迹、124 个事件、25 个检查点、25 次检查点恢复和 4 个显式恢复点；fixture/replay hash 仍分别为 `c5136af7d5abe6f055e76e230939f7aa5d4cf1c4b2bb832c492819d5604eeffc` 与 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。原 `model-non-action-recovery` 状态 hash 仍为 `99f548ee5632f16dde7b266f63d675d04b67df723d2022a792fea7f9ba662721`。B1/B2 的 fixture、suite replay、复合状态及各 Run hash 也保持不变。

## 定向失败诊断

| 故意变异 | 首差异路径 |
|---|---|
| `upstreamStatus` 错写 | `$.sourceFacts.upstreamStatus` |
| Runtime 错误码错写 | `$.sourceFacts.runtimeErrorCode` |
| transient 错写 | `$.sourceFacts.runtimeTransient` |
| AgentRun 错误码错写 | `$.sourceFacts.agentRunErrorCode` |
| Agent 事件顺序错写 | `$.sourceFacts.agentEventTypes` |
| 失败事件 `errorCode` 错写 | `$.events[2].data.errorCode` |
| 删除或乱序 `model_recovery` | `$.events[3].seq` |
| 重复恢复事件 | `$.events[4].seq` |
| non-action outcome 错写 | `$.modelRounds[0].outcome` |
| 删除失败终态 | `$.checkpoints.afterSeq` |

## 验证结果

- H3-2C1 fixture/replay 定向测试：`15 passed, 56 subtests passed`；
- H3-2C1、B1/B2、默认单 Run及生产投影组合：`96 passed, 199 subtests passed`；
- Model Runtime 与 Agent 协议：`21 passed, 160 subtests passed`；
- 完整 AgentRun 集成：`98 passed, 60 subtests passed`；
- H3-2C1、默认单 Run、B1、B2 CLI replay、两个 runner 的 Node 语法及 `git diff --check` 均通过。

测试只调用本地 `ThreadingHTTPServer` 假上游，不调用真实模型、工具或外部网络。

## 完成声明与回退

H3-2C1 证明的是：合成固定事件下的生产 reducer/View Model 投影、检查点恢复与重复投递，以及本地假上游下的当前 Runtime 分类、AgentRun 错误码和规范耐久事件顺序。

本阶段不证明真实网络、供应商或网关重试、所有 HTTP 状态的 Key fallback、线程竞争、DOM、浏览器交互、页面刷新、Runtime 原始事件恢复、H4 或发布门禁。没有把 HTTP 状态或 transient 写入 AgentRun/View Model。

回退时可独立删除新 schema/suite 和两份 Harness 定向测试，并移除 Model Runtime/AgentRun 测试中的 H3-2C1 case 消费逻辑；默认单 Run Harness、B1/B2 和生产行为无需迁移或回写。
