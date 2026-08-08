# H4-6L 不同 arguments 失败身份隔离与同指纹连续性

## 完成范围

H4-6L 只扩展测试侧隔离宿主和真实 Chromium 场景，同时覆盖默认 bundle 与 direct classic。场景复用 H4-6G/H4-6K 的 `read_file` 行范围生产执行器失败链，以固定字段顺序声明三个不同 toolCallId：

1. A1：`{"path":"fixture.txt","startLine":2,"endLine":1}`；
2. B1：`{"path":"fixture.txt","startLine":3,"endLine":1}`；
3. A2：再次声明 A。

三次参数均通过生产 schema 和既有只读 action/path 安全边界，真实进入 `execute_registered_tool → execute_read_file_tool`，并因 `endLine < startLine` 在生产执行器内部失败。测试没有修改生产限流算法、协议、持久化、安全边界或工具包装器。

## 身份隔离与连续性事实

- A1 与 A2 的规范 arguments 指纹相同，B1 的指纹不同；三次错误签名相同。
- 三次耐久失败的 `failureCount` 精确为 `[1,1,2]`：B 不继承 A 的计数，也不打断 A 的同指纹失败链。
- 三项 `retryLimitReached=false`、`retryBlocked=false`，`tool_retry_blocked=0`，`forceFinalRound=false`。
- 第四轮模型请求仍携带正常 `tools/tool_choice`，不含恢复指令，并由固定普通最终回答令父 AgentRun 进入 `completed`。
- 初始链只有一个 AgentRun；模型请求 4、Runtime 4、生产委托与真实工具执行均为 3、unsafe 为 0。Runtime cursor 向量为 `[4,3,3,3]`。
- AgentRun 精确为 19 个事件，`nextCursor=19`、耐久 `nextSeq=20`，终态 pending 为空且没有 Run errorCode。

本阶段只冻结上述固定字段顺序，不把它外推为任意 JSON key 排序都具有同一指纹。

## Session、DOM 与刷新唯一性

Session 顺序精确为：

`user → assistant → tool-call(A1) → tool-result(A1) → assistant → tool-call(B1) → tool-result(B1) → assistant → tool-call(A2) → tool-result(A2) → assistant(final)`。

三对 tool-call/tool-result 通过各自 toolCallId、agentRunId、arguments 与失败 result 严格闭合。页面始终只有一个工具组和 A→B→A 三个有序 failed 项；终答正文投影触发真实重绘时，稳定 process key 与用户展开状态保持，终态以及完整刷新后恢复为默认折叠。

首次请求计数为 AgentRun POST 1、Runtime POST 0、chat 4、tool execution 3。完整 reload 通过生产 Session 恢复后，AgentRun、Runtime、Session、失败结果和 DOM 投影保持唯一，AgentRun POST、Runtime POST、chat、tool execution 四项增量全部为 0。direct classic 使用直接入口，不把它描述为自动 bundle 故障降级。

## 稳定语义哈希

bundle 与 direct classic 的九项去随机化 SHA-256 完全一致：

| 投影 | SHA-256 |
| --- | --- |
| `eventProjection` | `e14d928023c7e8b4b6361e21a298dbb3bb3e8f55e869e55e199463c9df19167f` |
| `argumentIsolationExecutionProjection` | `aa850a56ead1282c75ecbe2307a48d321623495c9d9710ac79e148c79db735fa` |
| `modelToolReceiptProjection` | `5ef5d2a1bb4e6724ec42b245ab0bb31dc58739de0946038cff95b2951384f3d4` |
| `normalFinalProjection` | `be20dba411d3bd89097afd19589d2ebb98182a40d13218ee0fbd920047e23c7a` |
| `runtimeProjection` | `53c3e16055adbbc77fc095010ce4b714fad3d7ef3b5b58078b122063c84624ff` |
| `sessionRoleContent` | `3dfadda28fd29faf8cf684f9ef121feccc51b799fa7c0f21d344e2c21191f562` |
| `sessionToolMeta` | `ac5326e2d5c5599424237d8f760a8302f76a6e2bc687bb630600260642187f7b` |
| `terminalDom` | `1794c5f4551d5e05cf4dfd6b3bfd272427891dd76c8363285746fd18cbbf8707` |
| `refreshLifecycle` | `5fc851eaa40059021056e2806c4dbb151f3eb9eb0ae5959487e927beac858f4c` |

随机 ID、绝对时间、端口、完整错误文案、原始 JSONL 和完整 HTML 不进入跨运行哈希。收口时冻结的测试文件哈希为：

- `tests/e2e/h4/isolated_host.py`：`290895e3fdd37a04b89f2ce1dc8eaeb2cfe262a9c9f4c0e8a3fdcea05ce500bf`；
- `tests/e2e/h4/smoke.spec.cjs`：`807419cc933d302ea39845e5bc62c63509dd1547370b59163129ed6031c98a2a`。

## 完整门禁稳定性修正

完整矩阵另外收敛了两处纯测试侧确定性问题，均未改变产品行为：

- Q1 Control+Enter：H4-7B 排队动作仍只执行一次真实 `locator.press("Control+Enter")`。测试新增 prompt connected/enabled/focused/value 前置检查，并以脱敏时间线闭合 `keydown=1 → submit=1 → queue-save=1 → queued DOM=1`；Session PUT 只记录 method/path、固定 marker 与 queuedDispatch/checkpoint/status 计数，不保存完整正文、请求体、身份、路径或凭据。这是观察性因果门禁，不是生产竞态修复。首版观察器把单独 Control keydown 也计入目标事件，随后只按目标 Enter keydown 收敛；该失败轮不计通过。
- TIFF 重绘：原测试点击当前活动 Session 受 `loadSession` 的 300 ms 防抖影响，不能确定性证明重绘。门禁改为使用现有设置 UI 切换语言，沿真实 `onLanguageChanged → renderMessages` 触发生产重绘；旧节点必须断开，新节点重新取得后预览仍可解码，恢复原语言后同样保持。没有直接调用内部 render、增加 sleep/retry/timeout，TIFF 请求计数仍为 POST 2、GET 2、总计 4，原图 SHA、`image/tiff` 持久化与刷新四项零增量均未改变。这同样不是生产竞态修复。

## 验证结果

同一最终测试文件形态已完成：

- H4-6L bundle/direct classic 取证、哈希固化与复验通过，A→B→A 计数保持 `[1,1,2]`；
- H4-6K bundle/direct classic 旧九项哈希保持；H4-6G 及共享失败生命周期相关场景通过；
- TIFF bundle 连续三次、classic 单次及合并场景通过；Q1 bundle/classic 合并场景通过；
- H4 infrastructure 通过；
- 连续两轮标准 H4 均为 `43 passed`、单 worker、`retries=0`、exit 0，耗时约 151.2 秒和 150.8 秒；
- Agent Runtime 重复失败定向 `3 passed`；
- 前端/P0/background persistence `230 passed`；
- 完整 pytest `1122 passed, 751 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check`、哈希与资源清理通过。

文档收口沿用上述同一实现哈希下的有效完整矩阵，没有把未重跑项目写成收口后重跑。

## 完成边界与回退

完成声明严格限于固定字段顺序下，同一 action/path/错误签名、不同规范 arguments 的失败计数隔离与 A 同指纹链延续，以及 bundle/direct classic 同进程终态刷新零重执行。它不覆盖任意 JSON key 排序等价、不同工具、错误签名交替、阈值后交替、强制终答失败、跨进程 active、取消或外部副作用 exactly-once。

独立回退只需撤销两份 H4 测试文件中的 H4-6L 场景及 Q1/TIFF 稳定门禁和本专题收口文档；没有生产、数据迁移、协议或发布回退动作。
