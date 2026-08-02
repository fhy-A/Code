# Harness H2-1 Run 投影契约与纯函数边界

> 后续状态：H2-2 已在开发默认、正式关闭的独立开关下接入前台、恢复、队列和后台 AgentRun 只读影子计算，旧投影继续作为唯一可见实现。当前边界见 [`h2-2-frontend-shadow-projection.md`](h2-2-frontend-shadow-projection.md)。以下内容保留 H2-1 完成时的阶段事实。

完成时间：2026-08-03 01:00（Asia/Shanghai）

阶段性质：新增纯 reducer、规范 View Model 与离线比较契约，不接入现有事件轮询或 UI 投影

## 1. 阶段目标

H2-1 在 H1 版本化事件契约之上，先冻结新旧投影可以稳定比较的字段和纯函数边界，避免后续影子计算直接依赖 DOM、会话消息副作用或调用方的隐式时钟。

本阶段只建立以下能力：

1. 规范事件与显式快照事实进入同一个纯 reducer；
2. reducer 状态可以 JSON 序列化，并能从检查点继续重放；
3. 规范 View Model 不包含模型正文、思考正文、工具参数、工具结果、diff 或错误原文；
4. 新旧投影的首批比较字段形成固定契约；
5. 默认 bundle 和经典回退均装载该能力，但现有 `projectAgentEvent()` 不调用它。

## 2. 为什么输入同时包含事件和快照

H0 已确认当前实现并非所有状态都由耐久事件直接投影：

- 模型轮和工具记录主要由事件驱动；
- 等待授权、等待问卷和运行终态同时依赖服务端快照；
- 前端计时包含本地接力值，不能从事件时间单独无损恢复。

因此 reducer 的规范输入显式分为：

```js
{ kind: "event", event: normalizedEvent }
{ kind: "snapshot", snapshot: explicitSnapshotFacts }
```

调用方必须先经过 H1 事件适配边界；H2 reducer 不重复猜测协议版本。快照只补充状态、轮次、工具摘要、待处理事项和计时观察值，不会把会话消息或完整服务端响应复制进领域状态。

## 3. 纯 reducer 边界

事实源：`src/agent/run-reducer.js`

公开能力：

| 接口 | 作用 |
| --- | --- |
| `createRunProjectionState()` | 从空状态或显式快照事实创建 schema v1 状态 |
| `reduceRunProjectionEvent()` | 归约一个规范事件 |
| `applyRunProjectionSnapshot()` | 合并一次显式快照观察 |
| `reduceRunProjectionInput()` | 只接受 `event` / `snapshot` 两类规范输入 |
| `reduceRunProjectionInputs()` | 顺序重放一组输入 |

状态只包含：Run 状态与阶段、事件游标、模型轮摘要、按 `toolCallId` 去重的工具摘要、单一待处理事项、压缩摘要、显式计时事实、结构化时间线和诊断代码。

以下数据不会进入 reducer：模型正文、思考正文、工具参数、工具结果、命令输出、文件内容、diff、错误原文、Key、Authorization 或 Cookie。

### 3.1 确定性与幂等

- reducer 不访问 DOM、网络、文件、存储或系统当前时间；
- 相同状态和输入产生相同结果；
- 已处理序号再次投递直接返回原状态对象；
- 序号缺口和未知未来事件只增加代码级诊断，仍推进游标；
- 终态之后的不同状态事件不会令 Run 回流，只记录 `illegal_terminal_transition`；
- 状态为普通 JSON 对象，可在任意检查点序列化后继续重放。

## 4. View Model 与比较契约

事实源：`src/ui/run-view-model.js`

规范 View Model schema 版本为 1。首批新旧投影比较字段固定为：

| 字段 | 定义 |
| --- | --- |
| `status` | 当前 8 类 AgentRun 状态之一 |
| `terminalStatus` | 非终态为空；终态为 `completed / failed / cancelled` |
| `modelRoundCount` | 已观察快照轮数与事件轮次中的最大值 |
| `toolCount` | 按非空 `toolCallId` 去重后的工具执行数，不按开始/完成事件重复计数 |
| `pendingKind` | 空、`authorization`、`user-input` 或 `credentials` |
| `elapsedMs` | 使用显式观察值或调用方提供的参考时间计算，绝不读取 `Date.now()` |
| `timeline` | 每个耐久事件的 `seq/type/category/status/refId`，不包含原始载荷 |

`createRunProjectionComparison()` 只输出上述字段。H2-2 的影子比较必须在同一个快照边界、同一个显式计时参考点采样，不能把两次不同墙钟读取造成的毫秒差异记为投影错误。

## 5. 计时规则

计时不再由纯层隐式读取全局时钟：

1. 若调用方提供 `elapsedMs + elapsedObservedAt`，活动 Run 只在同时传入 `referenceTime` 时继续累计；
2. 终态使用显式 `completedAt / updatedAt` 收口；
3. 没有显式累计值时，才使用 `startedAt` 与显式参考点的差；
4. 时间缺失或非法时安全返回 0。

这条边界用于防止刷新后计时停住、回退、跨任务串联或测试依赖真实等待。

## 6. 兼容、接入与回退

- `src/frontend-entry.js` 在 `agent-runtime.js` 和 `app.js` 前装载两个纯模块；经典回退清单同步更新；
- 现有事件适配、`projectAgentEvent()`、会话消息、工具组、状态栏和授权/问卷交互完全不变；
- AgentRun、会话 JSONL、工具协议和服务端接口没有新增字段或迁移；
- 正式实例的事件 v1 默认值仍保持原决定，本阶段不改变任何开发/正式开关；
- 删除两个纯模块、入口引用及对应测试/清单即可完整回退，不影响现有持久数据。

## 7. 自动验证

- H2-1、H0 夹具与前端模块定向：`169 passed, 21 subtests passed`；
- H2-1、Harness、协议与 Agent 运行时定向：`115 passed, 212 subtests passed`；
- 完整回归：`961 passed, 442 subtests passed in 89.29s`；
- `npm run check:frontend` 通过默认 bundle、经典回退、构建新鲜度和 JavaScript 语法检查。

15 条 H0 合成轨迹的全部检查点状态、终态和事件时间线均与冻结基线一致；单工具和多工具轨迹分别得到 1 和 2 个唯一工具执行。检查点 JSON 往返后继续重放与从头重放得到相同比较快照。

## 8. 下一阶段

H2-2 才接入只读影子计算：

1. 在现有事件与快照边界旁同步喂给新 reducer，但不允许其写旧状态；
2. 为旧投影建立只读比较适配器，不从 DOM 文案反向解析领域状态；
3. 在同一显式计时参考点比较 H2-1 的七类字段；
4. 诊断仅保留脱敏、有限、内存级代码与计数；
5. 提供开发默认、正式关闭的独立开关，关闭后完全不执行新投影。

在 H2-2 观察到关键轨迹零差异前，不让新 View Model 接管任何用户可见界面。
