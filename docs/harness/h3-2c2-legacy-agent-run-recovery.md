# Harness H3-2C2：旧 AgentRun 持久化恢复契约

## 阶段定位

H3-2C2 为既有 AgentRun v1～v4 最小 compatibility fixture 建立真实生产持久化恢复契约。本阶段只新增严格版本化的 evidence manifest、对应 schema 和一份定向测试；没有修改生产 loader、AgentRun/JSONL 协议、既有 compatibility fixture、任何 replay runner/schema、前端或发布脚本。

manifest 的 evidence profile 为 `h3-2c2-legacy-agent-run-recovery` v1。它只通过相对路径引用以下四份既有 fixture，不复制其中的 `record`：

- `compatibility/agent-run-v1.json`；
- `compatibility/agent-run-v2.json`；
- `compatibility/agent-run-v3.json`；
- `compatibility/agent-run-v4.json`。

manifest 显式冻结当前 v4 持久化的 39 个字段、四份 fixture 的规范哈希、源记录版本、缺失字段清单和分层预期。v1/v2/v3/v4 缺失字段数量分别为 19/12/8/6；该清单不是从当前 serializer 临时推导后作为自身期望，而是 manifest 与测试常量中的独立固定契约。

## 三层生产证据

四个案例分别调用现有生产函数，并按实际字段归属验证三层结果；三层字段集合不被假定相同。

| 层级 | 生产入口 | 直接验证 | 边界 |
|---|---|---|---|
| loader 内部规范化 | `_agent_run_from_record()` | 内部 snake_case 状态、`resume_status`、父子字段、depth、权限、错误码、non-action/force-final 默认、context、pending steer、compaction、`next_seq` 等 | 内部锁、取消事件和 worker 对象不进入 manifest；不等同于公共 API |
| 当前公共投影 | `_agent_snapshot()` | 公共 camelCase 身份、状态、context、轮次、pending/steer/compaction 计数和 cursor | 不包含 `resumeStatus`、`forceFinalReason` 等非公共字段；不证明 UI 或 DOM |
| v4 持久化结果 | `_agent_run_record()` | 精确 39 个字段、`version: 4`、规范状态、`resumeStatus`、`forceFinalReason`、父子默认、context、pending/steer/compaction 与 `nextSeq` | 只证明 serializer 当前结果，不代表任意历史或损坏记录都可迁移 |

输入不变性检查只覆盖这四份最小 compatibility fixture。它不扩展为所有历史 AgentRun、用户数据或任意嵌套执行记录的不变性声明。

## 四个独立版本案例

| 案例 | 源状态 | 缺失字段 | 规范化重点 |
|---|---|---:|---|
| v1 | `tools` | 19 | 恢复为 `waiting_credentials`，`resume_status=tools`，旧模型 context 默认 128K |
| v2 | `waiting_user_input` | 12 | 保留等待输入与 `pendingInput`，模型族 context 默认 1M |
| v3 | `completed` | 8 | 保持唯一终态、既有 compaction、结果和 `nextSeq: 2` |
| v4 | `completed` | 6 | 保留同轮引导 receipt，父子/non-action/force-final 字段安全默认 |

每个案例都真实执行两次磁盘加载：

```text
旧记录写入临时 DATA_DIR
  -> 第一次 _get_agent_run()
  -> 同进程缓存命中
  -> 规范化 v4 持久化
  -> 清空内存 _agent_runs 模拟服务重启
  -> 第二次 _get_agent_run()
  -> 再次缓存命中
```

因此共有 4 个独立版本案例、4 次完整往返、8 次真实磁盘加载。所有 AgentRun、配置和 Session 测试文件均位于临时目录；实际生产 workspace helper 仍被调用，只把其事实源重定向到临时配置与目录。

## v1 自动持久化与 v2～v4 显式写回

活动 v1 的源状态为 `tools`。第一次 `_get_agent_run()` 经 loader 恢复为 `waiting_credentials` 后，追加且只追加一个：

```text
waiting_credentials(reason=server_restarted, resumeStatus=tools)
```

该追加通过 `_append_agent_event()` 完成，而 `_append_agent_event()` 已经自动调用 `_persist_agent_run()`，所以此时磁盘记录已是规范化 v4。测试随后再次显式调用 `_persist_agent_run()` 只是重复确认 serializer 与写回幂等，不是第一次 v4 持久化。清空 `_agent_runs` 后的第二次磁盘加载读取 `status=waiting_credentials`，不再追加重启事件，公共快照和持久化记录均保持稳定。

v2 的 `waiting_user_input` 以及终态 v3/v4 首次加载都不会追加重启事件，因此它们由测试中的显式 `_persist_agent_run()` 完成规范化 v4 写回。终态 v3 往返前后只保留原 `completed` 事件，公共快照稳定。

## 确定性基线

| 对象 | 规范 SHA-256 |
|---|---|
| H3-2C2 manifest | `9acdf241c211ccff9528f30a17ad03ce7ddeae16c263f5de4494fdd61c6bddeb` |
| schema | `a66792fa46e7844479b9320ad93e9dac4b610b664ad6e4e4a4d14d761add26f4` |
| AgentRun v1 fixture | `a2bed1af692366f4af3f21f1b41bba7f09cccac4456da57e93e193a0c5345598` |
| AgentRun v2 fixture | `890db5b3840b5bd2ffb2d0f4ac5f1cc0611865debf981a87fa29f3a32fd8cc66` |
| AgentRun v3 fixture | `f5e0279652b4aea71abf2f1447a87578b7201caff3519bba43f70bc77df7470a` |
| AgentRun v4 fixture | `96d60cdcebb6d49668e869d9b854bba67c53fc1ae0b3c551218b11554ffe13a0` |

默认单 Run、H3-2C1、H3-2B1 与 H3-2B2 的 fixture/replay 哈希均保持不变。H3-2C2 是独立持久化兼容证据，不并入默认单 Run、H3-2C1 或 multi-run 的场景、事件、检查点和恢复计数。

## 定向失败诊断

| 故意变异 | 首差异路径 |
|---|---|
| 缺失字段清单错写 | `$.cases[0].missingFields[0]` |
| loader status 错写 | `$.cases[0].expected.loader.fields.status` |
| 公共父 Run 错写 | `$.cases[1].expected.snapshot.fields.parentAgentRunId` |
| persisted depth 错写 | `$.cases[1].expected.persisted.fields.agentDepth` |
| loader context 错写 | `$.cases[1].expected.loader.fields.context_limit` |
| steer receipt 计数错写 | `$.cases[3].expected.snapshot.fields.steerReceiptCount` |
| v4 重写版本错写 | `$.cases[2].expected.persisted.fields.version` |
| 重启原因错写 | `$.cases[0].expected.disk.restartEvents[0].reason` |
| 第二次磁盘加载 `nextSeq` 错写 | `$.cases[0].expected.disk.secondLoadNextSeq` |

## 验证与副作用边界

- H3-2C2 定向：`5 passed, 20 subtests passed`；
- H3-2C2 与既有 Harness：`101 passed, 219 subtests passed`；
- 完整 AgentRun 与协议：`108 passed, 215 subtests passed`；
- compatibility fixture 校验、默认单 Run、H3-2C1、H3-2B1、H3-2B2 CLI replay、Python/Node 语法和差异检查均通过。

定向测试显式拦截并确认没有创建 worker 线程、没有调用模型 Runtime、工具执行入口或网络入口。完成声明仅限四份脱敏合成最小 fixture 经现有生产 loader、公共 snapshot、serializer 和临时磁盘持久化入口稳定恢复。

本阶段不证明损坏记录、未知版本、真实用户 Session JSONL、worker/工具外部状态、模型、网络、浏览器/DOM、页面刷新、Runtime 原始事件恢复或发布门禁。

## 回退

回退时可独立删除 H3-2C2 schema、manifest、定向测试和本专题文档。四份既有 compatibility fixture、生产 loader、AgentRun/JSONL 协议以及所有 replay runner/schema 均无需迁移或回写。
