# H4-7C detached `/parallel` 模型失败隔离与终态刷新唯一性

## 完成范围

H4-7C 只覆盖一个确定性真实浏览器生命周期：主任务正在执行单次只读 `read_file("fixture.txt")`，工具结果已形成、第二轮终答尚未发送时，用户提交 detached `/parallel`；隔离假上游针对固定 marker 返回一次 HTTP 502。默认 bundle 与 `/dist/frontend/index.classic.html` direct classic 复用同一生产 AgentRun、Runtime、Session 与 DOM 链，以及同一参数化测试 helper，没有新增产品交互、并发状态机、协议或持久化字段。

隔离 host 仅识别固定 `H4_PARALLEL_MODEL_FAILURE_USER`，并以固定错误 marker 返回 502。主任务继续复用 `before-tool-final-delta` 与 `before-tool-terminal` 两个既有闸门；background 不调用工具，也不引入 retry、sleep、额外控制协议或凭据路径。

## AgentRun 与 Runtime 事实

- 主任务保持唯一九事件工具链：`created → model_started → model_completed → tool_started → tool_completed → model_pending → model_started → model_completed → completed`。background 失败发生时主任务仍为 active，原 toolCall、result、稳定 process key 与展开状态不变；释放两个闸门后主任务正常 completed。
- detached background 使用独立 AgentRun，事件精确为 `created → model_started → failed`。它不生成工具 execution，不创建 checkpoint、替代 Run 或重复错误消息。
- background Runtime 精确为 `status=failed`、`errorCode=upstream_error`、`upstreamStatus=502`、`transient=true`；SSE 事件数为 0，content/reasoning 为空且 toolCall 数为 0。
- 首次请求计数固定为 AgentRun POST 2（主任务与 background）、Runtime POST 0、chat 3（主任务两轮与 background 一轮）、tool execution 1（只属于主任务）。生产 Runtime GET 只用于观察既有 Runtime，不得记作 Runtime POST。

## Session、DOM 所有权与刷新

Session 中 background 用户消息与唯一 error assistant 通过 `jobId`、`agentRunId` 和 reply reference 闭合。detached 终态沿用现有 `execution-trace-persistent` 规则保持可见，但不取得主任务工具轨迹或顶部完成状态的所有权：background reply reference 与自身 `.run-time` 各 1，background 顶部完成状态为 0；主任务顶部完成耗时为 1、assistant 页脚耗时为 0。

background 用户与 error assistant 不进入主任务工具组，主任务仍只有一个工具组、一个工具项和一个结果，最终回答位置与工具顺序不变。完整 reload 后主任务、失败 background 消息、身份、顺序、耗时和工具轨迹各唯一；AgentRun POST、Runtime POST、chat 与 tool execution 四项刷新增量全部为 0。

## H4-SYNC-1 原槽排序与后续对话隔离

H4-SYNC-1 保留 failure-first 交错：detached `/parallel` 的固定 502 先形成独立 failed 终态，主任务之后才释放 final 与 terminal 闸门。提交 `/parallel` 前，测试先以目标 Runtime 的页面 `wait=25` GET 证明真实前端 consumer 已 attach，并以动态原子 DOM 投影确认活动 Run anchor、主任务身份、稳定工具阶段和 detached 消息尚未创建；空 pending/thinking assistant 继续按产品既有规则隐藏，不作为可见占位断言。

生产排序修订只作用于同一 `parentTaskStartedAt`、`jobId` 闭合的完整 detached user/assistant pair：主任务 final 保留原主任务槽位，完整 detached pair 不再参与 legacy completion-order 重排。稳定终态与刷新后的逻辑顺序精确为：

```text
main user → main stage/tool trace → main final → detached user → detached failed assistant
```

非 detached 的 legacy completion-order 行为继续保留；跨 parent、queue 调度与 detached 执行生命周期没有改变。该修订只影响当前投影顺序，不回填或重写历史会话中的旧消息顺序。

主任务与 detached Run 均终态后，同一 Session 通过真实 composer 发送一次固定普通、无工具 follow-up，并得到唯一固定 final：

- follow-up 增量精确为 AgentRun POST `+1`、Runtime POST `+0`、上游 chat `+1`、工具执行 `+0`；场景总计为 AgentRun POST 3、Runtime POST 0、上游 chat 4、工具执行 1。
- 新 AgentRun 事件为 `created → model_started → model_completed → completed`，唯一 Runtime completed；主任务与 follow-up 都没有残留 pending、running、failed 或操作锁。detached failed 仍只属于自己的独立终态。
- 隔离 host 对实际模型 payload 只输出脱敏上下文投影：follow-up marker 为 1，detached user marker、detached error marker 与 detached 状态字段均为 0；主线 user、tool call、tool receipt、main final 与 follow-up user 顺序闭合，工具 receipt 仍是唯一成功的 `read_file("fixture.txt")`。
- 最终 DOM 顺序继续追加 `follow-up user → follow-up final`；主任务和 follow-up 页脚不重复显示耗时，detached assistant 独立 `.run-time` 仍唯一。
- follow-up 完成后的完整 reload 保持三条 AgentRun、四个 Runtime、九条 Session 消息、DOM 顺序与计时唯一；AgentRun POST、Runtime POST、上游 chat、工具执行四项增量全部为 0。

H4-SYNC-1 排除了随机 ID、时间、端口、完整正文、原始请求体、JSONL 与完整 HTML，bundle 与 direct classic 的八项 SHA-256 完全一致：

| 投影 | SHA-256 |
|---|---|
| `preParallelFence` | `10b427d80882ae5a10fc84ca44f894afea07bccf3b9e1944bc0b3ae5552fcf47` |
| `terminalOrdering` | `3639c2f18f3484e8a76ca8ef53b45a0b29ec1281a65943b75234cd55593744ee` |
| `followupRequestContext` | `25f3d36ea8966773c131ff552dea9211c24deba88efd68e22ba796226508ac10` |
| `followupAgentRuntime` | `b6d711c9ff9fcfb50b179aa03938c93eef6b741c971335310bee4a1ec8b875b3` |
| `followupSession` | `e0dfc6865fab9ada4fc038598ad83e22b126cdbd8c2cb66d91952497cb5ce25d` |
| `followupDom` | `b7b1505cf4fed62478c535a9ad86fab9291a26ac8318ac04d47ef0dc742fc8a6` |
| `requestCounts` | `51357c34453ca7e453830920b00500004f0183b75bcf58b9e8e56121e52860fb` |
| `refreshLifecycle` | `4f728a8ceb1d29f8c888e828cd1b27d21fbdb1508e030fa29a5aa3ffd4ba281f` |

## 原 H4-7C 历史语义哈希与当前保持项

随机 AgentRun、Runtime、toolCall、job ID、时间、端口、完整错误文案、原始 JSONL 字节与完整 HTML 均不进入基线。下表保留原 H4-7C 收口时的八项历史 SHA-256；当前代码仍以 `H4_7C_BASE_SEMANTIC_HASHES` 冻结其中标记为“保持”的五项。原 `sessionRoleContent`、`domOwnership` 与 `refreshLifecycle` 反映旧排序，已由上面的 H4-SYNC-1 独立投影取代，不把新值覆盖写入旧哈希。

| 投影 | SHA-256 | 当前状态 |
|---|---|---|
| `mainToolTrace` | `6599ebee8ff79520ee51e2fa2fe2011ce6237091791282c02f6b5525092223c4` | 保持 |
| `backgroundAgent` | `1319a246751c8daa8c6546cfe1b8f2aab159bb00a11b01f908b5d20c7f414545` | 保持 |
| `backgroundRuntime` | `6b71bc4b26a681050327da18905949caaa9ae806dd78747dc9708bba1a5f76d1` | 保持 |
| `sessionRoleContent` | `9846dc82c8e7a82b181c41ee23ecc25b0ac6bf25df1fe0564e5fea8b605e9ab7` | 历史；由 H4-SYNC-1 取代 |
| `backgroundMeta` | `e26b1c4a7e1a70f87ab60335fcd655331a2601f2a7dd6882e63821d2eb8d5baa` | 保持 |
| `domOwnership` | `0c317c7fffaaa70a224e2193072f71dfaac66f64f5f5b755d918abcca106d584` | 历史；由 H4-SYNC-1 取代 |
| `requestCounts` | `e90926ff643c4cff6ab16720a27dedbd1b5f4561b874e7bbe4ef7d3e63eaba1e` | 保持 |
| `refreshLifecycle` | `0cb60f329ee95fbe0953c4712394e8aa085b7c83a13680c2ec444b8d1ce37681` | 历史；由 H4-SYNC-1 取代 |

## 文件哈希与验证

原 H4-7C 收口前后冻结的测试文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `tests/e2e/h4/isolated_host.py` | `482482c3feb26bcc09ac9f1a5bdd81f23111cbdbe8bab5e78db6279ab6baed86` |
| `tests/e2e/h4/smoke.spec.cjs` | `ea7c04409a25687e3bcbe58d660ae9576c85bda1b2269458d21045f243ea5b73` |

同一测试文件形态已取得：

- bundle/direct classic H4-7C 定向通过，语义哈希一致；H4 infrastructure 通过。
- 连续两轮标准 H4 均为 `41 passed`、单 worker、`retries=0`、exit 0，完整耗时约 161 秒与 159.8 秒。
- H4-6A 两条工具生命周期与 H4-7B 两条计时场景通过且旧哈希保持。
- background/concurrency/frontend 定向 `265 passed`；完整 pytest `1122 passed, 751 subtests passed`。
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源审计通过。

此前一次标准 H4 使用 240 秒外层命令等待预算时，外层管道在约 242.8 秒关闭并产生 EPIPE，未取得 Playwright 完成摘要；该轮既不计通过，也不判为产品失败。后续只把外层等待预算增加到 360 秒以取得正式摘要，没有修改 Playwright 内部 timeout、单 worker、`retries=0`、测试断言或实现。

每次 Playwright 成功后只在确认 `output/h4-playwright/.last-run.json` 精确为 `status=passed` 且 `failedTests=[]` 时删除该单一成功标记；没有递归删除 output 或失败诊断。最终 H4 进程、监听端口、临时根、output 文件与暂存区均归零。

H4-SYNC-1 与累计稳定性实现包含在提交 `8178be99e8ede82d739902d6c8f37afc76846abb` 中。该最终树下，H4-SYNC-1 bundle/direct classic 与相邻 H4-7B 通过，前端排序定向 `3 passed`，`npm run check:frontend` 与 H4 infrastructure 通过；连续两轮标准 H4 均为 `51 passed`、单 worker、`retries=0`；完整 pytest 为 `1131 passed, 751 subtests passed`；Node/Python 语法和 `git diff --check` 通过。当前专题更新只执行 Markdown、链接、哈希引用、diff 与三文件白名单检查，不重跑长矩阵。

## 证明边界与回退

H4-7C/H4-SYNC-1 只证明确定性 HTTP 502 下单个 detached `/parallel` 先失败时不会污染或终止同进程活动主任务，主 final 保持原槽，随后一次普通无工具 follow-up 的实际模型上下文排除 detached 内容，并在完整 reload 后零重放。

本阶段不证明异常或孤儿历史 detached 记录、多并行失败、502 之外的其他错误码、显式取消、超时、queue/steer、排队失败或取消、Child、工具型 follow-up、active background 或跨进程恢复、真实外部网络、后台工具副作用 exactly-once，也不以自动化替代主观视觉验收。完整同源 detached pair 之外的迁移期混合记录与历史旧顺序不回填。

独立回退需撤销 `app.js` 的同源 detached 排序修订、对应前端/H4 隔离证据及本专题更新；不涉及数据迁移、Session/AgentRun/Runtime 协议或历史消息回写。
