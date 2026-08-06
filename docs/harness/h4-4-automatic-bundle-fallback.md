# H4-4 自动 bundle 失败降级

## 1. 阶段结论

H4-4 已在真实 Chromium 中证明默认根入口的两条生产自动降级分支：`code.bundle.js` 网络加载失败时以 `fallback=bundle-load` 进入生成的 classic 页面；bundle 脚本成功加载但未设置 ready 标记时，以 `fallback=bundle-init` 进入同一 classic 页面。两条路径都由默认入口现有 `location.replace()` 触发，测试不调用 classic 直达辅助入口，也没有复制第二套加载器或 Session、AgentRun、Runtime 状态机。

本阶段只修改 H4 浏览器测试及隔离 host 的测试基础设施，包括 Node host 的退出分类、自检契约，以及 Python host 的脱敏 metrics 阶段诊断；没有修改生产入口、构建器、Playwright 配置、AgentRun/Runtime/Session 协议或持久化格式。

## 2. 两条浏览器场景

标准 H4 矩阵新增：

- `bundle-load failure automatically falls back to classic`
- `bundle-init failure automatically falls back to classic`

每例在独立 page 首次导航前，只对 `/dist/frontend/code.bundle.js` 安装一次精确页面级路由：load 场景中止这一个请求；init 场景返回不设置 `data-code-frontend-ready` 的最小惰性 JavaScript。路由不匹配 classic 的 `app.js`、`agent-runtime.js` 或其他脚本，也不接管生产初始化。

两例共同验证：

- 初始导航为默认 `/`，主 frame 只经历根入口和一次 classic 目标导航；
- 最终路径为 `/dist/frontend/index.classic.html`，query 原因分别精确为 `bundle-load` 和 `bundle-init`；
- 最终 `data-frontend-runtime="classic-fallback"`，且 `data-code-frontend-ready` 不为 `true`；
- classic 主文档、`app.js`、`agent-runtime.js`、Session 列表与模型目录均只执行一轮稳定初始化，没有重定向循环或重复 classic 初始化；
- 降级后继续完成一条生产纯文本任务：AgentRun POST 1、Runtime POST 0、上游 chat 1、工具执行 0，AgentRun/Runtime 身份各唯一，user、assistant 与 final 各出现一次；
- 非 loopback 请求继续被阻止，非预期 page error 为 0，每例子进程、端口和临时根均清理归零。

load 场景只冻结目标 bundle 路径、`requestfailed` 事件类别和次数；init 场景不产生该 `requestfailed`。Chromium 的完整控制台错误正文不属于稳定协议，不作为门禁。测试也不增加 `history.length` 或 `goBack()` 断言；`location.replace()` 由生产入口源码契约和最终导航序列共同支撑，避免把浏览器历史栈实现细节变成脆弱门禁。

## 3. 隔离 host 正常退出竞态

H4-4 首次完整矩阵的第二轮在既有 `classic fallback completes one plain-text task` teardown 暴露出一次基础设施假失败：Python host 已处理 shutdown 并以 exit code 0 正常退出，端口、子进程和临时根也都已清理，但 Node readline 尚未来得及消费成功响应，旧 child-exit 处理便将 pending shutdown 无条件拒绝为 `H4 isolated host exited (0)`。阶段因此按门禁停止，没有把失败轮计入通过结果，也没有靠重跑或删除错误字符串掩盖问题。

修正后，Node host 为 pending 命令保留命令身份，并让 child-exit 处理复用可直接测试的纯分类边界。只有以下条件同时满足时，pending shutdown 才可由进程退出正常收敛：

- `stop()` 已明确发起 shutdown；
- 当前 pending 命令正是该 shutdown；
- exit code 严格为 0；
- signal 为 `null`。

非零退出、signal 退出、pending 非 shutdown 命令，以及不是由 `stop()` 发起的 shutdown 仍全部拒绝。命令超时、stdin 写入失败、子进程未退出、任一端口未关闭、临时根未删除或其他清理错误的既有处理不变；实现没有按字符串过滤错误，也没有清空 `cleanupErrors`。

基础设施自检直接冻结四类结果：预期 stop shutdown + exit 0 正常收敛；shutdown + 非零或 signal 拒绝；pending 非 shutdown + exit 0 拒绝；非 stop 上下文 shutdown + exit 0 拒绝。真实隔离 host 自检连续 5/5 次通过，随后两轮标准 H4 矩阵均未再出现该竞态。

## 4. 独立 metrics 超时与诊断边界

退出竞态修正通过后，提交前复验又在 `bundle-init failure automatically falls back to classic` 的 fixture teardown 暴露过一次独立的 `H4 host command timed out: metrics`。该轮浏览器功能断言已经通过，最终子进程、端口和临时根归零；阶段当时仍按门禁停止，没有靠继续重跑将失败计为通过，也没有改动 5 秒命令上限、跳过 stop-time metrics 或过滤 `cleanupErrors`。

只读审计没有发现明确锁反转；历史输出又缺少 metrics 内部分阶段证据，因此不能把该超时归因为终态未收敛、teardown 顺序或快照锁。为保留下一次首错证据，Python host 的 metrics 操作在 stderr 增加白名单 breadcrumb，以单调时钟区分 request received、metrics snapshot、gate snapshots、production snapshot、Session JSONL 和 response emit；字段只包含固定阶段名、进程内递增序号、耗时及成功/失败类别，不进入 stdout JSON 控制协议，也不记录 ID、正文、路径、环境、端口或凭据。smoke fixture 同时记录测试体的 AgentRun/Runtime 终态事实，并仅在 cleanup 失败时附加有界的白名单诊断；异常传播、5 秒上限、stop-time metrics、`cleanupErrors` 和资源清理断言均保持不变。

诊断加入后，一次 bundle-init 定向场景通过；随后累计三轮标准 11 例矩阵连续通过、零 retry。两条自动降级场景在测试体采样时均为 AgentRun `completed`、`nextCursor=4` 且终态事件存在，Runtime 为 `completed`、`nextCursor=3`；每例 stop-time metrics 的 `requestCount=2`，最大耗时为 15～16 ms，主要来自 Session JSONL 阶段，其余阶段约为 0 ms，H4 资源均归零。历史单次 metrics 超时仍未复现、根因未定位；这些成功样本只排除了“测试体尚未终态”这一解释，不能写成已经通过等待终态、调整 teardown 或修改快照锁修复。

## 5. 验证基线

实现复验结果：

- 两条 H4-4 定向浏览器用例：`2 passed`，约 5.4 秒；
- `npm run test:h4:infra` 连续 5/5 次通过；
- 严格退出分类修正后，两轮全新 `npm run test:h4:e2e` 的 infra 均通过，Playwright 均为 `11 passed`、`retries=0`，分别约 31.1 秒和 33.1 秒；
- metrics 诊断加入后，一次 bundle-init 定向场景为 `1 passed`，累计三轮标准 `npm run test:h4:e2e` 均为 infra 通过、`11 passed`、`retries=0`；最后两轮 Playwright 分别约 37.5 秒和 37.7 秒；
- `npm run check:frontend` 通过；
- R003 已完成的前端模块测试为 `171 passed`，完整 Python 回归为 `1113 passed, 739 subtests passed`；后续只修改 H4 测试基础设施诊断，相关生产与单元测试输入哈希未变化，因此沿用该结果；
- 三个 H4 Node 文件语法、Python host 语法与 `git diff --check` 通过；
- H4 子进程、临时根、Playwright output 和暂存区均归零。

收口前冻结的四个实现/测试文件 SHA-256 为：

- `tests/e2e/h4/smoke.spec.cjs`：`9870acc56995362e9620df3886d6e97eda8cc73e251d2577785816a32780c550`
- `tests/e2e/h4/isolated_host.py`：`4e28aa2807786529bbb6f0e481726a127464a2947aa6faff4d000438b907b410`
- `tests/e2e/h4/isolated-host.cjs`：`213e854cab54eb62dce8c01c9840fd7dd13c97371336c8db4c80988c90bd6705`
- `tests/e2e/h4/infrastructure-selfcheck.cjs`：`3f8bff6c46d379c25d72470b5f621261b41afed1fe8c1cd90194da4d095c4954`

## 6. 证明边界与回退

H4-4 只证明同一进程、默认根入口、loopback 隔离环境下的自动 bundle-load/bundle-init 降级及降级后的纯文本任务闭环。direct classic 流式刷新已由 H4-3 单独覆盖，不属于本阶段新增结论。本阶段不覆盖服务重启、跨进程恢复、工具刷新、问卷/授权、压缩、图片、队列/并行/Child、真实 CDN/完整 Markdown、浏览器崩溃、EXE 或发布门禁，也不把测试注入等同于真实公网故障分布。

独立回退只需撤销 `smoke.spec.cjs` 的两条场景和诊断、Node host 的退出分类、自检契约、Python host 的 metrics breadcrumb 及本阶段专题和事实源更新。无需修改生产代码、迁移持久化数据或改变 H4-1/H4-2/H4-3 已有证据。历史单次 metrics 超时应继续保留为未复现、根因未定位的测试基础设施边界；breadcrumb 是后续首错诊断，不是门禁放宽或已定位根因的证明。
