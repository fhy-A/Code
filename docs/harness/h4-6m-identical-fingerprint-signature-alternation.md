# H4-6M 同指纹错误签名交替隔离

## 完成范围

H4-6M 只扩展隔离宿主和真实 Chromium Harness，没有修改生产限流、工具协议、持久化或安全边界。默认 bundle 与 direct classic 共用同一参数化生命周期，三次模型工具声明使用三个唯一 `toolCallId`，但工具名和原始字段顺序固定的 arguments 完全相同：

```json
{"path":"h4-signature-alternation-fixture.txt","startLine":2,"endLine":1}
```

专用相对路径始终解析在每例独立临时 project 根内。隔离宿主从既有 `fixture.txt` 读取原始字节，并在受控委托边界按调用次序设置 `present → missing → present`：第一次和第三次在委托前写入并核对相同字节，第二次在委托前精确移除该专用文件。三次都继续调用原始 `execute_registered_tool`，没有伪造、捕获后改写或替换生产执行器错误；teardown 只精确清理该专用路径，owned root 继续提供兜底清理。

## 同指纹、交替错误签名与计数

- 三次声明的工具名和规范 arguments 指纹相同；本阶段只证明上述固定字段顺序，不宣称任意 JSON key 顺序会得到相同指纹。
- 第一次和第三次命中生产 `read_file` 行范围失败，第二次命中生产文件不存在失败，因此 `failureSignature` 关系为 `A → B → A`。
- 三条耐久 execution 的 `failureCount` 精确为 `[1,1,1]`。不同错误签名打断连续同签名计数；第三次 A 不继承第一次 A 的非连续计数。
- 三次均无 `retryLimitReached`、`retryBlocked`，没有 `tool_retry_blocked` 事件，也没有进入 `forceFinalRound`。
- 第四模型轮仍携带正常 `tools/tool_choice`，不含恢复指令，并产生唯一普通终答；父 AgentRun 最终为 `completed`。

完整生产链闭合为三次真实委托和三次真实执行、四次 chat、零 unsafe 请求。AgentRun 共 19 个事件，`nextCursor=19`，耐久 `nextSeq=20`，四个 Runtime 的 cursor 向量为 `[4,3,3,3]`，终态 `pendingToolCalls=[]`。

## Session、DOM 与刷新唯一性

- Session 共 11 条消息，角色和顺序为 user、第一轮 assistant、三对有序 tool-call/tool-result 与三轮 assistant 声明、最后 assistant 终答；三对结果分别通过 `toolCallId`、`agentRunId`、相同 arguments 和原始 result 精确配对。
- DOM 始终只有一个工具组和三个有序 failed 工具项，用户可见语义为“行范围失败、文件不存在、行范围失败”。活动态正文重绘保持稳定 process key 和展开状态；终态及完整 reload 后父 trace、工具组和三个单项均按既有规则默认折叠。
- 首次生命周期计数为 AgentRun POST 1、Runtime POST 0、chat 4、production tool execution 3；完整 reload 后 AgentRun POST、Runtime POST、chat、tool execution 四项增量全部为 0。
- bundle 与 direct classic 使用同一生产链和断言。runtime 入口标记单独核对，不进入跨入口领域哈希。

## 稳定语义哈希

随机 ID、绝对时间、端口、完整本地化错误正文、原始 JSONL 字节和完整 HTML 均不进入哈希。bundle 与 direct classic 的九项 SHA-256 完全一致：

| 投影 | SHA-256 |
| --- | --- |
| `eventProjection` | `94bf1904972bf0cc12156a1e1b1cdf24e04fad550eb92f286431c4ee63737110` |
| `signatureAlternationExecutionProjection` | `ad859f657b2dfce7f53a2d7689e776c6a09d7351e8685233a44ee31d9b2ff7de` |
| `modelToolReceiptProjection` | `d5ba927a08330c188893534558772db52a96f26860aca7a075ae1fdc8adf4a96` |
| `normalFinalProjection` | `5c37ad3dafd0bee531d31a9a2518151c119ccac5334d5bf50c2fbcd1c71a82d7` |
| `runtimeProjection` | `53c3e16055adbbc77fc095010ce4b714fad3d7ef3b5b58078b122063c84624ff` |
| `sessionRoleContent` | `1d3cbc5c75a4986aba24ae023342def9fe1eb4c56e6dd19e50f17b11832e39b8` |
| `sessionToolMeta` | `3eb5bf4987dda86b75128849634c491c48f85202ef0b71dfb1ecc330f5ca5e59` |
| `terminalDom` | `5f19d080ae18a0686a4f7e8bd110db2ee06098138345fafa46100f777e9cab09` |
| `refreshLifecycle` | `9eed2e8243028245f646fc0d656840e948b4d1e3cf3bc6b330963b918df9ecb9` |

冻结实现哈希：

- `tests/e2e/h4/isolated_host.py`：`AEA29C4142CA13DC2C18D6D23BF4CC60D4D2709FBCD6DD9E0910A29C73652937`
- `tests/e2e/h4/smoke.spec.cjs`：`97DF8FDD26F5FECCEBCE9827CDC3700476008C75198756C8E5B62AEA2A271A0E`

## 验证结果与无效轮次

- H4-6K/H4-6L bundle 与 direct classic 先行复验通过，原九项哈希保持不变；H4-6M bundle 首次有效取证、direct classic 对等及两例合并复验均通过。
- H4 infra 通过；连续两轮标准 H4 均为 `45 passed`、单 worker、`retries=0`、exit 0。
- 相关生产失败限流与 `read_file` 路由定向共 `6 passed`；前端/P0 为 `230 passed`；完整 pytest 为 `1127 passed, 751 subtests passed`；`npm run check:frontend`、Node/Python 语法、`git diff --check` 和资源清理均通过。
- 首次取证发现测试 wrapper 把脱敏 timeline 写在生产委托正常返回之后，而真实执行器失败通过异常传播，导致 timeline 没有被记录。修订只把只读取证和文件状态复核移入 `finally`，原异常继续原样传播，没有改变执行顺序、错误签名或限流语义；该首差异轮不计通过。
- 一次 pytest 定向命令使用了不存在的类名，未进入测试收集；随后以真实测试定位取得上述有效结果。该无用例命令不计产品通过或失败。
- 文档收口沿用同一冻结实现哈希下已经完成的完整矩阵，仅重做文档、语法、链接、diff、暂存白名单和资源门禁，不将未重跑项目描述为收口后重跑。

## 完成边界与回退

本阶段只证明固定字段顺序、同一 `read_file` 与完全相同规范 arguments 指纹下，隔离 project 内 `present → missing → present` 形成的 `A → B → A` 错误签名交替会得到 `[1,1,1]`，并在 bundle/direct classic 的同进程终态 reload 中保持唯一且零重执行。

本阶段不证明阈值后的错误交替、不同工具、不同 arguments、任意 JSON key 顺序、执行前 schema/parse 失败、权限/编码/大文件错误、跨进程 active 恢复、取消或外部副作用 exactly-once。独立回退只涉及两份 H4 测试差异和本专题及事实源文档；没有生产、协议、数据迁移或持久化回退动作。
