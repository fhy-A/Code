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

## 稳定语义哈希

随机 AgentRun、Runtime、toolCall、job ID、时间、端口、完整错误文案、原始 JSONL 字节与完整 HTML 均不进入基线。bundle 与 direct classic 共享以下八项 SHA-256：

| 投影 | SHA-256 |
|---|---|
| `mainToolTrace` | `6599ebee8ff79520ee51e2fa2fe2011ce6237091791282c02f6b5525092223c4` |
| `backgroundAgent` | `1319a246751c8daa8c6546cfe1b8f2aab159bb00a11b01f908b5d20c7f414545` |
| `backgroundRuntime` | `6b71bc4b26a681050327da18905949caaa9ae806dd78747dc9708bba1a5f76d1` |
| `sessionRoleContent` | `9846dc82c8e7a82b181c41ee23ecc25b0ac6bf25df1fe0564e5fea8b605e9ab7` |
| `backgroundMeta` | `e26b1c4a7e1a70f87ab60335fcd655331a2601f2a7dd6882e63821d2eb8d5baa` |
| `domOwnership` | `0c317c7fffaaa70a224e2193072f71dfaac66f64f5f5b755d918abcca106d584` |
| `requestCounts` | `e90926ff643c4cff6ab16720a27dedbd1b5f4561b874e7bbe4ef7d3e63eaba1e` |
| `refreshLifecycle` | `0cb60f329ee95fbe0953c4712394e8aa085b7c83a13680c2ec444b8d1ce37681` |

## 文件哈希与验证

收口前后冻结的测试文件 SHA-256：

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

## 证明边界与回退

H4-7C 只证明确定性 HTTP 502 下 detached `/parallel` 失败不会污染或终止同进程活动主任务，并证明两种前端入口在页面完整 reload 后恢复同一终态且零重放。它不证明显式取消、超时、排队失败或取消、Child、active background 刷新恢复、跨进程恢复、真实外部网络、工具副作用 exactly-once，也不定义新的并发产品语义。

独立回退只需撤销两个 H4 测试文件的 H4-7C 增量及本阶段收口文档；不涉及生产代码、数据迁移、协议兼容或发布回退。
