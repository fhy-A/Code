# H4-6O forced-final 模型失败终态与刷新唯一性

## 完成范围

H4-6O 沿用 H4-6K 的固定 schema-valid、只读 `read_file` 行范围失败：

```json
{"path":"fixture.txt","startLine":2,"endLine":1}
```

默认 bundle 与 direct classic 共用同一参数化生命周期。前三个唯一 `toolCallId` 的同指纹调用均真实委托生产执行器并失败，`failureCount` 依次为 1、2、3；第四个新 `toolCallId` 的同指纹调用由生产限流器生成耐久 blocked execution 和唯一 `tool_retry_blocked`，但不再进入执行器。第五轮 forced-final 模型请求移除 `tools` 与 `tool_choice`、携带既有恢复指令，隔离假上游随后返回固定 HTTP 502。该失败类型复用现有模型错误语义，没有真实外部网络、凭据或新重试策略。

最终父 AgentRun 为 `failed/upstream_error`，共 24 个事件，`nextCursor=24`，耐久 `nextSeq=25`；五个 Runtime 的 cursor 向量为 `[4,3,3,3,0]`，最后一个 Runtime 独立闭合为 `failed/upstream_error/502/transient=true`，且没有第五轮 `model_completed`。完整计数为 chat 5、生产工具委托与真实执行各 3、耐久 execution 4、blocked 1、unsafe 0。

## 失败终态、持久化与计时

- 失败前可观测轨迹保持单一工具组和四个 failed 项：前三项为真实行范围失败，第四项为重复失败阻断。终态按现有健康快照回滚契约只持久化 user 与唯一 `error-recovery` assistant，不伪保留已回滚的工具轨迹、最终回答或完成 marker。
- 公共 AgentRun snapshot 的 `activeRuntimeRunId` 为空，Session `runState.runtimeRunId` 同样规范化为空；v4 原始耐久记录精确不含 `activeRuntimeRunId` 键。最后一个失败 Runtime 由独立 Runtime API 证据定位，完整 reload 不会重新激活它。
- 当前页和完整刷新后都只有一个顶部 `data-completed-run-status` 耗时投影，格式合法；主 assistant 页脚 `.run-time` 为 0，不重复展示同一时钟。
- 完整刷新保持同一 AgentRun、失败 assistant、runState 与耗时唯一；AgentRun POST、Runtime POST、chat、真实工具执行四项增量全部为 0。

### failed 主任务耗时修正

根因是 failed 路径先保存了不含耗时的 `error-recovery` assistant，之后才在内存调用 `finalizeRunTiming`，导致当前页可能显示耗时而刷新后丢失。修正保持 `makeRunCheckpoint` 先捕获失败终态，随后在同一 `persistRunCheckpoint` / `saveSessionState(..., persistMessages)` 保存边界之前，对同一个 error assistant 调用既有 `finalizeRunTiming`；现有序列化器继续只通过 `meta._responseTime` 保存该值。

该修正没有新增持久化字段、Session JSONL 格式、计时算法、AgentRun/Runtime/事件协议或额外事实源，也不迁移或补算历史上已经缺失耗时的失败消息。`setStreaming(false)` 仍只负责终态重绘，已经清空的计时锚点不会再次计算耗时。completed、paused/cancelled、detached/background/parallel 与 queue 的既有行为不在本次修正范围内。

## Harness 稳定性门禁

- TIFF 门禁继续严格要求完整刷新在新 document generation 内只有一次 preview GET。请求诊断只记录脱敏 preview key hash、主 frame document generation 和阶段，用于区分旧页卸载与新页恢复；没有修改产品图片缓存、请求计数、安全边界或持久化契约。
- H4-7B queue 门禁先以有界生产状态确认主 Runtime 与对应 Session checkpoint 已持久化收敛，再建立观察器并执行唯一一次真实 `Control+Enter`。收敛点之后仍严格证明 `keydown=1 → submit=1 → queue transition PUT=1 → DOM=1`；没有修改队列产品语义、增加提交、sleep 或 retry。

这两项都是 Harness 观察窗口与因果门禁的确定性修正，不是生产 TIFF 缓存或队列语义修改。

## 稳定语义哈希

随机 ID、绝对时间、端口、完整本地化错误正文、原始 JSONL 字节和完整 HTML 均不进入哈希。bundle 与 direct classic 的九项 SHA-256 完全一致：

| 投影 | SHA-256 |
| --- | --- |
| `eventProjection` | `86e0b2c456a1b3cc6733c5315a821f0bb353ed6cb3cc57cb1c38cb94ac0f7fc8` |
| `retryExecutionProjection` | `c4f4a8432ad9be01f331e72be1c9b6bd709bb7eda508c3b00604a2967d8c31fe` |
| `modelToolReceiptProjection` | `4d02940043fc3266a6e6bf6e2a94ab7e775dd539401e84f40255daa29ed1b721` |
| `forcedFinalFailureProjection` | `e8711527a19fc4bb557ba5a70c5bd87ec0f42590feb3d4c495e55b4416dce2f2` |
| `runtimeProjection` | `c5664f513a21625433061cae70db64840b791260fcc21a4d4812924312e5ee1e` |
| `sessionRoleContent` | `431b4ed43aa1395a0c9b439806bcdc49d813b0cc0784d01086fccf64401d2e5b` |
| `sessionRunState` | `eb9c72f48ea2c11e70730a1c1c87491d66fcbe7e822ac879101ee910f599da17` |
| `terminalDom` | `aae2e342c398f0d712b92ff87c54f10dab19be7cc26fbcebfb67bb24f762ccdf` |
| `refreshLifecycle` | `60b5a625b74c8855ddde66f04ff48057eb00146ceab75988db20144d2c067f78` |

冻结的 source/test SHA-256：

- `app.js`：`B3AE68651723F3D323C8F453D4BB620EFE94A294CAAC6370A3177C456820AE8E`
- `tests/e2e/h4/isolated_host.py`：`6EC8F6EAE5301D93C959ED5E9C1CF10733577E909F62DBB7EFF638B49834CAAF`
- `tests/e2e/h4/smoke.spec.cjs`：`10F4B19259D973599812633256987846CFAEAF8312631423D17AFAD9F21FCA8D`
- `tests/test_frontend_modules.py`：`4E5EE41FF4AB7C3335075C7193F3C27ADC8F7A886C37D35B95E3612EF6A4CD4F`
- `tests/test_p0_stability.py`：`74BCE281EE8814DC65D3E43481BEFD17CE05495F0079F10D9999EB21921376C3`

## 验证结果

- H4-6O bundle/direct classic 对等通过，H4-6K 旧九项哈希保持；H4 infra 通过。
- 最终五文件哈希下连续两轮标准 H4 均为 `49 passed`、单 worker、`retries=0`、exit 0。
- H4-7B/H4-7C/暂停取消相关定向为 `6 passed`；前端/P0 为 `232 passed`。
- 完整 pytest 为 `1129 passed, 751 subtests passed`；`npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源清理通过。
- 文档收口沿用上述同一 source/test 哈希下已经完成的完整矩阵；收口后只执行文档、链接、语法、diff、白名单与资源门禁，不把未重跑项目写成收口后重跑。

## 完成边界与回退

本阶段只证明固定同指纹、schema-valid、只读行范围失败的前三次真实执行、第四次耐久阻断、第五轮 forced-final 固定 502，以及 bundle/direct classic 的 failed 终态回滚、顶部耗时持久化和同进程完整刷新零重放。

本阶段不证明执行前 schema/parse 失败限流、不同参数或工具、错误交替、固定 HTTP 502 之外的其他模型错误类型、模型错误重试/恢复、跨进程 active 恢复、取消、长输出或真实外部副作用 exactly-once。独立回退只需撤销 failed 计时保存顺序、本阶段前端/P0 与 H4 测试增量及本专题/事实源更新；不涉及数据迁移、协议或历史记录回填。
