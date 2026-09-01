# Harness H3-2D3：手动压缩失败与持久化边界

## 阶段定位

H3-2D3 在 H3-2D2 成功路径证据之上，闭合手动压缩的失败终结、Session 所有权、非阻断归档警告、最终保存自动重试、显式保存重试和操作锁清理。本阶段修改生产 `app.js`、消息投影与 i18n，并新增独立、严格版本化的 failure-boundary evidence schema、脱敏 fixture 和定向测试；没有修改 `server.py`、Session JSONL 顶层结构、HTTP endpoint、AgentRun/Runtime、Run replay runner/schema、`beforeunload`/`sendBeacon`、`package.json`、H4 或发布脚本。

evidence profile 固定为 `h3-2d3-manual-compaction-failure-boundaries` v1，scope 为 `session-bound-failure-and-persistence-retry`。测试执行当前 `app.js` 的精确源码切片，不是公开模块 API。D3 不是单 Run或 multi-run replay，不并入既有轨迹、事件、检查点或恢复计数。

## 19 个固定场景

suite 按固定顺序执行以下 19 个场景：

1. `compact-throws`
2. `compact-ok-false`
3. `summary-build-throws`
4. `archive-fails`
5. `first-save-fails-retry-succeeds`
6. `both-saves-fail`
7. `apply-fails`
8. `repeat-confirm`
9. `switch-before-confirm`
10. `switch-during-compact`
11. `target-changes-during-compact`
12. `switch-during-save-retry`
13. `state-appended-before-retry`
14. `save-response-lost-after-server-write`
15. `target-changes-during-retry`
16. `second-compaction-blocked-pending`
17. `explicit-retry-succeeds`
18. `failed-marker-persistence-retry-succeeds`
19. `operation-lock-render-throws`

确定性 suite hash 为：

```text
bf795a33b981e7034196b003088a5a82a73b7221d5ec6784680e7f5ea3dc4985
```

文件基线为：

| 文件 | SHA-256 |
|---|---|
| failure-boundary fixture | `7fed5f8cd5334aebd04073e75c0dbf14ae31a267285f402bab47a984bf95d5c4` |
| failure-boundary schema | `f95094620c0a8f42fe3c5845b5fab8b61104356160e33485abd561167aa68d9a` |
| failure-boundary test | `9b852213c487e5dcf580ca85429644d423cbdd6041f0f6a4ab8e3854522b0bf0` |

2026-08-14 发布门禁受控刷新连续生成两次相同证据。19 个场景的 marker、调用、目标 Session、保存重试、脱敏、锁恢复和副作用字段均保持不变；CODE-004 的 UI 结构只改变每个场景的 `uiHash`，两个带 pending 投影的场景同时改变 `pendingUiHash`，随后派生更新 19 个 `scenarioHash`、D2 source fixture 哈希和 suite hash。该刷新没有删除断言或扩大冻结边界。

2026-09-01 v0.6.7 发布门禁再次受控刷新 UI 冻结证据。D2 source fixture 更新为 `01b824a3a2bc8b7bbe0570304e3bcdf00bda520dea8e5345c14f9452055ba496`；两次独立生成的 19 场景 suite 完全一致，只更新每个场景的 `uiHash`、既有两个 `pendingUiHash`、由它们派生的 `scenarioHash` 与 suite hash。对 v0.6.6 只读临时导出逐场景比较后，19 个移除 UI / pending UI / scenario hash 字段的规范哈希全部相等，固定 case 顺序、dispatch 身份和 8 条 mutation 首差异路径也相等；当前 slice 继续保持 `75508cb263c790549546faa08adf3941d0964693b6d73e659c29fe3d38174710`，没有删除断言或改变失败、保存、权限和副作用语义。

## Session 所有权与保存链

手动压缩在确认弹窗建立时固定 `targetSessionId`，后续 messages、stats、lastUsage、marker、archive、save 和 retry 都通过目标 Session 访问器处理。页面切换不取消已发起操作，但后台目标的变化不会覆盖当前页面；只有目标仍是当前 Session 时才刷新对应消息区、统计和 toast。

运行中使用目标内容指纹检查并发变化，避免把旧快照覆盖到已经新增消息的 Session。`cacheActiveSessionState()`、`saveCurrentSession()` 和 Run checkpoint 清理统一复用现有 per-Session `saveSessionState()` 保存链；保存 payload 由生产 `buildSessionSavePayload()` 同时装入 messages、stats、lastUsage、title 与当前 runState。没有复制 Session 保存状态机，也没有修改持久化协议。

## 失败终结与错误安全

- compact 请求异常或 `ok:false`：保留原历史、stats 和 lastUsage，不生成 summary，不调用 archive；只终结一个脱敏 failed marker。
- summary 构造异常：以 `summary_build / summary_build_failed` 终结，原历史保持，没有半应用 summary 或 archive。
- archive 失败：保持非阻断，压缩仍为 completed；marker 记录 `archiveStatus: failed / archiveErrorCode: archive_failed`，UI 显示稳定警告，不自动重试 archive。
- apply 失败：原子恢复目标 Session 的 messages、stats 与 lastUsage，只保留一个 `state_apply / state_apply_failed` marker。
- 最终保存第一次失败：生成不含 Session、时间或正文的 `compactionId`，使用目标 Session 最新状态自动重试一次；第二次成功仍保持 completed，且不保留 `persistenceStatus`。
- 两次保存失败：保留完整原历史和 summary，在同一 marker 上记录 `persistenceStatus: failed` 与有界错误码；同 Session 在 pending 解除前禁止再次压缩。
- 显式重试只保存目标 Session 当前完整状态，只更新对应 marker 的 persistence 字段；不会再次调用 compact、archive、summary factory，不会再次创建 marker或清零统计。

持久化字段只使用固定枚举 `errorStage`、`errorCode`、`archiveStatus/archiveErrorCode`、`persistenceStatus/persistenceErrorCode` 和必要时的 `compactionId`。原始异常正文、Key、供应商响应、请求正文、Session ID、真实路径和无限长错误不会进入 Session JSONL；用户文案只由固定错误码映射到本地化文本。

## failed 与 persistence failed 的组合语义

当 marker 同时为 `status: failed` 和 `persistenceStatus: failed` 时，生产消息投影显示“上下文压缩失败，且失败状态尚未保存”，保留“重试保存”按钮，但绝不显示“上下文已压缩”。对应定向场景的调用轨迹为：

```text
compact → save:1 失败 → save:2 失败 → 显式 save:3 成功
```

该场景固定 compact 1 次、archive 0 次、summary factory 0 次、save 3 次。显式重试只增加一次 save；原 13 条历史仍是精确前缀，重试前新增消息和当前标题进入最新 payload，stats/lastUsage 不变。保存成功后只清除 persistence 失败字段，marker 最终仍为 `failed / compact_request / compact_request_failed`。

专属变异首差异路径为：

```text
$.results.failed-marker-persistence-retry-succeeds.pendingUiHash
```

## 操作锁异常清理

`compactConversation()` 与 `retryManualCompactionPersistence()` 在登记 `manualCompactionOperations` 后，把后续指纹、快照、标题、首次渲染和保存准备放在可靠的 `try/catch/finally` 边界中；只有本次调用实际登记的操作才在 `finally` 删除，不能误删既有锁。

`operation-lock-render-throws` 在登记锁后的首次生产 render 调用注入异常。结果为一个稳定的 `state_apply / state_apply_failed` marker，操作锁数量回到 0，未处理 Promise rejection 为 0；随后同一 Session 能重新打开唯一确认处理器，取消后 confirm/cancel/modal 监听器全部归零，且重新打开/取消不增加 compact 或 save 调用。专属首差异路径为：

```text
$.results.operation-lock-render-throws.lockRecovery.operationCount
```

## 响应丢失与最新状态收敛

`save-response-lost-after-server-write` 先让真实临时 `save_session` 完成磁盘写入，再由响应适配器抛出合成连接错误；后续使用目标 Session 当前状态重试并通过生产 `read_jsonl()` 复读，最终只存在一个 summary 和一个 marker。`state-appended-before-retry`、`target-changes-during-retry` 与显式重试场景共同证明重试不会使用过期完整快照覆盖后续消息或标题；请求期间状态继续变化时，不会错误清除 pending。

## H3-2D2 历史受控重基线

D3 修改了 `compactConversation()` 精确切片及其依赖，因此 H3-2D2 从提交 `f5a57e2` 的收口基线受控更新到当时的 D3 收口基线。下表保留该次历史对比；当前发布门禁值以上方 2026-08-14 受控刷新和 H3-2D2 专题为准。该次只允许以下结构证据变化：

| 对象 | H3-2D2 收口值 | H3-2D3 最终值 |
|---|---|---|
| 源码切片 SHA-256 | `1264f4f9d7d46c15012b4d0d092d52819f2e8c41daf5c4561ec0286b733052b8` | `6df39b85c5ae94f31a1fa5ae2fe71d2c18eb688fea8c1a7fe102d75bf0d102f5` |
| 切片字符数 | `5732` | `20676` |
| D2 replayHash | `36e0206d1be87e80bade8a0d6a568fa1f6e2e19747e858964727e0f21b1d4c26` | `db2a14b1d572606e9d5a1ed0c494bd0f6e801e31ff20feb0e9e40b9164ce967a` |
| D2 fixture 文件 | `56584599d968fd7cfcdfad17cc56ed59a7ec8d18c7ab27b5fbe33d5ec3eda586` | `1fac9a92faae6084d578d94daa8e7cd3e7a68beb57df94734f065c4927170384` |
| D2 test 文件 | `f681fab3d920a3377be79a4bdb4a7437531c891cda45b2007b39f2a1497cc85b` | `79ad0a04be9c91a27c73a83f16416d8bf57a2a6057f31b951e3f50ce4c7db328` |

人工逐段比较确认 D2 全部领域语义哈希不变：

| 领域 | SHA-256 |
|---|---|
| 源历史 | `0ecd9f0f2ccacca9d5a4e3281dfabc1cf6d09c4c81da867977d302b0598e40bf` |
| 最终 messages | `a71218ce9c3bf1ea776dc170938c5aa918d8d23793bf34a7a3d27b9e0c5abd2e` |
| summary / marker | `74eb698bc8d30e4aeb49c7048a0a816b368c2778a20f4ce154aef5a337ab74e7` / `14a60239fb4c24479f5a662731b7e78a353bfcd800bb43290e35f72b2d1921b6` |
| archive payload / record | `dd417968b48653557514100ca51a99cb276070dbd610502745ef577c48ff39e9` / `0540ccaef10e329c8d212f8f5a8076d4cf2d04063af89fee71247b7ba83c0df1` |
| serialized / save payload | `3a8f9f210d9e5daccc56789cd4a1ef8c144d89a829f6f55f68eff8d32e58779f` / `546f16466c9a3a092638f2ab47f3e18bcad0fa52487dcdb04999a1e662e725ed` |
| model context / API payload | `8d5972e4b0b9548099d2efbb95ecb1f14ff8d9dbe1bf62c603d3ec93d3108958` / `0e5dccd19e37ab2c5b814916035a27965b77121333605c65701707f0dc53b330` |
| UI HTML / 可见文本 | `7253fa07caca7bb89087ce706d45889ada1a305492f2b2bd9204a027a85f651c` / `92145b03f68be59e0a83c45b0f7288d78c1a36faada1edc8e8833b4ed047b397` |

## 验证结果

- D2+D3 定向：`12 passed, 38 subtests passed`；
- 前端模块：`169 passed`；
- 保存链与旧结构回归：`128 passed, 4 subtests passed`；
- 全部 Harness：`109 passed, 272 subtests passed`；
- 完整 Python：`1109 passed, 737 subtests passed`；
- 默认单 Run仍为 `17/124/25/25/4`，replay hash 保持 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`；H3-2C1、B1、B2 CLI 哈希也保持不变；
- `npm run check:frontend` 与随后独立 `npm run verify:frontend` 均通过，bundle、preview、经典回退和 bundle 语法正常；`dist/` 是忽略的本地产物，不进入提交；
- 隔离本机临时页面直接加载当前生产 i18n 与消息投影：中文、英文及切回中文即时正确；重试按钮在 Promise 处理中禁用、完成后恢复，compact/archive/summary 计数保持 0。临时页面、服务和脚本均已清理，不污染既有 Session。

## 完成声明与回退

H3-2D3 证明脱敏合成失败矩阵在当前精确源码切片、目标 Session 访问器、统一保存链、生产消息/i18n 投影和临时持久化组合下的契约。它不证明真实网络、真实摘要质量、页面刷新、完整 DOM 生命周期、Runtime 原始事件恢复、H4 隔离浏览器 E2E 或发布门禁；人工 i18n 检查也不替代完整应用浏览器生命周期验收。

本阶段没有新增 marker/Session/JSONL 协议字段或 HTTP endpoint。独立回退可撤销 D3 生产改动、三个 D3 evidence 文件、必要的旧源码断言适配和 D2 受控重基线，并删除本专题及对应事实源更新；无需迁移旧 JSONL。回退时必须同时恢复 H3-2D2 的切片、fixture 和测试文件哈希，不能只回退其中一层。
