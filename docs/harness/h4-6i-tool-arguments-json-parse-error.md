# H4-6I 工具参数 JSON 解析失败生命周期

## 完成范围

H4-6I 只在测试侧为默认 bundle 与 direct classic 各增加一条真实 Chromium 场景。假上游把固定原始字符串 `{"path":"fixture.txt"` 直接写入模型工具调用，没有经过 `json.dumps` 或对象重建修正；生产链真实进入 `server.py` 的 `json.loads()` / `parseError` 分支，并在 `execute_registered_tool` 之前终止。这不是缺少必填 `path` 的 schema `required` 失败，也没有改变工具协议、白名单、安全边界或持久化格式。

公共失败结果闭合为：

- `ok=false`；
- `action=read_file`；
- `errorCode=invalid_tool_arguments`；
- `fieldErrors=[]`；
- `failureCount=1`；
- decoder error 只要求非空，不冻结完整文案；
- `productionToolDelegations=0`、`toolExecutions=[]`、`unsafeToolRequests=0`。

## AgentRun 原始事实与 Session/UI 规范化投影

两层事实必须分开理解：

- 原始坏 JSON 只在 AgentRun 的 `model_completed.toolCalls`、`tool_started.arguments` 和 execution arguments 中按同一 toolCall 身份耐久闭合；
- Session 与 UI 使用生产前端规范化投影，保留 `read_file` action 元数据，但没有可解析的 `path`，也不保存或展示原始坏 JSON。

父 Run 最终为 completed，事件顺序固定为 `created → model_started → model_completed → tool_started → tool_completed(failed) → model_pending → model_started → model_completed → completed`；`nextCursor=9`、耐久 `nextSeq=10`、`pendingToolCalls=[]`。两轮 Runtime cursor 从活动态 `4/0` 收敛到终态 `4/3`。Session 角色链为 `user → assistant → tool-call → tool-result → assistant`，toolCallId、agentRunId、规范化 arguments 与失败 result 跨 AgentRun、Session 和 DOM 保持唯一对应。

## 浏览器生命周期与刷新

bundle 与 direct classic 均证明失败工具项在终答前后的两相投影、终态折叠与完整刷新唯一性。direct classic 直接进入 `/dist/frontend/index.classic.html`，精确标记为 `classic-fallback`，没有 bundle ready 或 fallback query，不属于自动 bundle 故障降级。

完整 reload 后仍是同一 AgentRun、Session、失败回执与 DOM 语义；AgentRun POST、Runtime POST、chat 和工具执行四项增量均为 0，没有第二 assistant、tool-result 或 final。

首轮唯一失败来自测试把 UI 的“无 path 参数”误建模为字面 `{}`。真实前端格式保留 `action=read_file` 元数据但没有 `path`；最终断言因此精确为 action 存在、path 和原始坏 JSON 不存在。该修正没有改变产品行为，也没有放宽 timeout、retry、身份、失败结果或清理门禁。

## 稳定语义哈希

以下 SHA-256 排除了随机 ID、时间、端口、完整 decoder 文案、JSONL 字节和完整 HTML；bundle 与 direct classic 完全一致：

- `eventProjection`: `7bd9960cdce1fe4e6cc79c96ebdb6201ecf36e34a3886415b20490268d5dbff6`
- `parseErrorReceiptProjection`: `4408c0eff96e0b57d370df9d6d04ab341c3f8d1d512aab9f5abeefd7f2603558`
- `modelToolReceiptProjection`: `d86effa558f902e0c15442c8bfe6de8127f7a33178ad77791b5671b432788e5a`
- `sessionRoleContent`: `dc6b9beeac5d404fd7fd7ff147e4cfb4bd8fdb9eef4fceebb399bbb93cb16497`
- `sessionToolMeta`: `f460fea9ea4f5fe16f53bace264c0ab3904b5fe5610ac8d82dcb824068f6c1da`
- `activeDom`: `e54e3de59dc8d46a78a819ae0b5b65d791462444e1b592cff96bff71c0226cac`
- `terminalDom`: `0c10ac9845c8e616e880ef9f693636390fffe942d390201d775d343ac0ab72e3`
- `refreshLifecycle`: `04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4`

## 验证结果

- H4-6I 哈希固化后：`2 passed`；
- H4 infrastructure：通过；
- 标准 H4 连续两轮：各 `31 passed`、单 worker、`retries=0`、exit 0；
- H4-6A～H 定向：`16 passed`，既有哈希保持；
- invalid-tool-arguments AgentRun 定向：`1 passed`；
- 前端/P0：`199 passed`；
- 完整 Python：`1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源清理：通过。

## 证明边界与回退

本阶段只证明这一固定 malformed JSON 在 bundle/direct classic 中的生产 parseError 生命周期与同进程刷新零执行；不覆盖缺 path、其他解析错误、执行器失败、取消、长输出、跨进程 active 恢复或工具副作用 exactly-once。

独立回退只需撤销 `tests/e2e/h4/isolated_host.py`、`tests/e2e/h4/smoke.spec.cjs` 的 H4-6I 测试增量及本专题/事实源更新；不涉及生产回退、数据迁移或协议兼容动作。
