# Harness H3-2D2：手动压缩成功路径与完整可见历史契约

## 阶段定位

H3-2D2 为 Harness 总体方案第 6.3 节“手动压缩保留完整可见历史”建立独立、严格版本化的成功路径证据。本阶段只新增 evidence schema、脱敏合成 fixture 和一份定向测试；没有修改生产代码、既有测试、会话 JSONL、Run replay runner/schema、`package.json`、前端或发布脚本。

evidence profile 固定为 `h3-2d2-manual-compaction-visible-history` v1，scope 为 `exact-app-source-slice-success-chain`。它不是单 Run或 multi-run replay，不并入任何轨迹、事件、检查点或恢复计数。

## 精确源码切片的执行边界

`compactConversation()` 当前没有作为模块公开导出。测试因此从 `app.js` 的唯一 `async function compactConversation()` 起点，切到唯一 `function projectOptimisticFirstMessage(` 终点，执行当前 `app.js` 的精确源码切片；这不是公开模块 API 导入。两个边界标记各出现一次，切片包含实际 `hideCompactConfirm()`，字符数为 5732，SHA-256 为：

```text
1264f4f9d7d46c15012b4d0d092d52819f2e8c41daf5c4561ec0286b733052b8
```

切片先在隔离 Node `vm` 中编译，再执行 `compactConversation()`，并由测试触发一次真实 confirm click。VM 同时固定 `new Date()` 与 `Date.now()`；保存完成后确认监听器已清理，再次 dispatch 不增加 compact、archive 或 save 调用。

该哈希只用于在生产源码变化时提示人工复审，不能作为机械更新门禁。只要切片变化，就必须重新检查完整函数边界、依赖、状态顺序、副作用和证据结论，再决定是否更新测试与哈希。

## stub 与真实状态变化

隔离执行只提供被切片调用所必需的被动依赖：

- `apiJson()` 对 compact 返回固定脱敏摘要，并捕获 compact/archive 请求；
- `saveSessionState()` 只捕获最终参数并发出完成信号；
- render、streaming 与 toast stub 只记录调用；
- 最小 DOM stub 只保存监听器、分发一次确认并允许检查清理状态。

这些 stub 不追加消息、不创建或修改 marker、不构造摘要、不选择压缩范围、不清零统计，也不模拟持久化。原历史前缀、compact summary、`manual-context-compaction` marker、状态与统计变化都来自实际源码切片。

## 组合生产证据链

一份固定、脱敏的 13 条源历史在 `meta.evidenceMessageId` 中保存测试身份；不依赖会被生产序列化丢弃的任意顶层 `message.id`。成功链依次验证：

1. 压缩前冻结 13 条源消息的身份、顺序、逐条规范哈希和整段历史哈希。
2. 实际切片向 `/api/compact` 发送当前生产计划选择的 8 条 API 消息；压缩范围含 7 条源记录，其中 `tool-call` 不映射为 API 消息，所以 `compressCount` 为 6，保留范围为 6 条。
3. 实际切片捕获的 `/archive` 请求必须为 `PUT`，payload 与压缩前 13 条消息深度相等且不包含运行中 marker。测试先把预压缩历史写入临时 Session JSONL，再把同一 payload 交给真实 `CodeHandler.archive_session()`；生产 `read_json()/read_jsonl()` 复读 archive JSON 与复制的预压缩 JSONL。
4. 实际切片传给 `saveSessionState()` 的最终 messages 再交给生产 `serializeSessionMessages()/buildSessionSavePayload()` 和临时 `write_jsonl()/read_jsonl()`。复读后原 13 条历史仍是精确前缀，只追加一个 summary 和一个 completed marker，stats 为零。
5. 生产 `getModelContextMessages()` 先按 `meta.evidenceMessageId` 验证上下文选择；再经 `mapMessageForApi()` 后按 `role/content` 规范哈希验证 API payload，不要求 API payload 保留测试身份。结果只包含 summary/marker 上下文，没有旧消息泄漏。
6. 同一最终消息交给生产 `renderUserProjection()/projectMessages()`。HTML 文本投影中 12 个原历史可见哨兵各出现一次且保持顺序，compact summary 不作为普通正文出现，completed marker 只出现一次。

archive 与最终保存的绝对路径在调用前后都必须解析到独立临时根目录；测试不访问真实 `data/sessions`。实际临时文件为：

```text
save/final.jsonl
sessions/2026/08/06/session-h3-2d2-synthetic.jsonl
sessions/archive/session-h3-2d2-synthetic_2026-08-06T10-00-00.000Z.json
sessions/archive/session-h3-2d2-synthetic_2026-08-06T10-00-00.000Z.jsonl
```

## 确定性基线

| 对象 | SHA-256 |
|---|---|
| evidence fixture 文件 | `c3ea5a28bc980ef0bd60d12effeb442a6ce7032b77a41b6f34672f41e3cdee91` |
| evidence schema 文件 | `3b1426da4a914ec89d72988636a18b515c2cbf3a72e66043664b4021fc52eba5` |
| 精确源码切片 | `6df39b85c5ae94f31a1fa5ae2fe71d2c18eb688fea8c1a7fe102d75bf0d102f5` |
| 源历史 / archive 复制历史 | `0ecd9f0f2ccacca9d5a4e3281dfabc1cf6d09c4c81da867977d302b0598e40bf` |
| 确定性 replay 状态 | `a61a4b547574cd33c084695b4459d0aa36237a252198f06f403a97eb726cb85e` |
| 最终内存 messages | `a71218ce9c3bf1ea776dc170938c5aa918d8d23793bf34a7a3d27b9e0c5abd2e` |
| archive payload / record | `dd417968b48653557514100ca51a99cb276070dbd610502745ef577c48ff39e9` / `0540ccaef10e329c8d212f8f5a8076d4cf2d04063af89fee71247b7ba83c0df1` |
| 最终 JSONL 往返 | `3a8f9f210d9e5daccc56789cd4a1ef8c144d89a829f6f55f68eff8d32e58779f` |
| 模型 context / API payload | `8d5972e4b0b9548099d2efbb95ecb1f14ff8d9dbe1bf62c603d3ec93d3108958` / `0e5dccd19e37ab2c5b814916035a27965b77121333605c65701707f0dc53b330` |
| UI HTML / 可见文本 | `7c8f25181b67f43a364155790f7d889359e3600b75a77087328bbd4ad6195cd8` / `92145b03f68be59e0a83c45b0f7288d78c1a36faada1edc8e8833b4ed047b397` |

2026-08-14 发布门禁复核把 HTML `hidden` 子树从可见文本解析中排除。连续两次生成得到相同证据：12 个可见历史哨兵、顺序、唯一性和可见文本哈希保持不变，仅 CODE-004 引入的原始 UI HTML 结构哈希及其派生 `replayHash` 变化；源历史、archive、保存、模型上下文、Session 所有权和零副作用字段均未变化。

默认单 Run `17/124/25/25/4`、H3-2C1、H3-2B1 与 H3-2B2 的计数和全部 fixture/replay/状态哈希均保持不变。

## 定向失败诊断

| 故意变异 | 首差异路径 |
|---|---|
| evidence profile 版本漂移 | `$.evidenceProfile.version` |
| 源码切片哈希漂移 | `$.sourceSlice.sha256` |
| 源历史删除 / 乱序 | `$.sourceMessages[12]` / `$.sourceMessages[0]` |
| 压缩计划范围错写 | `$.expected.plan.removedMessageIds[0]` |
| 原历史前缀变化 | `$.expected.completed.sourcePrefixHash` |
| summary 重复 / marker 状态错写 | `$.expected.completed.summaryCount` / `$.expected.completed.markerStatus` |
| archive payload 变化 | `$.expected.archive.payloadHash` |
| 最终 JSONL 变化 | `$.expected.save.roundTripHash` |
| 后续模型上下文泄漏旧消息 | `$.expected.model.contextSourceMessageIds[0]` |
| UI 哨兵缺失 / 重复 / 乱序 | `$.expected.ui.visibleSentinels[3]` / `[4]` / `[0]` |
| 一次性确认重复保存 | `$.expected.execution.repeatClickAddedSaveCalls` |

## 验证与完成边界

- H3-2D2 定向：`7 passed, 19 subtests passed`；
- compaction、模型请求、持久化、UI、Session/archive 相关组合：`405 passed, 48 subtests passed`；
- 全部 Harness：`104 passed, 253 subtests passed`；
- 完整 Python：`1102 passed, 718 subtests passed`；
- 默认单 Run、H3-2C1、H3-2B1 与 H3-2B2 CLI replay、Python/Node 语法、空白和差异检查均通过。

本阶段只证明脱敏合成成功路径在当前精确源码切片、真实 archive handler、生产持久化、模型上下文和 UI HTML 字符串投影上的契约。HTML 字符串断言不是 DOM 或真实浏览器显示验收。本阶段不证明 compact API 失败、archive 失败、最终保存失败、真实摘要质量、真实 HTTP、浏览器、DOM/滚动、页面刷新、Runtime 或发布门禁。

## 回退

回退时可独立删除 H3-2D2 schema、fixture、定向测试和本专题文档，并移除总览、TODO 与日志中的阶段事实。生产 `app.js`、archive handler、会话 JSONL、模型/UI 投影和其他 Harness 基线均无需迁移或回写。
