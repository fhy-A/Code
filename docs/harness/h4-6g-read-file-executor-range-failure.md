# H4-6G `read_file` 生产执行器行范围失败闭环

## 1. 阶段结论

H4-6G 只在测试侧增加一个固定、可复现的生产执行器失败契约：假上游声明 `read_file({"path":"fixture.txt","startLine":2,"endLine":1})`。该参数通过生产 JSON/schema 校验，也通过 H4 既有的只读 `action=read_file`、`path=fixture.txt` 白名单，随后真实进入 `execute_registered_tool → execute_read_file_tool`，最终因 `endLine < startLine` 在生产执行器内部失败。

本阶段没有删除或改写 fixture，没有扩大 action/path 白名单，没有由 H4 wrapper 注入异常，也没有修改生产代码、协议、Session JSONL 或持久化格式。该证据不是 `invalid_tool_arguments`，也不代表缺文件、权限、编码或其他文件系统失败已经覆盖。

两条真实 Chromium 场景在同一阶段同时覆盖默认 bundle 与 direct classic，并各自包含活动态、终态和完整 reload：

- `bundle executor-range failure lifecycle and reload`
- `direct classic executor-range failure lifecycle and reload`

direct classic 直接加载 `/dist/frontend/index.classic.html`，精确标记为 `classic-fallback`、无 bundle ready 和 fallback query；它不是 H4-4 的自动故障降级。

## 2. 执行器、AgentRun 与 Runtime 证据

bundle/classic 复用 H4-6E/H4-6F 的 contract 驱动生命周期、`before-tool-final-delta` 与 `before-tool-terminal`，没有复制第二套 AgentRun/Session/DOM 状态机。固定调用在两种入口中均满足：

- `productionToolDelegations=1`，host `toolExecutions` 恰好一条；
- execution arguments 严格为 `path/startLine/endLine` 三字段；
- result 为 `ok=false`、`action=read_file`、`failureCount=1`，且不存在 `invalid_tool_arguments`、`fieldErrors` 或 retry limit；
- 人类错误文案只检查非空并同时涉及 `startLine/endLine`，不冻结完整英文或本地化文本；
- AgentRun 依次记录 `created → model_started → model_completed → tool_started → tool_completed(failed) → model_pending → model_started → model_completed → completed`；
- 终态为 `nextCursor=9`、耐久 `nextSeq=10`、`pendingToolCalls=[]`，父 Run 经第二轮固定终答正常 completed；
- 两个 Runtime 从活动态 cursor `4/0` 收敛到终态 `4/3`；
- 单次任务计数为 AgentRun POST 1、Runtime POST 0、上游 chat 2、生产工具执行 1。

失败回执作为第二轮 `role=tool` 输入进入真实模型链；测试只保存去随机化规范投影，不记录完整请求、正文、请求头、Key、真实路径或原始 JSON 字段顺序。

## 3. Session、DOM 与刷新唯一性

Session 角色链固定为 `user → assistant → tool-call → tool-result → assistant`。tool-call/tool-result 以同一 toolCallId、agentRunId、三字段 arguments 和执行器失败 result meta 闭合；随机身份只在同一场景刷新前后比较，不进入跨运行字面哈希。

终答正文释放前，工具组为 running、单项为 failed；用户通过真实点击展开后，可看到唯一三字段参数和非空失败详情。终答正文进入生产投影而 terminal 仍未释放时，工具组转为 failed，真实 DOM 重绘后同一 process key 与 open 状态保持。前端终态信号闭合后，父 trace completed、工具组/单项 failed 且默认折叠，用户仍可按父 trace→工具组→单项逐层展开查看。

完整 reload 使用生产 Session 恢复链打开同一会话，不注入私有 state 或 localStorage。刷新后 AgentRun、Runtime、toolCall、九事件、失败 receipt、Session meta、process key 和 DOM 顺序保持唯一，父 trace/工具组/单项恢复默认折叠；AgentRun POST、Runtime POST、chat 与工具执行四项增量均为 0。

## 4. 固定语义哈希

bundle 首轮冻结八类不含随机 ID、时间、端口、完整错误文案、原始 JSONL 或完整 HTML 的 SHA-256，direct classic 必须匹配同一集合：

- eventProjection：`05679b66e0b8957455b7a57dde5cc6455948ef69a609772ad33f57489bf0d08d`
- executorReceiptProjection：`3a1b994b1fe398c83cb8adfcf7e71e2b2a98309b5e16cd0b8924420e719396a5`
- modelToolReceiptProjection：`60e752356006ec8f15d661edd9724ebdf24c7a0c1633af5bdf37e75a28a5f0c8`
- sessionRoleContent：`75ae4df19c62ebff5c92cc14b04015238de0a5d4b4a7789d0da50dd965c60e1e`
- sessionToolMeta：`d7ec6a76b4b67e204a24b508b6e548a46e2d92fe9ef8575d6a30bc8b5c5fc500`
- activeDom：`53db0899dd213b606bd89904aa7f4df93cf6270a535648b812b6cb7c2e7da425`
- terminalDom：`92162bb8446b0556cb897912ea0aa0db129b9682a8a071b96ad07795c335299c`
- refreshLifecycle：`04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4`

H4-6A 的六类旧哈希、H4-6C/H4-6D 的八类旧哈希及 H4-6E/H4-6F 的八类参数校验失败哈希均保持原值。

## 5. 观察收敛与有效验证

首轮标准 H4 曾出现 `26 passed / 1 failed`。失败位于既有 H4-6C `startMultiToolDetailAtSecondExecute()` 的同步 `controlIds()` 请求观察点：持久 AgentRun 事件已经含第一轮 runtimeRunId，但请求摘要观察器尚未收敛；随后脱敏诊断已观察到对应 Runtime GET。修订只把该同步断言替换为保持 AgentRun/Runtime 精确身份相等的有界 `expect.poll`，没有加入 sleep、额外请求、retry、超时调整或数量放宽，也没有修改产品行为。修订后 H4-6C/H4-6D 四例与 H4-6G 两例通过，连续两轮标准 `npm run test:h4:e2e` 均为 `27 passed`、单 worker、`retries=0`、exit 0。

剩余有效回归为：

- AgentRun/route 定向 `4 passed`；
- 前端模块/P0 `199 passed`；
- 完整 Python `1113 passed, 739 subtests passed`；
- `npm run check:frontend`、Node/Python 语法与 `git diff --check` 通过；
- H4 子进程、临时根和 Playwright output 文件归零。

以下均发生在产品测试收集或产品路径之外，不计为产品通过或失败：首次 Chromium 启动 `spawn EPERM`；Codex bundled Python 缺少 pytest；通用 WindowsApps Python 别名不可识别；真实 AppX Python 在沙箱内访问受限，而沙箱外预检为 Python 3.12.10/pytest 9.1.1 并完成正式回归；`check:frontend` 首次在沙箱内被 esbuild 目录权限阻断，同一命令在沙箱外通过。它们没有通过修改 PATH、安装依赖、切换第三个解释器或放宽内部测试门禁规避。

## 6. 完成边界与独立回退

H4-6G 只证明合成 `fixture.txt` 上 schema-valid 的 `read_file` 行范围语义失败，能够在默认 bundle 与 direct classic 中进入真实生产执行器，并闭合 AgentRun/Runtime/Session/DOM、第二轮固定终答及同进程刷新零重执行。

本阶段不证明缺文件、权限、编码、大文件、其他工具执行器、重复失败限流、工具取消、长输出、跨进程 active 恢复或真实外部副作用 exactly-once。独立回退只需撤销 `tests/e2e/h4/isolated_host.py` 的固定合成场景、`tests/e2e/h4/smoke.spec.cjs` 的 contract 参数化/两条场景及本次收口文档；不涉及生产回退、数据迁移或协议兼容动作。
