# H4-6H `read_file` 缺文件生产执行器失败闭环

## 1. 阶段结论

H4-6H 只在测试侧增加一个固定、可复现的缺文件契约：假上游声明 `read_file({"path":"h4-missing-fixture.txt"})`。该参数通过生产 `read_file` schema；H4 测试包装器只在原有 `fixture.txt` 契约之外增加这一个固定相对路径，并继续拒绝绝对路径、`..` 路径穿越、额外字段、其他 action 和其他 path。满足这些前置条件后，包装器仍调用原始 `execute_registered_tool → execute_read_file_tool`，没有自行构造缺文件异常，也没有修改生产代码、协议、Session JSONL 或持久化格式。

`resolve_project_path` 对该 project 根内的固定相对目标直接返回 project target；生产执行器随后在 `exists()/is_file()` 分支抛出精确错误“文件不存在”。隔离 home 中同名目标不存在只是一项额外隔离审计，用于证明测试没有借用用户目录；它不是本次生产失败的因果链，也不参与生产路径解析。

两条真实 Chromium 场景在同一阶段同时覆盖默认 bundle 与 direct classic，并各自包含活动态、终态和完整 reload：

- `bundle missing read_file executor failure lifecycle and reload`
- `direct classic missing read_file executor failure lifecycle and reload`

direct classic 直接加载 `/dist/frontend/index.classic.html`，精确标记为 `classic-fallback`、无 bundle ready 和 fallback query；它不是 H4-4 的自动故障降级。

## 2. 安全边界与生产执行证据

测试启动、生产委托前、生产执行后及完整刷新后均核对 `h4-missing-fixture.txt`：路径不是绝对路径、不含 `..`，解析后仍位于每例独立临时 project 根，而且目标始终不存在。包装器只接受精确 payload `{"path":"h4-missing-fixture.txt"}`，不允许附带 `startLine/endLine` 或其他字段；既有 `read_file("fixture.txt")`、危险 action/path 拒绝、非 loopback 阻断和基础设施自检保持不变。

bundle/classic 均闭合以下事实：

- 单一 AgentRun、单一 toolCall；
- `productionToolDelegations=1`、`toolExecutions=1`、`unsafeToolRequests=0`；
- 首次耐久 result 精确为 `ok=false`、`action=read_file`、`error=文件不存在`、`failureCount=1`；
- result 不含 `errorCode/code`、`invalid_tool_arguments`、`fieldErrors`、`retryBlocked` 或 `retryLimitReached`；
- AgentRun 依次记录 `created → model_started → model_completed → tool_started → tool_completed(failed) → model_pending → model_started → model_completed → completed`；
- 终态为 `nextCursor=9`、耐久 `nextSeq=10`、`pendingToolCalls=[]`，父 Run 经第二轮固定终答 completed；
- 两个 Runtime 从活动态 cursor `4/0` 收敛到终态 `4/3`；
- 单次任务计数为 AgentRun POST 1、Runtime POST 0、上游 chat 2、生产工具执行 1。

失败回执作为第二轮 `role=tool` 输入进入真实模型链。测试只冻结去随机化规范投影，不保存完整请求、请求头、Key、真实绝对路径、原始 JSONL 字节或随机身份。

## 3. Session、DOM 与刷新唯一性

Session 角色链固定为 `user → assistant → tool-call → tool-result → assistant`。tool-call/tool-result 以同一 toolCallId、agentRunId、精确 arguments 和生产失败 result meta 闭合；随机身份只在同一场景的刷新前后比较。

终答正文释放前，工具组为 running、单项为 failed；用户真实展开后可以看到唯一固定 path 与精确缺文件详情。终答正文进入生产投影而 terminal 尚未释放时，工具组转为 failed，真实 DOM 重绘后同一 process key 和 open 状态保持。前端终态信号闭合后，父 trace completed、工具组/单项 failed 且默认折叠，用户仍可逐层展开查看。

完整 reload 通过生产 Session 恢复链打开同一会话，不注入私有 state 或 localStorage。刷新后 AgentRun、Runtime、toolCall、九事件、失败 receipt、Session meta、process key 和 DOM 顺序保持唯一，父 trace/工具组/单项恢复默认折叠；AgentRun POST、Runtime POST、chat 与工具执行四项增量均为 0。project 目标和隔离 home 审计目标在刷新后仍不存在。

## 4. 固定语义哈希

bundle 首轮冻结八类不含随机 ID、时间、端口、完整 HTML、原始 JSONL 或 runtime 标记的 SHA-256；direct classic 必须匹配同一集合：

- eventProjection：`4dd3fb7c43cbe9bcc0fb95b5df7e4cf794f35f4e3a9eb2c8d388c2e7389314f2`
- missingFileReceiptProjection：`bef7e2038ec8d5a56437dbdeef1b43a73b7553d67fe637ae3fb26d9ae1a8b498`
- modelToolReceiptProjection：`4204a133ea7a8e74a5981668a013feb29d86b7bc492941b4e25c6a64652a2b8d`
- sessionRoleContent：`450f53474e8c9fe65b71409b7efb6c3a222e5f4629bd8dbbc89d6d3b6a05c923`
- sessionToolMeta：`d8e40c3d2d303c0e4c4c6394dde046869f7ffaee8414f960d54dbc3261cb2c7e`
- activeDom：`b6ae61b6e790e68c2c2d0586fb0d5a62d2074b88d4f6203a35760a78ced8c983`
- terminalDom：`2aed54d3a2fdb4e76d6c0fe53e4a223992c116adda0826b08334e1a44d54848f`
- refreshLifecycle：`04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4`

H4-6A～H4-6G 的既有语义哈希保持原值。

## 5. 有效验证

- H4-6H 首轮：bundle `1 passed`、direct classic `1 passed`；哈希固化后合并 `2 passed`；
- `npm run test:h4:infra` 通过；
- 连续两轮标准 `npm run test:h4:e2e` 均为 `29 passed`、单 worker、`retries=0`、exit 0，完整命令 100.9/101.6 秒；
- H4-6A～H4-6G 定向 `14 passed`，旧哈希保持；
- 缺文件 route、路径穿越与相关 AgentRun 定向 `4 passed`；
- 前端模块/P0 `199 passed`；
- 完整 Python `1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与 H4 资源清理通过。

真实 AppX Python 在沙箱内不可执行属于环境前置限制；沙箱外预检为 Python 3.12.10、pytest 9.1.1，并完成正式 Python 回归。该限制没有进入产品测试收集，不计为产品失败，也没有通过安装依赖、修改 PATH 或更换第三个解释器规避。

## 6. 完成边界与独立回退

H4-6H 只证明固定缺失相对路径在默认 bundle 与 direct classic 中通过生产 schema 和受控测试安全边界、真实进入 `read_file` 生产执行器并因文件不存在失败，同时闭合 AgentRun/Runtime/Session/DOM、第二轮固定终答及同进程刷新零重执行。

本阶段不证明权限、编码、大文件、其他工具执行器、重复失败限流、工具取消、长输出、跨进程 active 恢复或真实外部副作用 exactly-once。独立回退只需撤销 `tests/e2e/h4/isolated_host.py` 的固定缺文件场景、`tests/e2e/h4/smoke.spec.cjs` 的 contract/两条浏览器场景及本次收口文档；不涉及生产回退、数据迁移或协议兼容动作。
