# DSH Goal 模式调研分析

> 版本：v1.0 · 2026-08-14 07:27
>
> 历史快照声明：本文只描述 2026-08-14 当时的 `0.1.0-rc.6` 源码与 README 核对结果，不代表当前 DSH 版本或当前 Code 实现；引用本文结论前应按目标版本重新核对。文中的“实测设计”指源码/README 逐项核对，不表示完成了真实运行流程验证。
>
> 调研基线：DeepSeek Harness 本机部署随附包，四个包版本均为 `0.1.0-rc.6`：
> `@deepseek-ai/dsh-goal`、`@deepseek-ai/dsh-goal-round-driver`、`@deepseek-ai/dsh-tool-goal`、`@deepseek-ai/dsh-command-goal`
>
> 用途（2026-08-14）：为 Code Goal 功能实施提供对照依据。本文形成时**未修改 `docs/goal-mode-development-guide.md`**；本文只记录当时核对到的 DSH 设计，供历史对照与取舍。
>
> 来源：本机安装路径 `%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\` 下的四个包（lib 源码 + README.zh.md），逐行阅读源码并交叉核对 README。未验证内容在文中明确标注。

---

## 一、结论摘要

DSH 的 Goal 是一套"事件溯源状态 + 进程本地续行授权 + 面向模型窄工具 + 独立续跑驱动器"的四件套。其核心哲学可以概括为一句话：

> **持久层只存事实（phase / revision / rounds / 证据），"是否继续自动跑"是进程本地授权、默认关闭、只能由人类重新打开。**

对照 Code 的 `goal-mode-development-guide.md`，DSH 已落地的设计与该文档大部分决策同构，并且为文档第十四节列出的五个开放问题提供了现成的工程答案，其中最值得借鉴的三点是：

1. **resume 重新武装机制**：会话恢复 / fork 后目标持久 phase 仍在，但续行一律 disarm，必须由人类显式 resume 重新开启——比"服务重启后不自动续跑"更严格（连 fork 都不续）。
2. **blocked 的机械门槛 + 模型判断**：`blockedAfterConsecutiveRounds = 3` 作为硬下限，语义等价性由模型在 `blocked_reason` 中论证；人类直接授权可立即 block。
3. **工具权限三档分层**：create 可从人类请求推断意图；edit/pause/resume 必须直接人类轮次；complete/blocked 在自主 Goal Round 内也允许——不是一刀切。

DSH 不采用、也不需要与 Code 相同的是：四档权限档映射（DSH 的 goal 不携带权限档，权限属于执行环境）、`blocked` 作为 UI 状态（DSH 的 UI 同样只有三态投影，`blocked` 是持久 phase 而非 UI 状态）。

## 二、调研范围与方法

### 2.1 调研对象

| 包 | 版本 | 角色 | 调研深度 |
|---|---|---|---|
| `dsh-goal` | 0.1.0-rc.6 | 状态服务 `ctx.goals`（事件溯源 + CAS + 续行激活） | 源码全文（lib/index.js 827 行）+ README |
| `dsh-goal-round-driver` | 0.1.0-rc.6 | 同会话续跑驱动器（Round 预留/准入） | 源码全文（lib/index.js 363 行）+ README |
| `dsh-tool-goal` | 0.1.0-rc.6 | 模型工具 `get_goal`/`create_goal`/`update_goal` + 权限检查 | 源码全文（lib/index.js 372 行）+ README |
| `dsh-command-goal` | 0.1.0-rc.6 | 用户命令 `/goal`（人类入口） | README（源码未逐行读，见第十一节局限） |

### 2.2 验证方式

- 源码逐行阅读，交叉核对各包 README.zh.md；
- 状态机、转移表、权限判定均从源码直接摘录（附录 A 给出行号索引）；
- 未做真实运行验证（未启动 DSH 实测 Goal 流程），也未读 `invariant.js` 与 Typert 远程边界源码；这两点列为局限。

## 三、总体架构

### 3.1 四包职责

```
用户 ──(/goal 命令)──▶ dsh-command-goal ──┐
                                           ├──▶ dsh-goal（ctx.goals：唯一状态真源）
模型 ──(get/create/update_goal 工具)──▶ dsh-tool-goal ──┘          │
                                           ▲                         │ 会话日志 goal/change 事件
                     dsh-goal-round-driver │                         ▼
                     （idle 时自动排队下一 Round）◀────────── 持久会话事件流
```

- **`dsh-goal`**：纯状态域。所有变更经 `ctx.goals` 的动词（create/edit/pause/resume/complete/block/clear）写入会话日志的 `goal/change` 事件；除 `disarm()`（生命周期专用）外，每个动词都产生一个新 revision 并发出 `goal/changed` 通知。
- **`dsh-goal-round-driver`**：把"phase=active 且 activation=armed"的目标在 agent idle 时转换成连续的 Goal Round（保留的 `<goal_round>` 用户消息）。只消费公开 Agent/Session/Goal 服务，不碰持久化写入（block 除外——它通过 `ctx.goals.block` 报告 round-limit / queue-failed / prompt-rejected）。
- **`dsh-tool-goal`**：面向模型的三个窄工具，执行时做三层权限检查（见第六节）。纯状态变更，不负责调度。
- **`dsh-command-goal`**：人类 `/goal` 入口，确定性命令解析，不经模型轮次。

### 3.2 与 Code 现有组件的映射

| DSH 组件 | Code 现有对应物 | 差距 |
|---|---|---|
| `ctx.goals` 状态服务 | 无（Code 的 AgentRun 有状态但无独立 goal 域） | 需新建 |
| `goal/change` 事件（进 Session 日志） | Code 的 Session JSONL 事件流 | 需定义事件类型并扩展写入 |
| `goal` 投影（供 UI） | Code 的 run projection（H2 系列已建投影基础设施） | 复用投影机制 |
| Round 驱动器 | 无（AgentRun 一轮即终） | 需新建跨 AgentRun 编排 |
| `get_goal`/`create_goal`/`update_goal` 工具 | Code 的 `SERVER_TOOL_REGISTRY` | 需新增三个工具 + 权限检查 |
| `/goal` 命令 | Code 的斜杠命令解析（`/compact` 等已有） | 按既有命令平面扩展 |

## 四、持久数据模型

### 4.1 `goal/change` 事件（唯一持久真源）

每次变更向会话日志追加一条事件（`version: 1`）。快照型事件七字段：

```json
{
  "kind": "goal/change",
  "version": 1,
  "operation": "create | edit | pause | resume | complete | block",
  "goal": {
    "id": "goal-<uuid>",
    "revision": 1,
    "objective": "非空、已去首尾空白",
    "phase": "active | paused | blocked | complete",
    "maxGoalRounds": 256,
    "blockedReason": { "code": "lower-kebab-case", "message": "非空、已去首尾空白" }
  },
  "roundsStarted": 0,
  "createdAt": 1755165600000,
  "updatedAt": 1755165600000
}
```

`blockedReason` 仅在 `phase === "blocked"` 时存在（快照字段集合按 phase 严格校验）。清除是独立 tombstone：

```json
{
  "kind": "goal/change",
  "version": 1,
  "operation": "clear",
  "cleared": { "id": "goal-<uuid>", "revision": 8 },
  "clearedAt": 1755165600000
}
```

### 4.2 派生状态

```js
{
  goal,                // 上述快照（无 blockedReason 时省略该字段）
  roundsStarted,       // 已准入的 goal 来源 user/message 数
  createdAt, updatedAt,
  lastRef,             // 最近一次变更的 {id, revision}
  activation: "armed" | "disarmed"   // ← 进程本地，绝不持久化
}
```

**关键设计（源码确认）**：

- 每次 `agent/session-start` 事件、每次新建进程缓存，`activation` 一律置为 `disarmed`——即使回放发现持久 phase 是 `active`。所以**会话恢复 / fork 后目标还在，但自动续跑绝不会启动**。
- 只有人类授权的 `resume` 变更才把 activation 重新置为 `armed`；`sync()` 在消费到 `goal/change` 事件时，按事件 seq 匹配调用方预登记的 `pendingActivation`，不匹配一律回落到 `disarmed`（防止并发变更偷偷重新武装）。
- `activation` 在工具结果里是"实时观察值"，明确不构成回放权限依据。

### 4.3 投影

`goal` 投影（`applyGoalProjection`，stateVersion 4）是 last-wins 降级投影：非 `goal/change` 事件返回同一引用（不触发缓存失效），畸形变更被吞掉保持旧值；严格性由写入侧（GoalService 校验）和 `invariant` 兜底。UI 读这个投影；严格回放是另一条路径（fold，见第八节）。

## 五、状态机与转移规则

### 5.1 phase 集合与顶层不变量

- phase 只有四种：`active` / `paused` / `blocked` / `complete`（源码 `PHASES`）。
- 同一时间最多一个当前目标；**goal id 生成后不可变且全局不可复用**（`seenGoalIds` 集合，clear 后 id 仍被禁止复用）。
- 每次变更 revision 严格 +1；`createdAt` 与 `roundsStarted` 在非 create 变更中必须保持不变；`updatedAt` 单调不早于上一次（墙钟回拨时用 `max(now, 上次)` 钳制，源码 `nextMutationTime`）。

### 5.2 完整转移表（源码验证）

```
                     ┌──────────────┐
    create(无目标)───▶│    active    │◀────┐
    create(仅complete │              │     │ resume
    可替换)          └──┬──┬──┬──┬──┘     │ (active/paused/blocked→active)
                        │  │  │  │        │
                     pause block complete edit
                   (仅active)(仅active)(任意非complete)(任意phase)
                        ▼  ▼  ▼           │
                   ┌────────────────┐     │
                   │ paused /       │     │ edit 只改 objective/maxGoalRounds
                   │ blocked /      │     │ phase 与 blockedReason 不得改变
                   │ complete       │     │
                   └────────────────┘     │
                        │                 │
                     clear(任意phase)     │
                        ▼                 │
                   tombstone(revision+1)──┘
```

| 操作 | 前置条件（不满足即拒绝） | 效果 |
|---|---|---|
| `create` | 无当前目标 **或** 当前 phase==`complete`；revision 必须=1、phase=active、rounds=0、id 未被用过 | 创建 + armed |
| `edit` | 至少提供 objective / maxGoalRounds 之一；revision 匹配 | revision+1，phase/blockedReason 不变，activation 保留 |
| `pause` | 仅 `active` | → paused，disarmed |
| `resume` | `active`/`paused`/`blocked`；若已 active 且 armed 则拒绝冗余 resume；`roundsStarted < maxGoalRounds`（预算耗尽拒绝） | → active，**清除原 blockedReason**，armed |
| `complete` | 任意非 complete phase | → complete，disarmed |
| `block` | 仅 `active` | → blocked + blockedReason，disarmed |
| `clear` | 有当前目标 | tombstone（revision+1），disarmed，历史保留 |

### 5.3 稳定错误码

| 错误码 | 触发 |
|---|---|
| `GOAL_ALREADY_EXISTS` | create 时已有未完成目标 |
| `GOAL_STALE_REVISION` | CAS ref 与当前 revision 不匹配（报双方 id/revision） |
| `GOAL_NOT_FOUND` | 无当前目标 |
| `GOAL_INVALID_TRANSITION` | 非法 phase 迁移 / 冗余 resume / 预算耗尽 |
| `GOAL_AGENT_NOT_LIVE` | agent 不是注册表中的精确活跃实例 |
| `GOAL_INVALID_OBJECTIVE` / `GOAL_INVALID_MAX_ROUNDS` / `GOAL_INVALID_BLOCK_REASON` | 参数校验失败 |
| `GOAL_INVALID_EDIT` | edit 未提供任何替换字段 |

## 六、模型工具契约

### 6.1 三个工具

```ts
get_goal(): { goal: null } | { goal: Goal, activation: "armed"|"disarmed" }
// Goal = { id, revision, objective, phase, roundsStarted, maxGoalRounds, blockedReason? }

create_goal(objective: string, max_goal_rounds?: number): 同上
// 可从人类直接请求推断长期任务意图；非人类轮次与 subagent 在执行时被拒绝

update_goal(goal_id, revision, action,
            objective?, max_goal_rounds?, blocked_reason?): 同上
// action ∈ edit | pause | resume | complete | blocked
```

参数绑定规则（源码 `hasText`/`hasRoundCap`，严格 schema 空字符串/0 视为省略）：

- `objective` / `max_goal_rounds` **仅** `edit` 有效；其他 action 携带即报 `GOAL_TOOL_INVALID_UPDATE`；
- `blocked_reason` **仅** `blocked` 有效且必填；`complete` 携带即报错；
- `goal_id` 必须非空且无首尾空白，`revision` 必须正整数，否则 `GOAL_TOOL_INVALID_UPDATE`；
- 所有调用互斥执行（工具注册表保证同批调用顺序可见）。

### 6.2 执行时三层权限检查（全部强制）

```
第一层 身份（goalToolExecution）
  exec.agent 必须存在
  且 ctx.agents.get(agent.id) === agent      // 精确活跃实例，不认同名
  且 agent.status === "running"
  且 ctx.agents.currentInitiator() === agent  // 必须在自己的驱动器边界内
  且当前存在开放 turn（倒序扫到 turn/start 前不能有 turn/end，
     否则 GOAL_TOOL_DRIVER_REQUIRED）

第二层 开放轮次内调用（openTurn 已在第一层完成）

第三层 动作级权限
  create / edit / pause / resume  → requireDirectHuman()
  complete / blocked              → completionAuthority()
                                     = 直接人类 或 精确匹配的当前 Goal Round
```

**"直接人类"的定义（源码 `hasDirectHumanInput`）**：

- 调用 agent 必须是**运行时根**（`ctx.agents.roots()` 包含它）；持久 fork 谱系不降级已恢复的根，但活跃 subagent 所有权会降级；
- 当前 turn 内存在 `source.kind === "user"` 的 `user/message`；
- `Agent.followup()` / `steer()` 缺省 source 时会被分配 `user`——因此**非人类生产方（插件、调度器）必须显式传自己的 source**，否则就"继承"了用户权限（这是文档里的明确注意点）。

### 6.3 blocked 的机械门槛

```js
// 仅对自主 Goal Round 生效；人类直接授权可立即 block
if (action === "blocked" && authority.kind === "goal-round"
    && authority.goal.roundsStarted < blockedAfterConsecutiveRounds)   // 默认 3
  throw GOAL_TOOL_BLOCK_THRESHOLD
```

- 运行时只机械统计"已准入的互不重复 Round 数"，**障碍在语义上是否相同由模型判断**，并必须在 `blocked_reason` 中说明具体条件；
- 策略指引原文：`difficulty, uncertainty, or useful remaining work is not blocked`（困难、不确定、还有有用工作可做，都不算 blocked）；
- blocked 的持久 code 固定为 `"model-reported"`。

### 6.4 complete/blocked 的收尾

自主 Goal Round 报告 complete/blocked 后：

1. `exec.deferContext()` 注入一段 `<goal_complete>` / `<goal_blocked>` 收尾指令（目标原文回显 + 要求模型写面向用户的总结、**不得再调用工具**、如实说明未验证的细节）；
2. 通过 `concludeTurn()` 让物理轮次在该 step 后停止。

人类直接变更**不会**触发这种停止：模型可以确认变更，循环仍可接收并发的人类 steering。

### 6.5 系统提示词段落（原文，order 114）

```markdown
Use goal tools for one long-running completion objective in the current session. create_goal may infer goal intent from a direct human request in any language; do not create a goal for routine single-turn work. Call get_goal before update_goal and copy its exact goal_id and revision. After session resume or fork, an active goal is disarmed: when a human asks to continue or resume in any wording or language, use update_goal action resume to rearm it. Mark complete only when the objective is actually achieved. Mark blocked only after the same blocking condition persists for at least 3 consecutive goal rounds, and report that concrete condition in blocked_reason; difficulty, uncertainty, or useful remaining work is not blocked.
```

## 七、续跑驱动器（自动 Round 怎么发）

### 7.1 Round 生命周期

```
reserve → queued → claimed → admitted（进入 step 时 roundsStarted +1）
   │         │        │
   └─ discarded → cancelled →（下次 idle 时 pause goal）
```

1. **触发条件**（`readyToDrive`）：agent idle、无竞争排队消息（`competingQueued == false`）、目标 phase=active 且 activation=armed、`roundsStarted < maxGoalRounds`；
2. **持久性检查点**：排队前先 `ctx.sessions.flush()`；flush 失败或 `agent/error` → `disarm()`（绝不带着不确定的持久化续跑）；
3. **预留**：构造 `<goal_round>` 消息 + source `{kind:"goal", goalId, revision, round}`，`agent.followup()` 入 inbox；`state.attempt` 记录身份（goalId/revision/round/messageId/content）；
4. **准入闸门**：`agent/pre-step` 在调用下游监听器**前后各一次**校验 `validReservation`——fiber 未停、attempt 处于 claimed 且未 stale、内容完全一致（`isDeepStrictEqual`）、goal 仍 active+armed 且 revision 未变、`round == roundsStarted + 1`。任一失败 → reject + 把同批其他已领取消息放回 inbox + 重新触发驱动；**陈旧预留不消耗 Round 编号**；
5. **roundsStarted +1** 只发生在准入的 goal 来源 `user/message` 事件（`session/event` 监听，比对 messageId）。人类消息不消耗上限；
6. **取消语义**（`turn/end` / inbox discarded / cancel）：attempt 被丢弃 → 下次 idle 时 `pause` goal；`max-tokens` 结束 → disarm；aborted 且 attempt 已 claimed/admitted → 标记 cancelled 后同样 pause。

### 7.2 预留给模型的提示词（原文）

```markdown
<goal_round>
Objective: "..."\nRound: 3/256\n\nContinue working toward the objective in this same session. Treat the current workspace, tool results, and durable session state as authoritative; inspect them instead of assuming earlier narration is still current. Make concrete progress and verify the result. Before claiming completion, gather evidence that the whole objective is achieved, read the current goal, and mark it complete. If work remains, leave the goal active for the next round. Follow the configured goal-tool policy before reporting a blocker.
</goal_round>
```

注意两个设计点：目标文本用 `JSON.stringify` 引用（多行/形似标签的目标不会被误解析）；提示词**不是目标本身**，只是推进指令。

### 7.3 驱动器主动 block 的三个场景

| 场景 | code | 说明 |
|---|---|---|
| Round 预算耗尽（`roundsStarted >= maxGoalRounds`） | `round-limit` | 驱动器直接调 `ctx.goals.block` |
| 排队失败（followup 抛错且目标未变） | `queue-failed` | 同样直接 block |
| 预留消息在 pre-step 被下游拒绝 | `prompt-rejected` | block 并停止 |

### 7.4 卸载语义

teardown：全部 disarm → 标记 stale → 若 agent 在运行则以 `parent` cause 取消并 `whenIdle()` → 等待驱动器循环结算 → 清空状态。已准入的 goal 提示词可能在卸载开始前启动并消耗其 Round（文档承认的竞态），但 teardown 会取消请求并停用续行，不会再启动后续 Round。

## 八、一致性机制汇总

| 机制 | 实现 |
|---|---|
| Compare-and-set | 所有变更携带精确 `{id, revision}`，不匹配报 `GOAL_STALE_REVISION` |
| 严格回放 fold | `foldGoal`/`applyGoalEvent`：拒绝形状错误、revision 不连续、非法迁移、时间戳回退、Round 不连续；`dsh-goal/invariant` 在事件**入日志前**拦截（单独挂接时才启用） |
| 投影降级 | UI 投影 last-wins、畸形事件保持旧值；严格性由写入侧 + invariant 兜底，投影不阻断会话读取 |
| 单写入者 | 只有 GoalService 能 append `goal/change`；模型通过窄工具只能建议，无法覆盖整个对象 |
| 字段白名单 | 快照字段按 phase 严格校验（`decodeSnapshot` 用 key 排序比对）；blocked 只有 code+message 两字段 |
| 不变量 | 非 edit 不得改 objective/maxGoalRounds；edit 不得改 phase/blockedReason；clear 后 id 不复用；resume 清除 blockedReason |
| 凭据 | goal 事件不含凭据字段，受会话事件协议统一约束（agent_protocol 的同类设计 Code 已有） |

## 九、与 `goal-mode-development-guide.md` 的逐条对照

### 9.1 产品决策对照

| 文档决策 | DSH 实测 | 结论 |
|---|---|---|
| 顶层计划严格三态（pending/in_progress/completed） | 持久 phase 四态（active/paused/blocked/complete），UI 投影只有三态 | 方向一致；DSH 的 `blocked` 是持久 phase 不是 UI 状态，与文档 4.1"blocked 不投影为第四态"兼容 |
| 最小 UI，无编辑/暂停/恢复/清除按钮 | `/goal` 命令承担全部控制，UI 只读投影 | 一致 |
| 普通消息为主要控制面 | 文档 5 节意图表；DSH 用"直接人类轮次"判定 + 确定性 reducer 校验 | 一致；DSH 的"直接人类"判定是**可执行的**（roots + user source），比意图分类更硬 |
| 模型可建议、reducer 决定、用户确认 | 完全对应：窄工具 + CAS + requireDirectHuman | 一致 |
| 每步内部验收契约 + 证据分层 | DSH **未实现**（见 9.3） | Code 需自行设计 |
| 自动续跑 + 无进展保护 | Round 驱动器 + `blockedAfterConsecutiveRounds` | 一致，且给出了可执行参数 |
| 服务重启后不自动续跑 | 更严格：**任何 session-start / fork 都 disarm**，必须人类 resume | DSH 更严，建议 Code 采用 |
| 不可逆动作幂等 | DSH goal 域本身不涉及不可逆动作（权限属于执行环境） | 文档 9.2 的规则仍需 Code 自行实施 |

### 9.2 文档第十四节五个开放问题的答案

| 开放问题 | DSH 的落地答案 | 对 Code 的含义 |
|---|---|---|
| 14.1 存储：Session JSONL 扩展、独立日志还是组合 | **`goal/change` 事件直接进 Session 日志**（全量快照 + tombstone），另挂 `goal` 投影供 UI；无独立数据库 | Code 可选同方案：在 Session JSONL 事件流中加 goal 事件类型 + 投影 |
| 14.3 工具接口：通用更新 vs 窄接口 | **三个窄工具**（get/create/update），`update_goal` 必须回传 `goal_id + revision`（CAS），字段白名单 | 建议 Code 照此设计，不要给"更新整个 goal 对象"的工具 |
| 14.4 无进展分类、默认上限与可测试规则 | 不是检测器：**机械门槛 3 轮 + 模型论证 blocked_reason**；人类可立即 block；`round-limit` 预算耗尽自动 block | 默认值可取 3，并保留"人类直接授权可立即 block" |
| 14.5 自然语言意图分类置信门槛 | create 可从直接人类请求推断；edit/pause/resume 必须直接人类；complete/blocked 在自主轮内允许 | 三档权限是现成的、可测试的确定性规则 |
| 14.1 附加：revision/幂等/损坏恢复 | CAS + 严格回放 fold + 投影降级 + invariant；损坏时 goal 访问失败但会话读取不扩散 | Code 已有同类基础设施（H 系列影子校验），可对照 |

### 9.3 DSH 明确不做、Code 文档要求做的地方（差异清单）

1. **每步验收契约与证据分层**（文档 6 节）：DSH 的 goal 只有"一个整体 objective"，没有步骤级验收条件、证据列表、证据来源归属。DSH 的"证据"体现在模型按 `<goal_round>` 提示词自证 + 工具结果留在会话里，但**没有结构化验证**。Code 文档 6.2 的机器/Agent/人工证据分层是 Code 自己的增值设计，DSH 没有对应物。
2. **步骤计划模型**（文档 4 节 3~8 个步骤）：DSH 没有 steps 数组、current_step_id、步骤级状态。DSH 的 Goal 是单目标 + rounds 计数。
3. **暂停/恢复/修改的用户确认协议**（文档 5 节意图分类）：DSH 没有专门的确认流程，靠"直接人类轮次"这一硬判定 + 模型在轮内自然对话。
4. **budget 预算**（文档阶段 3）：DSH 只有 Round 数量上限，无 token/时间/货币预算。
5. **`/plan` 与 `/goal` 分工**：DSH 的 plan mode 是独立机制（`dsh-plan-mode`），与 goal 域无关；Code 文档 3.3 的分工是 Code 自己的产品决策。

## 十、对 Code 实施的建议

### 10.1 建议直接采用的 DSH 设计（低适配成本）

1. **`goal/change` 事件 + 全量快照 + tombstone**：与 Code 现有 Session JSONL 事件流天然兼容，复用 H2 投影基础设施。
2. **CAS 三件套**：`get_goal` 返回 `{id, revision}`，`update_goal` 必须原样回传；stale 拒绝。这与 Code 已有的 mtime 冲突检测（propose_edit）是同一思想。
3. **resume 重新武装**：Code 的 AgentRun 已在服务重启后等待前端重注凭据，goal 的"重启后 disarm、必须 resume"可以叠加在同一个"等待"语义上。
4. **blocked 门槛默认 3 + blocked_reason 必填 + `model-reported` code**：直接可测试。
5. **工具权限三档**：create（推断）/ edit·pause·resume（直接人类）/ complete·blocked（自主轮也允许）——注意 Code 需要自己的"直接人类"判定：对照现有 `source` 字段（`_normalize_session_source` 已有 codex/claude-code 来源）扩展 `user`/`goal` 来源判定。
6. **驱动器主动 block 三 code**（round-limit / queue-failed / prompt-rejected）：兜住自动续跑的失控路径。

### 10.2 需要 Code 自行设计的差异点

1. **步骤计划模型**：DSH 是单目标，Code 文档要求 3~8 步计划。建议在 goal 域内加 `steps`（只有顶层三态）与 `current_step_id`，但保持"事件全量快照"的写入方式不变。
2. **每步验收契约与证据分层**（文档 6.2）：机器证据（退出码/哈希/白名单）、Agent 报告（辅助）、用户 PASS（门禁）三层——DSH 无对应物，需要自定义事件类型（如 `goal/evidence`）与 reducer 判定。
3. **与四档权限档的映射**：DSH 的 goal 不携带权限档；Code 必须定义"Goal 自动续跑的 AgentRun 继承发起 run 的权限档"，并规定 `自动` 档以外的 Goal 续跑需要新授权（文档第 10 节只写了"不扩大权限"，未写映射，建议在实施方案中补死）。
4. **意图分类 → 确定性 reducer**：Code 文档 5 节把意图判定交给模型提议 + reducer 确定性校验；DSH 用 source 硬判定。Code 可以结合：消息仍走既有 AgentRun 流程，goal 变更只认 source + CAS。

### 10.3 建议的 MVP 范围调整（对照文档阶段 1）

文档阶段 1 的"建议范围"与 DSH 已证实可行的最小闭环基本一致，可增补：

- 加入"**resume 重新武装**"作为 MVP 必做项（文档未显式列出，但 9.1 节"服务重启后"隐含；DSH 证明它是最小可行中的关键）；
- 加入"**驱动器主动 block 三场景**"（round-limit 至少要有，否则预算耗尽时模型不会自动停止）；
- "机器证据与用户 PASS 门禁"保留，但注意 DSH 没有现成答案，需要自定义证据事件与 reducer 判定——这部分建议按文档 6.2 单独设计并拆独立提交。

## 十一、已知局限与本调研未覆盖

1. **版本漂移**：调研基线为 `0.1.0-rc.6`（本机随部署分发）；DSH 升级后本结论可能过时，实施前应重新核对。
2. **未读源码**：`dsh-command-goal` 仅读 README（`/goal` 六种输入语义已记录，但未逐行核对命令分发实现）；`dsh-goal/invariant.js`、Typert 远程边界（`typert.host.js`）未读。
3. **未做运行验证**：未实际启动 DSH 走一遍"创建 → 多轮续跑 → 刷新 → 服务重启 → resume"；文档中关于 `activation` 跨进程行为的结论来自源码与 README 的交叉核对，不是实测。
4. **未覆盖相邻机制**：`dsh-plan-mode`（计划模式）、compaction 对 `<goal_round>` 保留消息的遮蔽行为、subagent 在 goal 轮内委派的权限继承，均未展开。

## 附录 A：源码位置索引（本机）

```
%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\dsh-goal\lib\index.js
  PHASES / SNAPSHOT_OPERATIONS          : L40-45 / L32-39
  decodeSnapshot（按 phase 严格校验字段） : L85-101
  decodeGoalChange（信封+版本+tombstone）: L117-160
  applyGoalChange / validateSnapshotTransition : L229-258 / L176-212
  applyGoalEvent（Round 准入推进）        : L264-279
  foldGoal（严格回放）                    : L285-295
  applyGoalProjection（UI 投影，last-wins）: L376-391
  GoalService.create/edit/pause/resume/complete/block/clear : L566-680
  assertLive / expectCurrent / sync / commit : L682-794
  view（detached 视图 + activation）      : L796-810

%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\dsh-tool-goal\lib\index.js
  goalToolExecution（身份三层）           : L30-38
  hasDirectHumanInput / requireDirectHuman : L44-60
  completionAuthority / isMatchingGoalRound : L49-75
  update_goal execute（参数绑定+权限+门槛）: L329-367
  blocked 机械门槛                        : L352
  renderWrapupContext（收尾指令）         : L86-93
  guidance（系统提示词段落，order 114）    : L189-191 / L253-257

%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\dsh-goal-round-driver\lib\index.js
  renderGoalRoundPrompt（<goal_round> 原文）: L11-18
  readyToDrive / drive（检查点+预留）      : L79-164
  validReservation（pre-step 前后双检查）  : L276-280 / L281-339
  agent/status idle 取消后 pause          : L216-233
  驱动器主动 block（round-limit 等）       : L125-131 / L156-163 / L319-322
  teardown（disarm+cancel+等待停稳）       : L341-359

%USERPROFILE%\.dsh\profiles\node_modules\@deepseek-ai\dsh-command-goal\README.zh.md
  /goal 六种输入语义（/goal、/goal <objective>、edit、pause、resume、clear）: 全文
```

## 附录 B：已核对的关键事实清单

- [x] phase 四态、操作七种（含 clear tombstone）
- [x] create 仅可替换 complete 目标；goal id 不可复用
- [x] edit 不得改 phase/blockedReason；resume 清除 blockedReason
- [x] activation 不持久化；session-start/fork 一律 disarm
- [x] resume 预算耗尽拒绝（GOAL_INVALID_TRANSITION）
- [x] 工具三层权限：精确活跃实例 + 运行中 + 当前 initiator + 开放 turn
- [x] create/edit/pause/resume 需要直接人类；complete/blocked 接受精确 Goal Round
- [x] blocked 机械门槛默认 3，仅对 goal-round 权限生效
- [x] Round 预留/准入生命周期与 roundsStarted 推进条件
- [x] 驱动器主动 block：round-limit / queue-failed / prompt-rejected
- [x] 系统提示词段落与 `<goal_round>` 提示词原文
- [ ] （未验证）command-goal 命令分发实现源码
- [ ] （未验证）真实运行行为与跨进程恢复实测
