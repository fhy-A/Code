# H4-6E `read_file` 参数校验失败生命周期与刷新唯一性

## 1. 阶段结论

H4-6E 只在测试侧为默认 bundle 增加一个固定的生产参数校验失败路径。假上游声明 `read_file({"path":"fixture.txt","unexpected":true})`：`path` 合法，唯一错误是生产 schema 以 `additional_property` 拒绝 `unexpected`。该证据不是文件系统失败，也不是工具执行器失败；H4 wrapper 没有主动抛错，工具 registry、action/path 白名单、AgentRun/Runtime/Session 协议、JSONL 和生产代码均未修改。

两条真实 Chromium 场景分别覆盖参数校验失败后父 Run 完成，以及 completed 失败回执经生产 Session 恢复链完整 reload 后保持唯一且零执行：

- `invalid read_file arguments fail before execution and complete with final answer`
- `completed invalid read_file receipt reloads uniquely without execution`

## 2. 生产校验、回执和 AgentRun

唯一失败结果固定为 `errorCode=invalid_tool_arguments`、`failureCount=1`、`fieldErrors=[{field:"unexpected",reason:"additional_property"}]`。错误 message 只要求非空，不冻结完整英文或本地化文案。AgentRun 保留一条 `status=completed/outcome=failed` 的耐久 execution，用于解释事件、Session 和 UI；与之区分，H4 生产执行包装器的 `productionToolDelegations=0`、host `toolExecutions=[]`，证明 `execute_registered_tool` 没有被委托。

父 Run 经第二轮固定模型回答正常 completed，事件顺序为：

`created → model_started → model_completed → tool_started → tool_completed(failed) → model_pending → model_started → model_completed → completed`

终态固定 `nextCursor=9`、耐久 `nextSeq=10`、`pendingToolCalls=[]`，唯一 terminal 事件为 completed。请求边界为 AgentRun POST 1、Runtime POST 0、上游 chat 2、生产工具委托 0。两个 Runtime 的真实 cursor 从首次浏览器结果确认并冻结：活动态第一轮/第二轮为 `4/0`，终态为 `4/3`。

第二轮送模 `role=tool` 回执只形成脱敏规范投影，包含 tool alias、action、errorCode、failureCount 和固定 fieldErrors；不保存完整请求、正文、请求头、Key、原始 JSON 序列或字段顺序。Session 角色链固定为：

`user → assistant → tool-call → tool-result → assistant`

tool-call/tool-result 通过同一 toolCallId、agentRunId、arguments 和失败 result meta 闭合；人类错误文案不进入稳定哈希。

## 3. DOM 两相语义与刷新

在第二轮终答正文释放前，父 Run 仍处于模型轮，工具组外层为 running，唯一工具项为 failed。用户通过真实点击展开工具组和单项，可看到唯一的合法 path、额外字段 `unexpected` 和非空失败详情。

终答正文 delta 进入生产投影后、terminal 仍未释放时，工具组根据已完成的失败 outcome 转为 failed；真实 DOM 节点发生重绘，但同一 `data-tool-process-key` 与用户打开的工具组 `open` 状态保持，没有第二组、重复项、重复回执或重复 final。终态先独立闭合服务端九事件，再等待前端 banner 消失、stop 禁用、active trace 归零和 completed trace 唯一；此后父 trace completed、工具组/单项均为 failed 且默认折叠，用户仍可按父 trace→工具组→单项真实展开查看。

完成态场景经完整 reload 和生产 Session 列表恢复同一会话，不注入私有 state 或 localStorage。刷新后父 trace、工具组和单项恢复默认折叠，AgentRun、toolCall、九事件、失败回执、Session meta、process key 与 DOM 顺序不变；AgentRun POST、Runtime POST、chat、生产工具执行四项增量均为 0。

## 4. 固定语义哈希

H4-6E 冻结八类不含随机 ID、时间、端口、完整 HTML、原始 JSONL、完整请求及人类错误文案的 SHA-256：

- eventProjection：`860e9f45fe924f5a8a94ca031d2839264fd550dfcbef0c4a9a1bb89393bd6ef4`
- invalidReceiptProjection：`bf4ec29db9ac54505687e3fb3c2040ff5f4fa17aed715700c958317a3aa6c776`
- modelToolReceiptProjection：`1b94536a4cc63c2bc3b98c54eb14c329ac585b5ec65bf85c1ca7bbd080ab6c80`
- sessionRoleContent：`cbdcb15dad4b61b34bdf89556131827fc7fd973f88b9b9368e329bf61b1821fb`
- sessionToolMeta：`c62eca9c84fb4d3c94968c2423f8db13cff6ca254fd90eba9bb225c87d438285`
- activeDom：`3f718cb47d5fb90dcdc0bbc3a425718a43f1c0fe6ee082ce53e90a22cabc2ad4`
- terminalDom：`4cdf1271fd50f4060b985a2c9b579bad19b075e0b562881337cd2ddab42b161d`
- refreshLifecycle：`04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4`

H4-6A/H4-6B 的六类旧哈希和 H4-6C/H4-6D 的八类旧哈希均由既有浏览器场景再次核对并保持原值。

## 5. 验证与首错记录

- A/B 在首次采集和写入字面哈希后分别再次通过；H4 infra 通过；
- 连续两轮标准 `npm run test:h4:e2e` 均为 `23 passed`、零 retry，完整命令为 79.4/78.8 秒；
- H4-6A～H4-6D 八条既有工具详情场景为 `8 passed`，旧哈希保持；
- `test_agent_rejects_invalid_tool_arguments_without_calling_executor` 为 `1 passed`；
- 前端模块/P0 为 `199 passed`；
- 完整 Python 回归为 `1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 及 H4 子进程、端口、临时根和 output 清理均通过。

实现期两次未计入通过轮的首错都属于新增测试的观测建模修正：第一次在生产 Runtime GET 前过早核对请求摘要集合，第二次把终答正文投影后的失败组误预期为 running。修订后分别冻结“终答正文前 running/单项 failed”和“正文投影后 failed 且 key/open 保持”的真实两相语义；没有修改生产、提高 timeout、增加 retry/sleep、吞错或放宽清理门禁。

文档收口后只复跑 H4-6E 两条定向、infra、语法和 diff；连续两轮 23/23、旧 H4 八条、完整 pytest、前端/P0 与 `check:frontend` 均沿用上述相同实现/测试文件 SHA-256 的已完成结果，不描述为文档后重新运行。

## 6. 完成边界与独立回退

本阶段只证明默认 bundle 中“合法 path + 唯一额外字段”的生产 `additional_property` schema 拒绝、失败回执进入第二轮、父 Run completed、真实失败 DOM 生命周期，以及同进程刷新零执行和唯一性。它不覆盖缺少 path、JSON parse、文件系统/执行器失败、重复失败限流、direct classic、取消、长输出、异构工具、跨进程 active 恢复或工具副作用 exactly-once。

独立回退只需撤销 `tests/e2e/h4/isolated_host.py` 的固定场景/脱敏指标、`tests/e2e/h4/smoke.spec.cjs` 的两条 H4-6E 场景与哈希，以及本阶段收口文档；不涉及生产回退、数据迁移或协议兼容动作。
