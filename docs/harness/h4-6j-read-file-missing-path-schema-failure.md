# H4-6J `read_file` 缺少必填 `path` 的 schema 失败

## 完成范围

H4-6J 只在测试侧为默认 bundle 与 direct classic 各增加一条真实 Chromium 场景。假上游把合法 JSON 原始字符串 `"{}"` 直接写入模型工具调用；生产链完成 `json.loads("{}")` 后进入 `read_file` schema 校验，并因唯一缺失必填字段 `path` 在 `execute_registered_tool` 之前失败。这不是 H4-6I 的 JSON `parseError`，也不是 H4-6E 的 `additional_property`，没有修改工具协议、白名单、安全边界或持久化格式。

公共失败结果严格闭合为：

- `ok=false`；
- `action=read_file`；
- `errorCode=invalid_tool_arguments`；
- `fieldErrors=[{field:"path",reason:"required",message:"is required"}]`，且没有第二个字段错误；
- `failureCount=1`；
- `productionToolDelegations=0`、`toolExecutions=[]`、`unsafeToolRequests=0`。

生产执行器没有被委托，但 AgentRun 仍持久化一条 `status=completed/outcome=failed` 的 execution。原始 `"{}"` 在 `model_completed.toolCalls`、`tool_started.arguments` 和 execution arguments 中按同一 toolCall 身份闭合；失败 receipt 被送入第二轮模型，父 Run 随后产生固定终答并进入 completed。

## AgentRun、Runtime 与 Session/UI 投影

父 Run 的耐久事件顺序为 `created → model_started → model_completed → tool_started → tool_completed(failed) → model_pending → model_started → model_completed → completed`，并保持 `nextCursor=9`、耐久 `nextSeq=10`、`pendingToolCalls=[]`。两轮 Runtime cursor 从活动态 `4/0` 收敛到终态 `4/3`。

Session 角色链为 `user → assistant → tool-call → tool-result → assistant`。AgentRun 保留原始 `"{}"`，但 Session/UI 使用生产规范化投影：`read_file` action 可见、`path` 不存在，并展示 required 失败结果；测试不把页面是否显示字面 `{}` 作为契约，也不把完整人类错误文案纳入哈希。

bundle 与 direct classic 均闭合失败工具组的活动态、正文投影后状态、终态折叠和完整 reload 唯一性。direct classic 直接进入 `/dist/frontend/index.classic.html`，精确标记为 `classic-fallback`，没有 bundle ready 或 fallback query，不属于自动 bundle 故障降级。刷新后仍是同一 AgentRun、Session、失败 receipt 与 DOM 语义，AgentRun POST、Runtime POST、chat 和工具执行四项增量均为 0。

## 共享 helper 的活动态节点替换

完整矩阵曾在共享失败生命周期 helper 的“展开单工具详情、检查内容、再次折叠”路径暴露节点身份竞态。定向诊断对具体旧 `<details>` / `<summary>` 取证时得到 `Element is not attached to the DOM`，直接证明活动态生产重绘会替换节点；问题不属于同一已连接节点的真实点击失效。

修正仍保持真实交互强度：首次点击后立即验证实际节点为 open；内容检查后重新取得当前具体节点并比较身份与连接状态。当前节点仍 open 时，只点击该具体节点并立即证明关闭；旧节点已断开且新节点已按活动态契约恢复 closed 时，不再误点新节点把它打开。最后仍严格断言当前可见 locator 为 closed。该修正没有修改生产代码、超时、worker、retry、产品状态或断言强度，也没有复制前端状态机。

修正前的 `32 passed / 1 failed` 标准轮与节点身份诊断失败轮均不计为通过；有效门禁只采用修正后同一文件哈希下的连续两轮 `33 passed`。

## 稳定语义哈希

以下 SHA-256 排除了随机 ID、时间、端口、完整错误文案、JSONL 字节和完整 HTML；bundle 与 direct classic 完全一致：

- `eventProjection`: `8e0d1a69b13eb0c91eaea433f851f8c1ac4e6ce2e1561f2045bbfab19f846ce5`
- `missingPathReceiptProjection`: `989616f6ead8ea168f0f785627866befd8960d4221be83a36c2b6558764afda7`
- `modelToolReceiptProjection`: `027989be15a449c7cf563e2238404c093361ac7db5ef8dad367b1f6875c6e497`
- `sessionRoleContent`: `73166b500f99d97a978f7d5c8e057a50d3aa0ea44c062de8e12e13909f2d524b`
- `sessionToolMeta`: `b912f584b5b211e7b79d2ae517529bc89bbd4dcd77dfd5258b9c9434d5d3a6da`
- `activeDom`: `30ec16a776f8ecf36035827abb24185ec2d34050288f1db31ebbaf5f625c72da`
- `terminalDom`: `ee55a3e8a0629a776a81e4a411261227a9a708314f40a7bbcc5c01ce4b3b9c88`
- `refreshLifecycle`: `04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4`

## 验证与已知基础设施事实

- H4-6J bundle/direct classic 哈希固化后：`2 passed`；
- 原 H4-6I direct classic 场景修正后独立连续两次通过，H4-6E/I/J bundle/classic 共享路径：`6 passed`；
- H4 infrastructure：通过；
- 标准 H4 连续两轮：各 `33 passed`、单 worker、`retries=0`、exit 0，完整命令分别为 151.143 秒和 126.391 秒；
- invalid-tool-arguments AgentRun 定向：`1 passed`；
- 前端/P0：`199 passed`；
- 完整 Python：`1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源清理：通过。
- 文档收口后在相同实现哈希下轻量复验：H4-6J bundle/direct classic `2 passed`、原 H4-6I direct classic `1 passed`、正式 H4 infrastructure 通过；完整矩阵沿用上述同哈希有效结果，没有重跑完整 pytest 或第三轮标准 H4。

更早的标准入口曾独立出现一次 infrastructure `/api/ping` `fetch failed`，当前没有稳定复现或唯一根因；R003 的外层临时诊断载体自身超时也没有形成产品结论。随后三次未经包装的正式 infra、自身最终 infra 门禁及两轮完整标准入口均通过。上述历史事实继续保留，但不计产品失败、不计通过轮，也不代表通过重跑定位或修复了该环境/传输异常。

## 证明边界与回退

本阶段只证明固定空对象缺少 `path` 在默认 bundle/direct classic 中的生产 schema required 生命周期、第二轮失败回执、父 Run completed 与同进程刷新零执行。它不覆盖其他 required 字段、其他工具、真实模型或外部网络、跨进程 active 恢复、工具取消、发布或真实外部副作用 exactly-once。

独立回退只需撤销 `tests/e2e/h4/isolated_host.py`、`tests/e2e/h4/smoke.spec.cjs` 的 H4-6J 测试增量、共享 helper 节点身份修正及本专题/事实源更新；不涉及生产回退、数据迁移或协议兼容动作。
