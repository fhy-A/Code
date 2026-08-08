# H4-6N 同指纹成功打断失败链

## 完成范围

H4-6N 只扩展隔离宿主和真实 Chromium Harness，没有修改生产限流、工具协议、持久化、UI 或安全边界。默认 bundle 与 direct classic 共用同一参数化生命周期，三个唯一 `toolCallId` 均声明完全相同的固定 arguments：

```json
{"path":"h4-success-reset-fixture.txt"}
```

专用相对路径始终解析在每例独立临时 project 根内。隔离宿主在受控委托边界按调用次序设置 `missing → present → missing`：第一次确认专用文件不存在，第二次写入与既有 `fixture.txt` 完全相同的字节并核对 SHA，第三次再精确删除。三次均继续调用原始 `execute_registered_tool`，没有 mock、伪造、捕获后改写或替换生产执行器结果；teardown 只精确清理该专用路径，owned root 继续提供兜底清理。

## 同指纹成功打断失败链

- 三次声明的工具名、字段顺序和规范 arguments 完全相同，因此 fingerprint 一致；本阶段不宣称任意 JSON key 顺序会得到相同指纹。
- 三条耐久 execution 的 outcome 精确为 `failed → succeeded → failed`，`failureSignature` 关系为 `A → absent → A`。
- 两次缺文件失败的 `failureCount` 均为 `1`。中间成功项在耐久 execution 顶层及其 `result` 内都不存在 `failureCount`，也不存在失败签名；成功执行会打断此前同指纹失败链，第三次同失败不继承第一次计数。
- 三轮均无 `retryLimitReached`、`retryBlocked`，没有 `tool_retry_blocked` 事件，也没有进入 `forceFinalRound`。
- 第四模型轮仍携带正常 `tools/tool_choice`，不含恢复指令，并产生唯一普通终答；父 AgentRun 最终为 `completed`。

完整生产链闭合为三次真实委托和三次真实执行、四次 chat、零 unsafe 请求。AgentRun 共 19 个事件，`nextCursor=19`，耐久 `nextSeq=20`，四个 Runtime 的 cursor 向量为 `[4,3,3,3]`，终态 `pendingToolCalls=[]`。

## Session、DOM 与刷新唯一性

- Session 共 11 条消息，角色和顺序为 user、三轮 assistant 工具声明及三对有序 tool-call/tool-result、最后 assistant 终答；每对结果通过 `toolCallId`、`agentRunId`、相同 arguments 和原始 result 精确配对。
- DOM 始终只有一个工具组和三个有序工具项，状态为 `failed/succeeded/failed`。成功项显示固定 path、`26 B` 和唯一一份受控 fixture 正文；活动态正文重绘保持稳定 process key 和展开状态，终态及完整 reload 后按既有规则默认折叠。
- 首次生命周期计数为 AgentRun POST 1、Runtime POST 0、chat 4、production tool execution 3；完整 reload 后 AgentRun POST、Runtime POST、chat、tool execution 四项增量全部为 0。
- bundle 与 direct classic 使用同一生产链和断言。runtime 入口标记单独核对，不进入跨入口领域哈希。

## 稳定语义哈希

随机 ID、绝对时间、端口、完整本地化错误正文、原始 JSONL 字节和完整 HTML 均不进入哈希。bundle 与 direct classic 的九项 SHA-256 完全一致：

| 投影 | SHA-256 |
| --- | --- |
| `eventProjection` | `b396c14c67535bb53f17151d50ce778bdbba80acb024a6e1a5bbafdb9abf3c54` |
| `successResetExecutionProjection` | `2f8deb0062775cb9a354a981b5716672c341fb6b9f562b6a73bcf327ca190322` |
| `modelToolReceiptProjection` | `1f86ca8012531c5aa0090128549596797d3d60a1a9abd70a120e1dfa6cc6e7af` |
| `normalFinalProjection` | `40824ea79a03d0f8e82df043ee3030f20b901b9ebfa94b44995752fed1906b6d` |
| `runtimeProjection` | `53c3e16055adbbc77fc095010ce4b714fad3d7ef3b5b58078b122063c84624ff` |
| `sessionRoleContent` | `42f299dc94ade765e72e403dde767f6586285eda79fa7f73955f1662f23ed381` |
| `sessionToolMeta` | `f4d120765d56b4fd397c01caefdb2c9ec0970fcce210a52481f61136d062331a` |
| `terminalDom` | `0894c3038aae4180631183d1f6fc91822be44f06865f318041fb1f996f894229` |
| `refreshLifecycle` | `d9ac00cdbf0bc758c39b7f47d1941ea36c2b2bc07f7f9e264301833308d35725` |

冻结实现哈希：

- `tests/e2e/h4/isolated_host.py`：`24A76E0E9CBA1852FC0D46858D981AF3D0F4E139C158687C6F817F94C9D8B42F`
- `tests/e2e/h4/smoke.spec.cjs`：`5181EAAF79DE796799871EEE0308A7E00C38B49BAE482FAF2735FFF9880D5403`

## 验证结果与无效轮次

- 在最终断言增强后的冻结文件哈希下，H4-6K/H4-6L/H4-6M bundle 与 direct classic 共 `6 passed`，全部旧哈希保持；H4-6N bundle/direct classic 及九项新哈希对等通过。
- H4 infra 通过；连续两轮标准 H4 均为 `47 passed`、单 worker、`retries=0`、exit 0。断言增强前已完成的两轮因文件哈希随后变化，明确作废，不作为本阶段最终证据。
- 相关 limiter 与 `read_file` 根契约定向共 `6 passed`；前端/P0 为 `230 passed`；完整 pytest 为 `1127 passed, 751 subtests passed`；`npm run check:frontend`、Node/Python 语法、`git diff --check` 和资源清理均通过。
- 首次 H4-6N bundle 取证把 DOM 布尔值 `false` 投影为 `undefined`，测试据真实结构改为稳定 Boolean 投影；该轮不计通过，也没有改变产品行为或九项语义范围。
- 一次带首尾锚点的 Playwright 标题 grep 没有匹配完整标题、未运行用例；该无用例命令不计产品通过或失败。
- 文档收口沿用上述同一最终实现哈希下已经完成的完整矩阵，仅重做链接/占位符、语法、diff、暂存白名单和资源门禁，不将未重跑项目描述为收口后重跑。

## 完成边界与回退

本阶段只证明固定字段顺序、同一 `read_file` 与完全相同 arguments 指纹下，隔离 project 内 `missing → success → missing` 会得到 `failed → succeeded → failed`、`A → absent → A` 与 `1 → absent → 1`，并在 bundle/direct classic 的同进程终态 reload 中保持唯一且零重执行。

本阶段不证明不同工具或不同 arguments、阈值后行为、错误交替、任意 JSON key 顺序、执行前 schema/parse 失败、权限/编码/大文件错误、跨进程 active 恢复、取消或外部副作用 exactly-once。独立回退只涉及两份 H4 测试差异和本专题及事实源文档；没有生产、协议、数据迁移或持久化回退动作。
