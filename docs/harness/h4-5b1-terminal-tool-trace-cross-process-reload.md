# H4-5B1 含已完成工具轨迹的终态 AgentRun 跨进程重载与零重执行

## 1. 阶段结论

H4-5B1 在 H4-5A 已建立的真实 generation A→B 进程边界上，新增一条含单次受限 `read_file("fixture.txt")` 的终态 AgentRun 浏览器证据。进程 A 完成两轮模型交互、一次只读工具执行和最终持久化后完全退出；进程 B 以新 PID、新随机 loopback 端口和新 origin 从同一受控 root/data/project/home 启动，通过生产 Session 列表与可见 UI 打开同一 Session，并从磁盘加载同一 completed AgentRun。

进程 B 中 AgentRun POST、Runtime POST、上游 chat 和工具执行四项增量均为 0；旧两轮 Runtime GET 均返回 404，没有创建替代 Runtime。AgentRun 耐久事件、工具执行结果、Session JSONL 和 DOM 投影在 A/B 间保持一致且唯一。因此，本阶段直接证明的是“含已完成工具轨迹的终态 AgentRun 跨进程重载且 B 不重执行工具”，不是 active worker 在重启后消费 completed receipt，也不是任意工具副作用 exactly-once。

本阶段没有修改生产代码、`server.py`、AgentRun/Runtime/Session 协议、JSONL 格式或持久化实现。

## 2. 进程、请求与身份闭合

generation A：

- AgentRun POST 1、Runtime POST 0、上游 chat 2、工具执行 1；
- 唯一工具为受控 `read_file("fixture.txt")`，唯一 tool call、execution、outcome/result 均为 completed；
- AgentRun 状态为 `completed`，`nextCursor=9`，耐久记录 `nextSeq=10`，`pendingToolCalls` 为空，terminal 事件唯一；
- 九事件顺序固定为 `created → model_started → model_completed → tool_started → tool_completed → model_pending → model_started → model_completed → completed`；
- 第一轮 `model_started.runtimeRunId` 对应阶段说明 `H4_TOOL_STAGE` 与 Runtime cursor 4；第二轮对应最终回答 `H4_TOOL_FINAL` 与 Runtime cursor 3，不能只按 cursor 排序替代身份绑定。

generation B：

- 新 PID、新随机端口和新 origin，复用同一受控持久化根；A 子进程退出且两端口关闭后 B 才 ready；
- AgentRun POST 0、Runtime POST 0、上游 chat 0、工具执行 0；
- 读取与 A 相同的 AgentRun、实际 `clientRequestId`、toolCallId、completed 工具 execution/result、九事件投影与终态；
- 两个旧 Runtime 按各自 runtimeRunId 分别返回 404，不创建替代 Runtime；
- Session role/content、稳定工具 meta 配对与最终 DOM 语义均与 A 相同。

随机 AgentRun、Runtime 和 toolCall ID 只比较同一场景 A/B 一致性，不冻结为跨机器字面基线；含随机 ID/时间的原始耐久记录字节也只做 A/B 相等检查。

## 3. Session 与 DOM 契约

Session JSONL 的角色链固定为：

`user → assistant → tool-call → tool-result → assistant`

- `tool-call` 与 `tool-result` 各一条，两者 `meta.toolCallId` 指向 AgentRun 中同一唯一 toolCallId；生产消息提供的 `meta.agentRunId` 同样指向该 AgentRun；
- `tool-call` 声明 `read_file("fixture.txt")`；`tool-result` 只包含一份受控合成文件内容；
- user、阶段说明和最终回答各唯一，Session `runStateKeys` 为空。

DOM 中 `article.msg.assistant` 总数为 3，精确分为普通 assistant 2 个和 `tool-process` 1 个。可见语义节点依次为 user、阶段说明、工具动作、工具结果、最终回答，各出现一次且顺序不变。工具投影不被误称为普通 assistant，B 中没有 active banner、停止入口或重复 assistant/tool。

## 4. 固定语义哈希

以下 SHA-256 只覆盖脱敏、确定、无随机 ID/时间的语义投影：

- 工具结果：`1895281c988e7a243d395e51f6d73137142dd155dd6e23e43bec4948d9fa691c`
- 工具 execution 投影：`1783025dc756f6fbb2f18544210aa491b4ae1535d02595e3527093ad0a15e9d9`
- 九事件规范投影：`85dfc1ee8f8e43ef6d87fd6ea59bd289fd15830d5f729f5729266033373fda1e`
- 耐久记录语义投影：`b1c30c051cd9b640f4efa72784d1dc7756042e2422d6f1facb82dfb2b28e6122`
- Session role/content：`ecfbdadd2377ffc0f7c897b024dbd9aee7091c0375a3a48befe75c6a461c3a9a`
- Session 工具 meta 配对：`587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9`
- DOM 语义：`37d1870e896058e5f001c491a241353faa230e5b0a6fca9d487f8cf8bd058e91`
- 最终结果：`e40fb4ba752c3fe25f985c5aa78152ee6ce0166330aa57ca7d67e8a68e24bdef`

## 5. H4 控制 stdout 隔离边界

本阶段同时移除了一个已确认不安全的测试基础设施共享 stdout 边界：隔离 Python host 在导入生产 `server.py` 后定义 H4 专用 `CodeHandler` 子类，只覆盖 `log_message()` 并直接返回，使生产 CodeHandler 访问日志不再与 stdin/stdout JSONL 控制响应共用 stdout。业务处理函数、生产 `server.py`、FakeUpstreamHandler、Node parser、5 秒命令上限、ack 顺序和控制协议均未改变。

infra selfcheck 增加源码边界和有界运行时压力：每轮并发 8 个真实 loopback `GET /api/ping` 与 8 个 `metrics` 控制命令，每个 Promise 一一收敛，pending、子进程、端口与临时根归零；最终正式自检连续 5 轮分别约 6.11、6.17、6.19、6.26、6.42 秒通过，未使用 retry、sleep 或放宽超时。

这只能表述为“移除已确认的不安全共享 stdout 边界”。历史 `release-model` 控制响应超时的唯一根因仍未闭合；当前证据不能排除 Windows pipe/readline、Node event loop 或 pending 竞态，也不应把后续稳定通过描述成已唯一定位或修复该历史超时。

## 6. 验证基线

最终测试文件形态下：

- plain-text 定向：`1 passed`；
- H4-5B1 定向：`1 passed`，九事件、Runtime 4/3 cursor、Session/DOM 与八个语义哈希全部闭合；
- 连续两轮标准 `npm run test:h4:e2e`：均为 infra 通过、`13 passed`、`retries=0`，完整命令分别 48.05/48.00 秒；
- H3-2C2：`5 passed, 20 subtests passed`；
- AgentRun 工具回执恢复定向：`6 passed`；
- 前端模块与 P0：`199 passed`；
- 完整 Python 回归：`1113 passed, 739 subtests passed`，89.53 秒；
- `npm run check:frontend`、Node/Python 语法和 `git diff --check` 通过；
- 验证后 H4 子进程、两代端口、临时根、Playwright output 和暂存区归零。

收口冻结文件 SHA-256：

- `tests/e2e/h4/smoke.spec.cjs`：`67e3d0889765e9a1a5a04aea66ca723eba24cbc9685cc1806044b9d5488c1c52`
- `tests/e2e/h4/isolated_host.py`：`ad7e0884ebf79df447a7808c70c1b72bb01b80c54fc6a974e747f740b465833a`
- `tests/e2e/h4/infrastructure-selfcheck.cjs`：`d5b83b27a561e78a95bbeb618821aa58c2b0b83a592dd145fd05c2b5756ea069`
- 未修改的 `tests/e2e/h4/isolated-host.cjs`：`10afb7586451bf3b6c978d9befa5c443fb05237045ee2009e1808eeb966b501d`
- 未修改的 `server.py`：`5e0e5d4cb24680810c5efb46657fe317dadc8aea8f84d66425d219079640d738`

## 7. 完成边界与回退

H4-5B1 只证明 terminal 工具轨迹跨进程重载与进程 B 零重执行。它不证明：

- active worker 在重启后消费已完成 receipt；
- 工具外部副作用 exactly-once，尤其写入、命令、删除或授权工具；
- Runtime 原始状态或事件跨进程持久化；
- 非终态 AgentRun 自动恢复、部分正文保留或真实进程崩溃恢复；
- 问卷/授权、压缩、图片、队列/并行/Child 等其他真实 DOM 生命周期。

真正的 active receipt consumption 仍需产品决策：必须先明确 explicit/auto resume 语义以及是否允许重启后产生新的模型请求，再单独审批；不得由本阶段的 B 零执行推定已经完成。

独立回退只需撤销 `isolated_host.py`、`infrastructure-selfcheck.cjs` 和 `smoke.spec.cjs` 的本阶段测试侧增量及本次事实源更新，不涉及数据迁移、协议回滚或生产部署回退。
