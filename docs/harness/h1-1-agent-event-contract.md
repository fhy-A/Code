# Harness H1-1 Agent 事件契约纯函数基线

完成时间：2026-08-02 20:05（Asia/Shanghai）

基线提交：`d20806a`

阶段性质：新增纯协议模块与契约测试，不接入生产事件链

> 后续状态：H1-2 已将本模块接入服务端内存影子观察，但仍未改变事件、持久化或前端协议；当前边界见 [`h1-2-server-shadow-validation.md`](h1-2-server-shadow-validation.md)。以下内容保留 H1-1 完成时的阶段事实。

## 1. 阶段目标

H1-1 将 H0 冻结的 22 类现有耐久事件转成可执行的版本 1 契约，并先在完全脱离运行时的纯函数层验证以下规则：

1. 当前无版本事件可以兼容归一到 v1；
2. v1 事件信封、事件类型、允许载荷和最低必需字段可验证；
3. 未知事件和未来字段不会导致旧消费者崩溃；
4. 凭据字段和凭据形态文本不能进入事件；
5. 事件序号单调，完全相同的重复投递幂等；
6. Run、模型轮和工具执行的终态不可逆。

本阶段没有让 `server.py` 导入新模块，也没有给现有持久事件增加字段。当前生产事件仍保持原来的无版本 `{seq, type, data, createdAt}` 信封；协议 v1 只存在于新纯函数模块的规范化输出中。

## 2. 唯一实现入口

事实源：`agent_protocol.py`

公开能力：

| 接口 | 作用 |
| --- | --- |
| `AGENT_EVENT_PROTOCOL_VERSION` | 当前规范版本，固定为 `1` |
| `AGENT_EVENT_SPECS` | 22 类事件的允许载荷和最低必需字段 |
| `normalize_agent_event()` | 将当前无版本事件、v1 或未来稳定信封归一到 v1 |
| `AgentEventSequenceValidator` | 单运行事件序号、重复与冲突检查 |
| `validate_transition()` | Run、模型轮和工具执行迁移检查 |
| `public_contract_summary()` | 生成可序列化的契约摘要，供测试和后续诊断使用 |

模块不读取网络、文件、会话、配置或全局运行状态；输入相同则输出相同。时间戳由调用方提供，纯函数不会读取当前时钟。

## 3. v1 规范信封

规范化事件固定为：

```json
{
  "protocolVersion": 1,
  "seq": 1,
  "type": "model_started",
  "data": {
    "round": 1,
    "runtimeRunId": "runtime-fixture-1"
  },
  "createdAt": "2030-01-01T00:00:00Z"
}
```

归一结果同时返回：

- `sourceProtocolVersion`：来源事件的版本；现有无版本事件记为 `0`；
- `knownType`：当前 v1 是否认识该事件类型；
- `diagnostics`：兼容、未知字段、结构错误或未来版本诊断。

这组辅助信息暂不进入 AgentRun 持久记录，也不进入用户会话 JSONL。

## 4. 兼容与未知字段策略

### 4.1 当前无版本事件

缺少 `protocolVersion` 的现有事件按来源 v0 读取，保持 `seq/type/data/createdAt` 原值并补成 v1 规范信封，同时产生 `legacy_unversioned_event` 信息级诊断。

### 4.2 未知事件

未知 `type` 不抛错、不改名，完整保留类型和 `data`，返回 `knownType=false` 与 `unknown_event_type` 诊断。后续投影可以忽略该事件并继续处理已知状态。

### 4.3 未知字段

- 信封未知字段不会进入规范信封，只产生 `unknown_envelope_fields` 诊断；
- 已知或未知事件的载荷未知字段原样保留，并产生 `unknown_payload_fields` 信息级诊断；
- 这样既不让未来字段污染稳定信封，又避免旧消费者在转发或诊断时静默丢掉未来载荷。

### 4.4 未来协议版本

兼容模式可以按 v1 稳定信封读取更高版本，并产生 `future_protocol_version`；严格测试模式会拒绝尚未声明支持的更高版本。后续正式接入时不得假定未来版本语义与 v1 完全相同。

## 5. 严格模式与兼容模式

| 情况 | 兼容模式 | 严格测试模式 |
| --- | --- | --- |
| 当前无版本事件 | 归一并诊断 | 归一并诊断 |
| 已知事件缺少最低字段 | 保留并诊断 | 抛出 `AgentProtocolError` |
| 未来协议版本 | 按稳定信封归一并诊断 | 抛出错误 |
| 未知事件类型 | 保留并诊断 | 保留并诊断 |
| 未知载荷字段 | 保留并诊断 | 保留并诊断 |
| 凭据字段或凭据文本 | 始终拒绝 | 始终拒绝 |
| 非法迁移或序号间隙 | 诊断并保持兼容 | 抛出错误 |

H1 后续正式运行接入必须先使用兼容/影子模式，只记录脱敏诊断；测试继续使用严格模式。不能在没有观察差异前让正式任务因新增验证器失败。

## 6. 凭据拒绝

契约递归拒绝以下字段名的大小写和分隔符变体：

- API Key、Access Token、Authorization、Cookie；
- headers、keys、password、client secret。

字符串同时拒绝 Bearer 值和 `sk-` 形式凭据。`authorizationId` 等业务 ID 不会被误判，因为检查的是完整规范化字段名，而不是子串。

该规则只保护 Agent 事件。模型请求、工具实现、会话或日志仍需各自已有的凭据边界，不能因为事件校验存在就放宽其他安全措施。

## 7. 事件顺序和幂等

`AgentEventSequenceValidator` 以单个 AgentRun 的游标为边界：

- 新序号必须大于当前游标；
- 严格模式要求无间隙连续；
- 同一序号、同一规范内容再次投递标记为 `duplicate_event`，不再接受；
- 同一序号对应不同内容始终抛错，防止冲突事件覆盖；
- 兼容模式遇到间隙会接受并产生诊断，便于从非零游标或不完整历史继续观察。

这只是序号与内容检查，不是 H2 reducer。它不会生成消息、改变状态或执行工具。

## 8. 状态迁移表

### 8.1 Run

迁移表覆盖 H0 的 8 个实际顶层状态。`completed/failed/cancelled` 只能保持自身，任何终态回到 `model/tools/waiting_*` 都是非法迁移。

### 8.2 模型轮

模型轮使用 `pending/started/completed/recovery/failed/cancelled` 描述协议阶段。完成后可以进入下一轮 pending 或进入 recovery；failed/cancelled 不可恢复。

### 8.3 工具执行

工具迁移表覆盖 H0 记录的 10 个执行状态：`running`、两类等待、两类 applying、`authorized`、两类 child 等待以及 `completed/cancelled`。工具终态不可回到 running 或 applying。

这些表只声明允许边界，不推导 AgentRun 的当前状态，也不替代线程、Condition、进程取消、工具回执或授权逻辑。

## 9. 自动验证

定向结果：

- H1-1 契约测试：`9 passed, 135 subtests passed`；
- H0 + H1-1 联合测试：`22 passed, 153 subtests passed`；
- AgentRun v1/v2/v3、旧上下文字段与旧 JSONL 定向兼容：`3 passed, 3 subtests passed`；
- 完整回归：`936 passed, 396 subtests passed in 69.77s`；
- `npm run check:frontend` 通过 bundle、构建新鲜度、JavaScript 语法和经典回退门禁；
- Python 语法与 `git diff --check` 通过。

每个现有事件类型至少有一个严格契约子测试；15 条 H0 无版本轨迹的 106 个事件全部执行兼容归一并保持原始 `data`。

## 10. 回退与下一步

H1-1 可通过删除 `agent_protocol.py`、契约测试和本说明整体回退，不需要修改或迁移任何 AgentRun、JSONL 或前端数据。

下一小阶段 H1-2 建议：

1. 在服务端新增默认关闭或兼容模式的影子验证入口；
2. 新事件产生后同步归一并记录内存级脱敏诊断，不阻断正式运行；
3. 明确功能开关和诊断上限；
4. 用 15 条 H0 轨迹及现有假上游验证影子结果；
5. 观察无差异后，再单独决定是否让新写入事件显式包含 `protocolVersion: 1`。

H1-2 仍不替换前端投影；前端旧事件适配和未知事件跳过策略应作为后续独立小阶段处理。
