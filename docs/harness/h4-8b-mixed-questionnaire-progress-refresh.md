# H4-8B 混合问卷渐进进度与刷新恢复

## 目标与完成范围

H4-8B 冻结一个确定性的三题 `request_user_input` 浏览器生命周期。三题全部为 required，并严格按以下顺序作答：

1. single：从两个固定选项中选择 B；
2. multiple：从三个固定选项中选择 A、C，同时填写固定 Other marker；
3. text：填写固定 text marker。

默认 bundle 与 direct classic 共用同一套生产 UI/API、Chromium 页面操作和隔离 loopback 假上游。场景不调用真实模型、外网、凭据或注册工具执行器，也不改变生产代码、问卷协议、Session JSONL、AgentRun/Runtime 协议或持久化格式。

## 公共测试结构

H4-8A 与 H4-8B 共享三个低层原语：`beginQuestionnaireLifecycle()`、`completeQuestionnaireLifecycle()` 和 `reloadCompletedQuestionnaireLifecycle()`。它们没有 H4-8A/H4-8B 业务分支，推进并断言两阶段共有的真实页面/API transport 生命周期，返回原始 AgentRun、Runtime、Session、metrics、reload 快照与共享请求计数投影；不包含 H4-8A/H4-8B 专属 projector 或哈希逻辑。

两阶段的领域投影、精确断言、evidence label 和语义哈希继续分离。H4-8A 的九项冻结值没有重基线；H4-8B 只增加混合控件、渐进 Session 进度、Q3 前完整刷新和三答案终态语义。

## 渐进进度证据

初始等待态为同一 AgentRun 的 `waiting_user_input`，唯一 pending input 包含原始三题定义，首个 Runtime 已完成且 active Runtime 已清空。随后通过真实 radio、checkbox、Other 输入框、text 输入框和 confirm 按钮逐题推进：

| 阶段 | Session `userInputRequest.questions` 状态 | 当前 DOM |
|---|---|---|
| 初始 | `pending / pending / pending` | Q1，进度 1/3 |
| Q1 后 | `resolved / pending / pending` | Q2，进度 2/3 |
| Q2 后 | `resolved / resolved / pending` | Q3，进度 3/3 |
| Q2 后完整刷新 | `resolved / resolved / pending` | 仍仅 Q3，进度 3/3 |

Q1 与 Q2 的确认只保存 Session 局部进度，不提交最终 Agent input。自 Q1 开始至 Q3 最终确认前，AgentRun POST、Runtime POST、`/input`、`/resume`、上游 chat、新 AgentRun、新 Runtime、注册工具 delegation/execution 的增量均为 0。

Q2 后执行一次完整页面刷新。刷新后证据同时证明：

- AgentRun、requestId、tool call 和 interaction execution 身份保持唯一且一致；
- Session 的 `runState.agentRunId` 与 `userInputRequest.agentRunId` 都指向当前 Run，title、reason、requestId 和 toolCallId 仍匹配固定契约；
- Session 保留 Q1 的 single B 与 Q2 的 multiple A+C、Other，Q3 仍为 pending；
- AgentRun `pendingInput` 仍是服务端原始三题定义，不被前端局部进度污染；每题均明确不存在 `status`、`selected`、`text`、`other`、`answer`、`value`、`values`、`checked`、`resolved` 等进度字段；
- 问卷 panel 仍唯一，DOM 只显示 Q3 的 text 控件和 3/3 进度，不重复 Q1/Q2；
- 刷新不产生 AgentRun/Runtime 写入、input/resume、模型请求或工具执行重放。

尚未确认的当前题草稿不属于本阶段持久化承诺；本场景只在 Q2 已完成保存、Q3 尚未填写时刷新。

## 单次提交、同 Run 继续与终态

Q3 填入固定 text marker 并唯一确认后，同一 AgentRun 继续并完成第二轮模型请求。固定计数如下：

| 观察层 | 计数 |
|---|---:|
| AgentRun 总数 / AgentRun POST | 1 / 1 |
| Runtime 总数 / 浏览器 Runtime POST | 2 / 0 |
| `/input` POST | 1 |
| `/resume` POST | 1 |
| 上游 chat | 2 |
| registered tool delegation | 0 |
| registered tool execution | 0 |
| durable native interaction execution | 1 |
| questionnaire tool receipt | 1 |

AgentRun 的 12 个事件严格为：

```text
created → model_started → model_completed → tool_started
→ user_input_required → user_input_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

其中 `waiting_credentials` 是当前生产恢复链的耐久事件名，并不表示本场景使用了真实凭据；问卷作答前的状态仍是 `waiting_user_input`。

终态 Session 恰好保留六条逻辑消息，顺序为：

```text
user → assistant tool-owner → questionnaire tool-call
→ user-input-summary → questionnaire tool-result → assistant final
```

`user-input-summary` 使用既有 user role、`_system=true` 和 `skipApi=true`，不作为普通模型用户消息。Session summary、AgentRun durable tool result 与假上游实际 receipt 均按 Q1→Q2→Q3 顺序独立核对：single 仅为 B；multiple values 为 A、C 且 Other marker 唯一；text marker 唯一。投影比较语义字段和 marker 次数/顺序，不把前端省略的不适用字段与服务端 `null` 表示误判为差异，也不冻结本地化分隔符或完整显示正文。

终态 DOM 不再显示 questionnaire panel、pending 或 active trace；原 user、唯一 tool process/item、argument/result detail、三行有序摘要和唯一 final 均存在。完整刷新后，Session/AgentRun/Runtime 与 DOM 语义投影保持一致，AgentRun/Runtime 写入、`/input`、`/resume`、上游 chat、registered tool 与 native interaction execution 的刷新增量均为 0。

## 稳定语义哈希

随机 AgentRun/Runtime/Session 原始身份、端口、时间、原始请求体、完整 HTML、完整 JSONL 与本地化正文均不进入哈希；随机身份只以 alias 或 match 布尔归一。固定受控 request/tool/question/option/answer 的 name、value、role、kind、marker 可以作为稳定语义字段或匹配结果进入，并同时冻结数量、类型、顺序和状态。bundle 与 direct classic 的九项 SHA-256 精确相等：

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `0e66c7254f24708cf2f09c10ab2cc456a49954a0d691a9aaf61ce12d67d3184f` |
| `progressSnapshot` | `372e17ded267937f8f1ca30c683cf7ce8b548af976c4979f617af8fa04d006aa` |
| `progressDom` | `d635937b610a1e098910ed3ddb43c2f6ab734e349401d9336e812588b59a85e6` |
| `inputSubmissionProjection` | `5082f9c4a6eded92d612adae0334717b94619f295eaaabf86708e4c9f0b68eb4` |
| `runtimeProjection` | `7f4f58396717deb173b18dd703f2ff76557455cd4aee661cd71c3c4bc5aa1b31` |
| `sessionRoleContent` | `ba570ba870a189929e69069ec42c83747102a292b8118a153900185c27686bf0` |
| `sessionInputMeta` | `89823e3f8e29025bd03d50d33bd063f70ca68d6558a7f465ca5b83dd5591b820` |
| `terminalDom` | `bcd0070502f78af981739b6116e93adbaa2d5f3c5f542f6d827de3c3eac7b7c1` |
| `refreshLifecycle` | `12189043590d29b528a2beaac58e4f1c49f66d0d0a1e4ff2889c3dd7b69f612f` |

同一最终文件树下，H4-8A bundle/classic 也重新运行通过，其九项运行结果与既有常量逐项相等。

## 验证事实

- H4-8B frozen bundle、direct classic 和 bundle+classic pair 均通过，九项哈希逐项相等；
- H4-8A bundle+classic 通过，旧九项哈希未变化；
- H4 infrastructure 自检通过；
- 连续两轮标准 H4 均为 `55 passed`，`workers=1`、`retries=0`；
- questionnaire/Agent/route/frontend 定向为 `9 passed`；
- 完整 pytest 为 `1131 passed, 751 subtests passed`，另有 3 条固定损坏 TIFF 输入触发的预期 Pillow EXIF 警告；
- `npm run check:frontend`、Node 语法、Python AST 语法和 `git diff --check` 均通过；
- 结束时 H4、headless Chromium、isolated host 相关进程与监听均为 0，`code-h4-e2e-*` 临时根为 0；既有失败诊断原样保留。

Python 回归只在测试子进程内临时设置 `PYTHONPATH`，复用本机已有 Python 3.12.10、pytest 9.1.1、requests 2.32.5 与 jsonschema 4.26.0；没有安装依赖、创建或修改虚拟环境，也没有持久修改 Process/User/Machine 环境。

## 证明边界、兼容性与回退

H4-8B 只证明固定 all-required 三题、single B、multiple A+C+Other、text marker、Q2 后同进程完整刷新、最终单次提交、同 Run 继续和终态刷新。它不证明：

- optional、cancel、skip、back-edit、invalid schema 或任意题数/选项数；
- 重复/并发提交、多标签页、多个 pending input、stale/unknown request；
- `/input`、`/resume`、Session save 或模型请求失败与重试；
- 浏览器崩溃、服务重启、跨进程 active 恢复或草稿级持久化；
- authorization、Child、queue、steer、detached 或 background 生命周期；
- 真实模型、外网、凭据、注册工具副作用或通用 exactly-once；
- Firefox/WebKit、发布行为、主观视觉或无障碍验收。

本阶段没有生产、协议、schema 或持久化格式变更，因此没有数据迁移；独立回退只需撤销本专题及两份 H4 测试增量，不回写历史 Session。

统一 TODO、开发日志和日志索引仍由并行 workbar 协作者现场占用，本提交不修改这些共享事实源。因此本专题是 H4-8B 的独立证据收口，不代表统一项目总账已经归档；待共享现场释放后，应另做 docs-only 归档。
