# H4-8G detached `/parallel` 编辑授权完整刷新恢复

## 目标与阶段定位

H4-8G 为一个固定、合成、单 Session 场景补齐真实浏览器证据：主任务先通过唯一 `read_file` 进入第二个模型 Runtime，在主任务仍 active 时从真实 composer 提交一次 detached `/parallel` 编辑任务；background AgentRun 产生唯一 `propose_edit` 并等待授权，主任务随后先完成；当前、last-active Session 做一次完整页面刷新后，页面恢复同一 background AgentRun、authorization、diff 与操作入口，用户再通过真实 UI approve；编辑只应用一次，background final 以 detached 结果持久化。其后再提交一次普通前台 follow-up，实际上游模型上下文不含这条 detached 编辑链。

本阶段不是新增产品功能，也不是生产修复。实现差异只位于：

- `tests/e2e/h4/isolated_host.py`：增加 H4-8G 专属、只返回整数的完整消息编辑 artifact 计数；
- `tests/e2e/h4/smoke.spec.cjs`：增加固定 lifecycle、薄投影、十三项冻结哈希，以及 bundle/direct classic 两个共用入口。

`app.js`、`server.py`、AgentRun/Runtime API、授权协议、Session/JSONL 格式、持久化、安全边界和产品交互均未改变。H4-8G 证明的是既有产品链在严格限定窗口中的实际行为，不建立新的同步 API、恢复协议或 exactly-once 契约。

## 固定场景

场景固定为同一 Session、单标签页/actor、单 background job、单 proposal、approved 分支：

1. 通过真实 UI 启动主任务；固定假上游让第一轮产生唯一 `read_file`，第二轮保持在模型 final-delta gate；
2. 确认主 AgentRun 已进入第二次 `model_started`，第二个 Runtime 为当前 active Runtime，并观察真实前端 consumer 已附着；
3. 从真实 composer 提交一次 `/parallel`，background 作为独立顶层 AgentRun 产生唯一 `propose_edit`，进入 `waiting_authorization`；
4. 保持 background 等待授权，释放主任务 gate，使主 AgentRun 正常完成；background checkpoint、authorization、diff 与操作入口继续保留；
5. 在当前、last-active Session 执行一次完整 page reload，不切换 Session、不点击侧栏、不额外触发 `refreshSessions`；
6. reload 通过稳定 `clientRequestId` 重附同一个 background AgentRun，恢复同一 pending authorization、proposal、diff、checkpoint 与卡片；
7. 用户真实点击 approve 一次；同一 background Run 完成 authorization、apply、resume、第二轮模型与 detached final；
8. 再从真实 composer 提交一次普通无工具 follow-up，核对真正发往模型的上下文只含前台主线；
9. 终态再完整 reload 一次，核对 Run、Runtime、Session、DOM、文件和所有受控业务指标稳定。

主 `read_file`、background `propose_edit`/apply 与 follow-up 无工具请求分别计数，不能把它们笼统写成“工具执行为 0”。

## `/parallel` 前的真实 consumer fence

R059F 暴露过一种调度窗口：测试虽然已经看见主 AgentRun 第二次 `model_started` 和 active Runtime 身份，但真实前端 consumer 尚未附着时就提交 `/parallel`，background user 可能先占用 Session 消息位置。H4-8G 没有把这一偶然顺序写入基线，而是复用既有 `waitForFrontendRuntimeConsumer` 只读门禁：

- 目标严格是主任务第二个 Runtime；
- 只接受 lifecycle boundary 之后、同一 Runtime 身份的真实 `GET /api/runtime/runs/{id}`；
- cursor 必须是 numeric，`wait=25`，并且观察到 positive wait；
- 哈希只记录 target 匹配与 positive wait 两个布尔，不记录原始 Runtime ID、URL、端口、时间或候选次数。

该 fence 是测试对既有前端长轮询 consumer 的只读调度观测，不是 `sleep`、超时放宽、产品同步 API 或生产行为修改。它证明的是 consumer 已附着之后的固定顺序，不覆盖 consumer attach 之前的极短窗口，也不把该窗口提升为产品级排序承诺。

## 等待授权与主任务先完成

background AgentRun 首次进入等待态时精确为五事件：

```text
created → model_started → model_completed → tool_started → authorization_required
```

其状态为 `waiting_authorization`、cursor `5`，存在唯一 pending authorization、proposal、diff 与 waiting execution。background checkpoint 保存同一 job、`clientRequestId`、AgentRun、cursor、permission profile 与受控任务字段；根 Session 的前台 `authorizationRequest` 不被 background 请求替换。

释放主 gate 后，主 AgentRun 以九事件正常 completed；前台 checkpoint 清理，而 `backgroundRuns` 中唯一 waiting checkpoint 保持。主终态形成后，background AgentRun 的状态、事件、execution、authorization 和 checkpoint 投影与释放前精确相等，授权卡与 diff 仍可操作。因此固定 background 授权等待不会阻塞或终结主任务。

Session 与 DOM 的受控逻辑顺序保持主 final 在 detached background user/edit pair 之前；background 不取得主任务 completed-status ownership。这里冻结的是受控角色、顺序、身份和 DOM 投影，不宣称完整 Session JSON 或 HTML 字节稳定。

## 完整刷新、配置闸门与同一 Run 重附

等待态刷新严格限定为当前、last-active Session 的一次完整 page reload。测试不执行 Session 切换、侧栏/列表刷新、非 last-active Session 恢复或额外 `refreshSessions`。运行中 Session 切换等路径已有独立恢复缺口，本阶段没有修复，也不能从本证据推断其行为。

隔离环境在 reload 启动时会先读取 `/api/config`。为保证 background dispatcher 在重附前读取固定假上游而不误触真实网络，H4-8G 在同一 BrowserContext 路由栈上安装一次性、精确同源、空 query 的 `GET /api/config` gate：

- exact gate、request listener 与既有 context catch-all 各观察该请求 1 次；
- release 前只在页面恢复既有 fake base URL 与唯一 synthetic key，并精确核对；
- release 前 AgentRun create transport 增量为 0；
- gate 随后 `fallback` 给既有 context 安全/诊断 handler，真实响应为 2xx；
- `try/finally` 负责 release、等待 reload settlement、移除 listener 和 exact route。

测试没有 `fulfill`、`fetch`、改写 header/body，也没有重写 AgentRun create 或 `/resume` 请求。reattach 与 resume 的真实请求只在本地比较 fake URL、唯一 synthetic key、目标 Session/Run 和精确 key 集；证据与哈希只保存布尔，不输出 URL、Key、原始 ID 或请求体。

刷新会多产生一次 background AgentRun create **传输尝试**，但服务端通过同一 Session 和稳定 `clientRequestId` 返回既有 Run。因而必须区分：

| 事实 | 值 |
|---|---:|
| durable AgentRun 总数（终态） | 3 |
| AgentRun create transport 总数 | 4 |
| waiting reload create transport | 1 |
| waiting reload 新增 durable AgentRun | 0 |

四次 create transport 分别来自主任务、background 首次创建、waiting reload 重附与普通 follow-up；额外一次不是第四个 durable Run。刷新前后 background 的 job、Session、`clientRequestId`、AgentRun、authorization、cursor 与 checkpoint 保持相同。等待刷新期间 Runtime、chat、proposal、authorization、resume、apply、有效 write 与 backup 的业务增量全为 0，文件保持 initial。

## 批准、恢复与唯一文件副作用

reload 恢复后，用户只通过真实授权 UI 点击 approve 一次。授权与 resume transport 都精确指向同一个 background AgentRun，并各发生 1 次；resume 请求继续使用 fake URL 与唯一 synthetic key，响应为 2xx 且状态进入 model。

background 完整十二事件为：

```text
created → model_started → model_completed → tool_started
→ authorization_required → authorization_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

两个 background Runtime 的 cursor 为 `[4,3]`。固定副作用计数为：

| 事实 | 值 |
|---|---:|
| production authorization / resume | `1 / 1` |
| registered proposal delegation / execution | `1 / 1` |
| proposal / apply / effective write / backup | `1 / 1 / 1 / 1` |
| controlled unsafe delta | `0` |
| replayed | `false` |

全场景 registered delegation/execution 总量为 `2/2`：主 `read_file` 为 `1/1`，background `propose_edit` 为 `1/1`，普通 follow-up 为 `0/0`；三个 AgentRun 的事件数分别为主任务 `9`、background `12`、follow-up `4`。

文件只从 initial 变为 target 一次，唯一 backup 保存 initial 字节。这里的“一次”是固定隔离场景中的受控生产指标和耐久投影，不外推到操作系统 write syscall、任意失败窗口或通用 exactly-once。

background completed 后只追加一个 canonical detached final，background checkpoint 清理；不会额外投影一个未 detached 的模型 assistant，也不会产生双 final。主 AgentRun 在 background 完成前后保持自身身份和终态，background 没有污染或替换主 Run。

## Usage 只累计一次

H4-8G 通过阶段关系证明 usage 合并一次，而不冻结或宣称实际耗时：

- background 等待态 Session stats 等于已完成主 AgentRun usage，尚未提前计入 background；
- background AgentRun usage、detached final usage，以及终态 Session 相对等待态的 usage delta 语义相等；
- follow-up AgentRun usage 与 Session 在 background 终态之后的新增 delta 语义相等；
- usage equality 先统一到固定 `input/output/cache/cost/cacheWrite` 投影再比较，避免对象键插入顺序形成伪差异。

这些关系只证明本固定成功路径的 usage 合并一次，不证明其他 background 类型、失败恢复或跨进程路径的通用 usage exactly-once。

## 普通 follow-up 与编辑 artifact 隔离

background 完成后，测试从真实 composer 提交一次既有普通无工具 follow-up。终态为 3 个 durable AgentRun、5 个 Runtime、5 次 upstream chat；五个 Runtime cursor 为：

```text
[4,3,4,3,3]
```

follow-up 实际模型请求中的受控主线顺序为主 user、唯一 `read_file` tool call、对应 receipt、主 final、follow-up user；background user、编辑 tool receipt、detached final 和 detached 状态字段均不进入该上下文，`unclassifiedNonSystemCount=0`。

为避免只依赖 H4-7C 的旧 failure marker 分类，隔离宿主又对 `payload.messages` 的全部角色与完整嵌套 JSON 做一次 H4-8G 专属扫描，固定检查以下七类编辑 artifact：

```text
EDIT_AUTHORIZATION_APPROVE_USER
EDIT_AUTHORIZATION_STAGE
EDIT_AUTHORIZATION_APPROVE_FINAL
PROPOSE_EDIT_TOOL_CALL_ID
PROPOSE_EDIT_PATH
PROPOSE_EDIT_OLD_TEXT
PROPOSE_EDIT_NEW_TEXT
```

本场景 `detachedEditArtifactCount=0`。helper 只返回整数，不输出消息、正文、ID、路径或 diff；并且只有 host 已观察到 production edit proposal 时才给 follow-up context 增加该字段，因此 H4-7C 的零编辑路径保持原输出形状。这个门禁只扫描七个固定 marker，不是通用敏感信息、任意 detached 内容或所有未来编辑格式的泄漏扫描。

## 终态完整刷新与零业务重放

follow-up 完成后的终态 reload 保持三个 AgentRun、五个 Runtime、Session/DOM 顺序、detached 身份、usage、target 文件和 initial backup。AgentRun/Runtime 创建、upstream chat、authorization、resume、registered delegation/execution、proposal、apply、write、backup 与 unsafe 的受控业务增量全为 0。

“零业务重放”不表示零 HTTP、零 GET 或零网络请求。页面仍会执行正常配置、Session、AgentRun/Runtime snapshot 和资源读取；证据只排除新的模型、工具、授权、恢复和文件业务副作用。

## 十三项冻结语义哈希

bundle 与 direct classic 共用同一 lifecycle、投影、hash inputs 和 expected；十三项最终冻结值为：

| 投影 | SHA-256 |
|---|---|
| `preParallelFence` | `540ae88a41e13cf77f9913ffa5b7f4489dcc536cd5a5e9905abcad6752ce0937` |
| `waitingAgentProjection` | `ff426ad3e9ae36b9e379c0bfdfdfd5714b051d5a297eb173144dd16346807fff` |
| `waitingActiveDom` | `9abe49fc00c52d00e69b2384cc064fba456dfbd34aa11bc7f397b4504b371f9a` |
| `mainTerminalIsolation` | `8fe0ed85dd2c22ce19ca32a885ac13c945de697a657a8ad495b42c9bfc8ffc9a` |
| `waitingSessionProjection` | `572f009990f75aecf216df0acf4ddaecc2da366c80e413b77014ed938f7d0c33` |
| `waitingReloadLifecycle` | `63b8e49eb3859368e05d11a626f2a480ea0c48e7b871dfb2e6cf6b25306c0dee` |
| `decisionSubmissionProjection` | `f827f34e4647001078fa290a45e1ccb7c1ba1bc2ffb797f1728ddaf20d774d8c` |
| `backgroundTerminalAgentRuntime` | `a24f62f7ed7658581125e902877352fe76d5fba3c1ecd2fdf6340659d4f6eb36` |
| `backgroundTerminalSession` | `2677c782ad9882dd4be181859e6d8b7b0843d6794f7cc0952ef85cb8ad10f94b` |
| `backgroundTerminalDom` | `39e1428311504cabd0a8004d711809c9203859dfce8cebc631e9ebff3ed00325` |
| `followupRequestContext` | `cb728e9a97ebb86660b16c0089f79ae136847abf36b8f329780789bd94aee8f5` |
| `followupTerminal` | `ae54a71daf8cdab6fecfdcb06c579a887b17141504c6a9426541f00d30a3d864` |
| `terminalReloadLifecycle` | `ffad15908367bd4a8139e755ea7aa00ab208b90776e25cf96432ce9e08a9acad` |

哈希只包含受控 alias、枚举、计数、角色/事件/顺序、状态、usage 关系布尔与其他布尔因果。实际 usage 数值由独立断言校验，不进入冻结哈希。原始 Run/Session/authorization/proposal/tool ID、完整 URL/端口、Key/header/request body、时间、绝对路径、正文、diff、HTML 与完整错误均不进入哈希或脱敏 evidence。唯一固定相对路径 `fixture.txt` 只用于精确核对主 `read_file` 参数。

## 验证事实

- 相关十文件回归：`680 passed, 260 subtests passed, 1 warning in 34.74s`；唯一 warning 为既有损坏 TIFF/EXIF Pillow 负测。
- 邻接 H4：H4-7C、H4-8A、H4-8B、H4-8C approve/reject 与 H4-8F 的 bundle/direct classic 共 `12 passed (40.7s)`，1 worker、0 retry，旧冻结哈希未漂移。
- Harness replay：`17 fixtures / 124 events / 25 checkpoints / 25 checkpoint recoveries / 4 explicit recoveries`；suite hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。
- 完整 `tests` pytest：`1126 passed, 751 subtests passed, 3 warnings in 93.48s`；三条 warning 均为既有损坏 TIFF/EXIF Pillow 负测。
- H4 round 1：标准 `npm run test:h4:e2e` 先运行 infra，再以 1 worker、0 retry 完成 `67 passed (3.9m)`，67 条 cleanup 全部闭合。
- H4 round 2：独立 infra 通过后，专用 output 的 smoke 以 1 worker、0 retry 完成 `67 passed (4.4m)`，67 条 cleanup 全部闭合。
- 两轮中 A～G 受门禁哈希跨 runtime、跨轮保持；H4-8G 的 bundle/direct classic 十三项逐项一致。一个非冻结的动态 durable-record byte 计数跨轮不同，但其八项受门禁语义哈希一致，未作为漂移。
- `npm run check:frontend`、`npm run verify:frontend`、Node 语法、Python AST、`git diff --check` 均通过。Python AST 另报告既有 `server.py:4949` invalid escape `\C` SyntaxWarning；它不是 pytest 的三条 TIFF/EXIF warning。
- H4/isolated-host/Python/Chromium 相关进程、候选监听、`code-h4-e2e-*` 临时根、fixture、backup 与 H4 pyc 均为 0。两枚新增 Node 经只读命令行确认是共享 MCP stdio 服务、无监听，不是 H4 残留，未终止或清理。
- R059M 的 adjacent、round 1 默认 output 与 round 2 专用 output 各只含 passed `.last-run.json`。R059C～R059L 既有 ignored output 保持原文件、mtime 与哈希；九份 `%TEMP%` R059M 诊断日志仍保留且不进入 Git。

## 证明边界

H4-8G 只证明隔离 Chromium 中固定同 Session、单 background job、单 proposal、approved、主任务先完成、current/last-active Session 完整 reload、真实 UI approve、单次成功 apply 与后续普通 follow-up 的场景。它不证明：

- consumer attach 前极短窗口中的消息顺序；
- Session 切换、sidebar/list refresh、额外 `refreshSessions` 或非 last-active Session 恢复；
- 多 proposal、多 pending authorization、多 background job、多 `/parallel`、多标签页或并发 actor；
- reject、授权请求/响应丢失、durable decision 后响应丢失、重复 decision；
- resume、Session save、apply、write 或 backup 失败与重试；
- 进程崩溃、服务重启、跨进程恢复或 crash/write/backup window；
- 真实模型、外网、真实凭据、Firefox/WebKit、性能 SLA、主观视觉或可访问性；
- 通用后台授权恢复、通用 exactly-once，或“所有并行失败均隔离”。

## 兼容性、回退与阶段状态

本阶段没有生产代码、API、协议、Session/AgentRun/Runtime、JSONL schema、持久化、迁移、安全边界或交互变化。回退只需撤销 `isolated_host.py` 的 H4-8G artifact 计数、`smoke.spec.cjs` 的 H4-8G lifecycle/投影/哈希/两个入口，并移除本专题及对应日志/索引增量；不需要迁移或回写任何真实数据，也不应回退 H4-7C 或 H4-8C。

H4-8G 阶段至此完成。Harness 第一轮综合完成判定、完成线、TODO 与总览同步留给用户指定的新审批/开发会话作为唯一下一步；当前按用户要求暂停。本阶段提交不宣告“Harness 第一轮已经完成”，也不启动 H4-8H 或其他后续开发。
