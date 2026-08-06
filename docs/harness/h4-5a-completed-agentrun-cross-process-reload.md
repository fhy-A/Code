# H4-5A 已完成 AgentRun 的真实跨进程重载

## 1. 阶段结论

H4-5A 已在隔离 Chromium 与真实 CodeHandler 进程边界中证明一条 completed/terminal 纯文本 AgentRun 的跨进程重载路径：generation A 完成任务并持久化后完全退出，两个 loopback 端口确认关闭；generation B 使用不同 PID、新随机 loopback 端口和新 origin 启动，但复用同一受控临时 root、data、project 与 home。B 重新 import 并启动真实 `server.py`/CodeHandler，没有复用 A 的 Python 对象、模块全局或 loader 内存。

浏览器在 B 中通过生产 Session 列表和可见 UI 选择同一唯一 Session，没有注入私有 `state`、localStorage 快照或前端 reducer。B 从磁盘加载同一 completed AgentRun；旧 Runtime GET 返回 404，且没有创建替代 Runtime、第二 AgentRun、第二上游请求或工具执行。本阶段只增加 H4 测试基础设施和浏览器证据，没有修改生产代码、AgentRun/Runtime/Session 协议或持久化格式。

## 2. 真实 A → B 进程边界

跨进程生命周期由隔离 host 拥有唯一临时根，并保持普通 `startIsolatedHost()`/`stop()` 行为不变：

1. generation A 使用独立 PID 与随机 CodeHandler/假上游端口完成纯文本任务；
2. A 的 AgentRun 与 Runtime 均进入 terminal，唯一 terminal 事件和 Session JSONL 完成持久化；
3. A 执行 shutdown，确认子进程退出且两端口关闭，同时只在受控跨代生命周期中暂时保留 owned root；
4. generation B 以不同 PID 和新随机端口启动，复用同一 owned root/data/project/home；
5. 新浏览器页面连接 B 的新 origin，通过生产 UI 打开同一 Session；
6. B 完成证据采样后退出，最终清理唯一临时根；generation stop、final cleanup 与重复 stop 均保持幂等。

基础设施自检同时固定 A/B PID 不同、A 两端口关闭先于 B ready、跨代路径相同且位于 owned root、A 停止后 root 仍存在、最终 root 删除，以及 B 启动失败时资源仍归零。环境白名单、父环境敏感变量隔离、只读工具边界、5 秒命令上限和严格退出分类均未放宽。

## 3. 请求、身份与持久化证据

generation A：

- AgentRun POST 1、Runtime POST 0、上游 chat 1、工具执行 0；
- AgentRun 状态为 `completed`，`nextCursor=4`，事件顺序为 `created → model_started → model_completed → completed`，terminal 事件唯一；
- Runtime 状态为 `completed`，`nextCursor=3`；
- result SHA-256 为 `e129e0ef87b3c2fd20d8142e0ab08f63ded268b467561a7df284205a79a4268b`；
- Session JSONL 规范 role/content SHA-256 为 `91b17aaec8ae34fe35eaf1433130b0b1cd84c9adbdf63e8e0862a3015431aa4d`。

generation B：

- AgentRun POST 0、Runtime POST 0、上游 chat 0、工具执行 0；
- 生产 API 返回与 A 相同的 AgentRun ID、实际 `clientRequestId` 值、terminal status、cursor、事件类型、result 和事件中保存的旧 Runtime ID；
- 旧 Runtime GET 精确返回 404，没有创建替代 Runtime；
- Session JSONL role/content 哈希与 A 完全一致；
- DOM 中原 user、assistant、final 各出现一次，没有 active banner、停止入口、暂停或失败提示，也没有重复正文。

普通前台路径的 `clientRequestId` 当前实际值为空字符串。本阶段只验证 A/B 保留同一实际值，不把它描述为非空稳定映射，也不以该字段单独证明 Session、AgentRun 或 Runtime 归属。

## 4. 已知测试基础设施风险

阶段验证期间，历史两次标准矩阵分别出现过 `release-model` 与 `release-model-catalog` 控制响应 5 秒超时；命令副作用和任务 terminal 随后成立，但 Node pending 未在时限内收敛。两轮临时有界诊断的正常样本没有复现超时，无法唯一归因于 Python response emit、Windows pipe/readline、Node event loop 或 pending 竞态。

R003/R004 临时诊断已完整回退。最终实现没有迁移到 HTTP、放宽 5 秒上限、增加 retry/sleep、吞掉错误，或把“副作用已发生”视为控制命令成功。最终文件形态的定向、infra、连续两轮标准 H4 与完整回归均通过；因此该问题保留为低概率测试基础设施已知风险，不能描述为已修复，也不是已确认的产品跨进程失败。

## 5. 验证基线与冻结哈希

最终代码形态验证结果：

- H4-5A 定向：`1 passed`，5.1 秒；
- `npm run test:h4:infra`：通过；
- 连续两轮标准 `npm run test:h4:e2e`：均为 infra 通过、`12 passed`、`retries=0`；Playwright 分别 45.6/41.6 秒，完整命令分别 55.2/51.0 秒；
- H3-2C2：`5 passed, 20 subtests passed`；
- completed AgentRun/tool receipt 定向：`3 passed`；
- 前端模块与相关 P0：`199 passed`；
- 完整 Python 回归：`1113 passed, 739 subtests passed`，144.40 秒；
- `npm run check:frontend`、Node/Python 语法和 `git diff --check`：通过；
- 验证后 H4 子进程、端口、临时根、Playwright output 与暂存区均归零。

收口冻结的测试文件 SHA-256：

- `tests/e2e/h4/isolated-host.cjs`：`10afb7586451bf3b6c978d9befa5c443fb05237045ee2009e1808eeb966b501d`
- `tests/e2e/h4/infrastructure-selfcheck.cjs`：`ad0f4df1acb108b9efb9b980455fe2e11a9a50a24360929441c1950deb06f912`
- `tests/e2e/h4/smoke.spec.cjs`：`a239a38c0c3674e390d917d4aaf3976f52245ae2390b2232898a866ed4e74516`

## 6. 完成边界与回退

H4-5A 只证明 completed/terminal 纯文本 AgentRun 在“进程 A 完全退出、进程 B 从同一受控持久化根重新加载”的真实边界中保持身份、事件、结果、Session JSONL 和 UI 唯一性。它不证明：

- active Run 跨进程自动续流或部分正文保留；
- 同 origin、原标签页自动重连或 localStorage 连续性；
- Runtime 原始状态或事件跨进程持久化；
- completed 工具回执或外部副作用 exactly-once；
- 问卷/授权、压缩、图片、队列/并行/Child 等其他真实 DOM 生命周期。

独立回退只需撤销 `isolated-host.cjs`、`infrastructure-selfcheck.cjs` 和 `smoke.spec.cjs` 中的 H4-5A 增量及本阶段事实源更新。无需迁移数据、修改生产协议或执行生产回退。
