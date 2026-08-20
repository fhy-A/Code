# CODE-012 · 模型上下文能力与用户预算开发指导

> 状态：设计指导完成，尚未实施。本文是 CODE-012 的专题设计依据，不替代 [`TODO.md`](../TODO.md) 的未完成事项，也不替代 [`development-log`](development-log/README.md) 的完成事实。

## 1. 目标与非目标

目标是把“模型最多能接收多少上下文”和“用户愿意给本轮多少工作预算”拆成两个概念，由服务端唯一解析并冻结到 AgentRun，前端只展示和提交用户意图。

非目标：第一阶段不修改 `new-api-source`，不调用 New API 管理员 metadata API，不探测真实渠道，不读取/保存 Key、Authorization、上游账单或 Goal sidecar，不承诺所有 `/v1/models` 都提供上下文字段，也不在没有数值证据时从 400/超时推断窗口。

## 2. 当前事实与调用图

- 前端 `src/agent/compaction.js#getModelContextLimit` 按模型名维护 128K/200K/1M 族规则；`app.js` 在前台和 background 创建 Run 时分别调用它。
- `src/ui/panels.js` 的上下文百分比也调用前端函数，因此当前显示值是“按当前选中模型重新猜测”，不是 Run 冻结值。
- 服务端 `server.py#_agent_model_context_limit` 有第二套族规则；`_normalize_agent_context_limit` 只验证客户端 `contextLimit` 为 1024～2,000,000 的整数。
- `contextLimit` 已写入 AgentRun record、created event、snapshot 和恢复模型；服务端 90% 自动压缩阈值来自冻结值。
- Child delegation 与 Goal soft successor 已传入父 Run 的 `context_limit`；新 background/queue 则仍由前端创建时重新计算。
- 模型目录 `code-model-catalog-cache-v1` 只保存 `baseUrl + string[] model IDs`；`refreshModels()` 遍历所有 enabled Key，但只保留 `item.id`，丢弃其他字段。
- `_classify_runtime_failure` 能识别 `context_window_exceeded`，现有恢复只允许一次压缩重试，但错误事实没有结构化数值上限，也没有跨 Run 校准。

```text
/proxy/models → refreshModels → string ID cache v1
                           └→ model→keys 内存映射
selected model → 前端族规则 → createAgentRun(contextLimit)
                              → 服务端范围校验并冻结
                              → event/record/snapshot/recovery
                              → 90% auto compact
Child/Goal successor ────────────────继承父 Run
panel/session stats → 前端族规则（当前重复事实源）
```

## 3. 术语与产品口径

| 术语 | 定义 |
|---|---|
| 已验证硬上限 | 显式能力覆盖、可信 metadata 或有数值证据的运行时校准形成的不可突破上限 |
| Code 估算上限 | 统一模型族规则或未知 128K；置信度较低，用户可选择更大预算尝试 |
| 用户工作预算 | 用户在设置页为新 Run 选择的上下文预算；自动或具体 Token 数 |
| 最大输出预留 | 当前 `Max Tokens`，必须从可用输入预算扣除 |
| 安全余量 | 协议、工具 schema、估算误差的保留量；首阶段取 `max(4096, 最终限制×5%)` |
| 最终冻结 `contextLimit` | AgentRun 创建时服务端解析并写入 record 的总窗口限制 |
| 可用输入预算 | `max(1024, contextLimit - maxTokens - safetyMargin)` |
| 来源置信度 | explicit/calibrated 为 hard；metadata 为 verified；family/unknown 为 estimated |
| connectionScope | normalized baseUrl + canonical model 的稳定能力作用域，不含 Key |
| 向下校准 | 有明确总窗口数值证据后，只用更小值收紧当前及未来 Run |

## 4. 唯一解析公式

```text
estimatedCapability = family(model) 或 unknown=128K
declaredCapability = explicitOverride ?? trustedMetadata ?? estimatedCapability
hardCapability = min(declaredCapability, runtimeCalibration 若存在)

若 declared 来源为 explicit/metadata 或存在 calibration：
  requestedCapability = min(userBudget 或 hardCapability, hardCapability)
否则（只有 family/unknown 估算）：
  requestedCapability = userBudget 或 estimatedCapability
  允许用户选择更大预设/自定义值，但范围仍为 1024～2,000,000

finalContextLimit = requestedCapability
safetyMargin = max(4096, floor(finalContextLimit × 0.05))
availableInputBudget = max(1024, finalContextLimit - maxTokens - safetyMargin)
compressionTrigger = min(floor(finalContextLimit × 0.90), availableInputBudget)
```

“自动”表示不设置独立用户上限：hard 来源取 hardCapability，estimated 来源取估算值。用户预算只影响新 Run；旧 Run 和活动 Run不热更新。

## 5. 来源优先级与冲突规则

| 顺序 | 来源 | 能否被用户预算突破 | 冲突 |
|---|---|---|---|
| 1 | 专家显式能力覆盖 | 否 | 精确 connectionScope+model 唯一 |
| 2 | `/v1/models` 可信 metadata | 否 | 同 item别名/同 baseUrl多 Key 均取最小 |
| 3 | 统一模型族规则 | 是 | 用户明确尝试后可高于估算 |
| 4 | 未知模型 128K | 是 | 用户明确尝试后可高于估算 |
| 收紧层 | 运行时硬校准 | 否 | 并发、重复样本永远 min-merge |

## 6. connectionScope 与多 Key

`canonicalBaseUrl` 统一 scheme/host 大小写、默认端口和尾斜杠，拒绝 URL userinfo。持久键为：

```text
connectionId = SHA-256("code-connection/v1\0" + canonicalBaseUrl)
scopeKey = connectionId + "\0" + canonicalModelId
```

不得保存 Key、Key 尾号、Authorization 或可逆 Key 哈希。同一 baseUrl 的全部 enabled Key 属于同一连接；每个 Key 返回的 metadata 独立规范化，缺失者走族规则/128K，然后所有候选取最小。网关内部 channel 不可观测时不建立虚假 channel 身份。

## 7. 模型 metadata 与缓存 v2

可信总窗口字段白名单：`context_window`、`context_length`、`contextWindow`、`contextWindowTokens`、`max_context_tokens`、`maxContextTokens`。只接受整数 1024～2,000,000；拒绝布尔、浮点、单位字符串、描述文本数字、`max_input_tokens`、`max_output_tokens`。同一 item 多别名不同值取最小并标记 conflict。

```json
{
  "version": 2,
  "connectionId": "sha256:...",
  "models": [
    {"id": "model-id", "contextWindowTokens": 200000, "metadataStatus": "valid"}
  ],
  "savedAt": 0
}
```

v1 字符串 ID 缓存继续可读并视为 metadata missing；live 成功后写 v2。刷新失败保留旧缓存和当前模型列表。v2 损坏时不采用部分 metadata，回退族规则/128K；不能因损坏提高已知 hard 上限。

## 8. 服务端数据结构

唯一 resolver 位于服务端；前端不再保留模型族表。

```json
{"schema":"code-context-overrides/v1","revision":1,"entries":[
  {"connectionId":"sha256:...","modelId":"model-id","contextWindowTokens":200000}
]}
```

```json
{"schema":"code-context-calibration/v1","entries":{
  "<connection>/<model>":{
    "ceilingTokens":131072,
    "observedAt":"...","reviewAfter":"...",
    "evidenceCode":"context_window_exceeded"
  }
}}
```

文件存于 `data/`，使用跨进程锁、原子 replace、revision/CAS。损坏时 resolver 进入 degraded：使用安全 128K，不继续学习，等待显式 reset。`reviewAfter` 只提醒复核，不自动删除校准或提高限制。

模型解析响应至少包含 `modelId`、`connectionId`、`contextWindowTokens`、`source`、`confidence`、`hard`、`catalogRevision`。前端创建 Run 时可以发送旧 `contextLimit` hint，但服务端只允许它向下收紧权威结果；新客户端另传可选 `contextWindowTokens` 和 `contextBudgetTokens`。

## 9. UI 契约

复用设置页模型区现有 Temperature / Max Tokens 布局，增加“上下文预算”：

```text
桌面： [Temperature] [Max Tokens] [上下文预算]
窄屏：按现有 setting-row 安全换行，不横向溢出

上下文预算：自动 | 64K | 128K | 200K | 400K | 1M | 2M | 自定义
模型能力：1M（metadata · 已验证）
用户预算：400K
实际预算：400K；可用输入约 376K（已扣输出与安全余量）
```

estimated 来源允许选择更大值并显示“高于 Code 估算，可能被上游拒绝”；hard 来源则禁用/钳制更大预设。自定义值必须显示钳制原因。第一阶段不增加复杂逐模型覆盖 UI；专家覆盖属于阶段 C，可在现有设置页使用带预览和校验的高级 JSON。

## 10. AgentRun 兼容与继承

- 旧 Run 有 `contextLimit`：原样恢复，禁止用新 metadata/预算/校准改写。
- 旧 Run 缺字段：保持当前服务端族规则兼容。
- 新字段 `contextWindowTokens`、`contextBudgetTokens` 可选；`contextLimit` 继续表示最终冻结值。
- 旧客户端 hint 只能向下钳制，不能提高 hard capability。
- Child、delegation、Goal soft successor继承父 Run冻结值。
- queue/background 在入队/创建时冻结；排队期间设置变化不改已入队任务。
- 同 Session 的新普通用户轮次是新 Run，才读取最新设置/metadata/校准。
- 运行中百分比读 AgentRun snapshot；终态会话信息读最后一个前台 Run 的可选冻结值；旧 Session 再回退 resolver。

## 11. 发送前检查与超限恢复

发送前估算输入，超过 `availableInputBudget` 时先走现有压缩/明确提示，不向上调限制。运行时仅当错误已分类为 `context_window_exceeded`，且结构化字段或明确标签给出“总窗口”单一整数，并严格小于当前冻结值时学习。模糊 400/422、429、502、timeout、connection、content filter、安全拦截、当前 prompt token 数都不得学习。

明确超限后：当前 Run 立即向下收紧，沿用既有“一次压缩恢复”上限；跨 Run持久化按 scopeKey min-merge。任何自动过程都不能提高校准；只有显式 reset 或专家覆盖修改才能解除。

## 12. 迁移、失败与回滚

- v1 cache 原地可读；v2 可通过删除新 key 回滚到 v1/族规则。
- overrides/calibration 新文件均为可选；停用 resolver 新层后旧 Run仍可恢复。
- 前端 bundle/classic 必须共用同一模块与服务端响应。
- metadata 缺失/冲突/越界、缓存损坏、配置损坏和存储锁失败均 fail-closed，不清空用户 Key、不改旧 Run。
- 回滚不得删除用户校准证据；先停用读取，再由用户明确决定 reset。

## 13. 安全与隐私

持久化内容只含 connectionId、canonical model、数值、来源、时间和 revision；禁止 Key、Authorization、原始错误正文、请求内容、账单、Session/Goal 内容和无关绝对路径。诊断只记录枚举、数值范围和哈希作用域。

## 14. 分阶段实施与文件候选

### A · 统一 resolver + metadata/cache 兼容

候选：新增服务端 resolver/store 模块，`server.py`、`app.js` 模型目录、`src/agent/compaction.js`（删除族表，仅保留调用）、模型目录/AgentRun测试。完成 resolver、v1/v2、connection、多 Key最小合并。

### B · 用户预算 UI + Run 冻结/展示

候选：`src/features/settings.js`、`index.html`、`styles.css`、`src/core/i18n.js`、`app.js`、`src/ui/panels.js`、AgentRun/前端/H4测试。完成预设、自定义、公式、冻结与展示。

首个交付允许 A+B 合并；不得静默混入 C/D。

### C · 专家能力覆盖

版本化配置、Settings 高级 JSON、预览/删除/回退。需独立 STRICT 审批。

### D · 有证据的向下校准

数值错误提取、per-Run 收紧、原子 min-merge、review/reset。需独立 STRICT 审批。

### E · 综合验收

bundle/direct classic、刷新/重启、旧 Run、Child/Goal successor、queue/background、多 baseUrl/多 Key。

## 15. 验收矩阵

| 层级 | 必须覆盖 |
|---|---|
| 自动单元 | 64K/128K/200K/400K/1M/2M、自定义、alias、范围/公式、metadata 白名单与冲突 |
| 持久兼容 | cache v1/v2、旧 Run有/无 contextLimit、可选新字段、损坏/锁/CAS |
| 运行时 | 前台、queue/background、Child、Goal successor、一次压缩恢复、模糊错误不学习 |
| UI | 三列/窄屏、自动/预设/自定义、能力/用户/实际三值、钳制/估算警告、中英文 |
| H4 | bundle/classic、刷新、切 Session、200K/1M、多连接、多 Key、旧 Run恢复、压缩阈值一致 |
| 人工 | 设置可理解、警告不误导、较大预算可尝试但 hard 值不可突破 |

## 16. 停止条件与最终完成定义

出现新的上游 metadata 语义、需要按真实 Key区分能力、要改变旧 Run冻结语义、要自动提高校准、要增加第二套前端族表，或 A+B 需要混入专家覆盖/学习时立即停止重审。

CODE-012 最终完成需证明：服务端唯一 resolver；前端能力/预算/实际值与 Run/压缩一致；128K/200K/1M/2M、自定义、同模型多连接/多 Key、metadata 缺失/损坏、旧 Run、Child/Goal successor全部通过；校准只向下且可解释/reset；无 Key/业务数据泄漏；bundle/direct classic 与回滚路径通过。
