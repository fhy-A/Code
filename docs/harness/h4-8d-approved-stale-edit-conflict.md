# H4-8D 批准后陈旧编辑冲突保护

## 目标与阶段性质

H4-8D 为生产已有 stale-edit 冲突保护补齐真实浏览器证据：页面在固定 `propose_edit` 等待授权时完整刷新，随后测试控制面把同一固定文件改成第三方内容；用户仍通过真实授权 UI 批准，生产 `apply_edit` 检测到陈旧 proposal，保留第三方内容，并让同一 AgentRun 继续到正常终态。终态完整刷新后，身份、Session、DOM 和文件状态保持一致，业务链不发生重放。

本阶段不是生产修复。它没有修改生产代码、API、authorization 协议、AgentRun/Runtime 协议、Session JSONL 格式或持久化结构，也没有定义新的冲突交互。生产冲突行为、失败结果投影和既有 UI 状态均保持原样；H4-8D 只新增隔离宿主、自检和浏览器测试证据。

本专题按 [`Harness 第一轮完成线`](harness-round-1-completion-line.md) 收口其中的 H4-8D 必选项；它不替代该完成线中的问卷队列、授权失败安全重试、`/parallel` 审计或最终整体验收门禁。

## 固定场景与受控第三方转换

场景只操作每条用例独立隔离项目根内的固定相对路径 `h4-propose-edit-fixture.txt`，并只生成一份固定 proposal：

- initial SHA-256：`f12af1cc9275e5511341e977ac8ad5b13050b8eb8951b4a78555018cdbcaebe3`；
- proposal target SHA-256：`26ed22af144d40ac7a02a4a6087bbfa8bcb2024782e90fdac3ed6cb2abbbf3ef`；
- third-party SHA-256：`3ca2970e23df18316faba0c55fde5881e36d215d02499ee36e3e257113ebe931`。

模型首轮只通过生产 `propose_edit` 生成建议，不写文件。等待授权的完整刷新恢复同一 AgentRun、authorization、proposal、Session diff 和 DOM 授权面板，文件仍为 initial SHA。

刷新完成后，测试控制面执行唯一一次固定转换，把 initial 内容改成内置 third-party 内容。该命令不接收路径、正文、哈希或长度 payload；宿主在锁内先核对固定路径、initial SHA、唯一 proposal 已生成、production apply/write/backup 均为 0 且转换时间线为空，然后才写入固定的 28 字节内容并回读核对 SHA。测试控制转换计数与生产工具计数严格分离：

| 观察层 | 计数 |
|---|---:|
| 测试控制转换 attempt / write / rejection | 1 / 1 / 0 |
| production proposal delegation / execution | 1 / 1 |
| production apply invocation | 1 |
| production effective write / backup | 0 / 0 |

基础设施自检另外证明：proposal 生成前调用以及 exact-key 门禁覆盖的额外 payload 都在各自测试控制写入前拒绝；固定负例包含 path、body、target SHA、expected-before SHA 与 byte length 字段。唯一合法转换后文件保持 third-party SHA，随后重复调用被拒且不发生第二次写。该控制命令不调用 registered tool、production propose/apply、`write_file`、`delete_file` 或 `run_command` 入口，且自检中的 production callback 增量全部为 0。

## 批准决策、原始冲突结果与投影语义

用户通过真实 UI 只批准一次。授权决策的耐久事实是 `approved`；authorization POST 与 resume POST 各 1 次。生产 apply 被调用一次，并以现有 stale-edit 契约返回失败结果。受控投影对原始 result 严格核对：

| 字段 | 冻结语义 |
|---|---|
| `ok` | `false` |
| `action` | `apply_edit` |
| `conflict` | `true` |
| `applied` | `false` |
| `currentMtime` | 存在、为整数且大于 0；具体值不冻结 |
| `error` | 非空；完整文本不进入原始结果哈希 |
| `path` / `proposalId` | 分别匹配固定相对路径和唯一受控 proposal |
| `rejected` / `replayed` / `backupPath` | 字段缺失 |

对应 durable tool execution 的状态为 `completed`、outcome 为 `failed`；这描述的是批准后的工具应用冲突，不表示用户拒绝，也不使父 AgentRun 失败。第二轮模型仍收到唯一冲突回执并产生唯一固定 final，父 AgentRun 最终为 `completed`。

当前前端和 Session 归一投影中的 `rejected=true`、DOM 的 `is-rejected` 只表示“批准后冲突、编辑未应用”的既有失败投影。它们不能被解释为用户选择了 reject；真实用户 decision 仍由 authorization 元数据和原始 result 共同证明为 approved。

## 生命周期、刷新与可见冲突原因

完整生命周期的公共计数为：

| 观察层 | 计数 |
|---|---:|
| AgentRun 总数 / 浏览器 AgentRun POST | 1 / 1 |
| Runtime 总数 / 浏览器 Runtime POST | 2 / 0 |
| 上游 chat | 2 |
| authorization POST / resume POST | 1 / 1 |
| registered proposal delegation / execution | 1 / 1 |
| production apply / write / backup | 1 / 0 / 0 |

AgentRun 的 12 个连续事件严格为：

```text
created → model_started → model_completed → tool_started
→ authorization_required → authorization_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

其中 `waiting_credentials` 是既有恢复链事件名，不表示本场景使用真实凭据。两个 Runtime 的实测事件 cursor 为 `[4, 3]`。终态 Session 保持五条逻辑消息：

```text
user → assistant tool-owner → propose_edit tool-call
→ server-managed tool-result / edit suggestion → assistant final
```

等待态完整刷新保持同一 AgentRun、Runtime、authorization、proposal、Session diff 和 DOM；AgentRun/Runtime 写入、chat、authorization/resume、proposal/apply/write/backup 及测试控制转换增量均为 0。批准后，文件在 apply 前、冲突后、终态及终态完整刷新后都保持 third-party SHA，且始终不等于 proposal target SHA。

终态完整刷新继续保持同一 AgentRun、两个 Runtime、Session、冲突 result 与 DOM；AgentRun/Runtime 写入、chat、authorization/resume、proposal/apply/write/backup 和测试控制转换增量再次全部为 0。这里的“零业务重放”不表示刷新零网络请求：页面恢复所需的正常 GET/读取请求允许发生，门禁针对模型、授权、恢复、工具执行和文件副作用。

冲突原因并非自动展示，也没有专属冲突卡。测试先真实展开 terminal trace，再依次展开对应 `propose_edit` stage 和唯一 result item，随后证明结果区域与 `<pre>` 实际可见，并核对文案 `File modified by another session, please re-read.` 在该可见结果中精确出现一次。首次终态和终态完整刷新后都重复同一真实展开与可见性断言；断言完成后再按相反顺序折叠并证明结果重新隐藏。

## 文件保持与安全边界

测试控制写将文件从 initial SHA 转为 third-party SHA 恰好一次。生产 apply invocation 为 1，但 baseHash/mtime 联合校验在 backup 和有效写入之前终止，所以 production effective write 与 backup 均为 0，第三方内容不会被 proposal target 覆盖。

该计数是隔离宿主观察到的生产逻辑调用与副作用，不宣称操作系统层 exactly-once，也不把测试控制写伪装成生产写。隔离宿主仍保持 H4-8C 的固定 `propose_edit`、路径、字节、proposalId 与 base/new hash 门禁；任意 `write_file`、`delete_file` 和 `run_command` 继续硬拒绝。所有文件状态位于用例自己的临时隔离根，并由逐例 cleanup 移除。

## 冻结语义哈希

H4-8D 的 bundle 与 direct classic 对以下十项逐项相等，并在连续两轮标准 H4 中保持不变：

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3` |
| `waitingSnapshot` | `9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2` |
| `waitingDom` | `880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618` |
| `thirdPartyTransitionProjection` | `07a021c9dedf08a455140666ebc27a063eb61d996fb71b8ead63b358dea10b1f` |
| `conflictSubmissionProjection` | `6903528a33064bdbd1204523546ff9a4144083782e28452b9c7b9ee1a6948ac8` |
| `runtimeProjection` | `b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540` |
| `sessionRoleContent` | `f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0` |
| `sessionAuthorizationMeta` | `b8b0df63df027b536446ed665706b7e87ac84e6e304c3fcebdbcbb444137240d` |
| `terminalDom` | `b564237ff8ab8a1bf5578a8181f17a6c711d3b15789bbfecacefc8eff862389d` |
| `refreshLifecycle` | `a349197ae9a3805e700b57bb13464687e37307f4b923f85f1426d6d4dc184f1a` |

随机 AgentRun、Runtime、Session、authorization 和 proposal 原始 ID、端口、时间、绝对路径、完整 diff、文件正文、完整 HTML、完整错误文本、具体 `currentMtime` 与原始请求体均不进入哈希。随机身份使用 alias 或 match 布尔归一，只冻结固定 action、decision、role、相对路径、marker、计数、顺序、状态和可见性语义。

## 验证事实

- R051 六个 frozen 单例全部通过：H4-8D bundle `1 passed (6.4s)`、direct classic `1 passed (5.0s)`；H4-8C approved bundle/classic 分别为 `1 passed (4.0s)` / `1 passed (4.2s)`，rejected bundle/classic 分别为 `1 passed (4.6s)` / `1 passed (4.1s)`。H4-8D 十项与 H4-8C approved/rejected 十八项分别严格匹配原冻结值；
- 编辑授权与冲突低层定向测试为 `10 passed in 1.71s`，覆盖耐久批准、拒绝不写、apply 幂等、approved stale conflict、写后重启 replay，以及 diff、写入、备份和 mtime conflict/match；
- H4-8A/H4-8B bundle/direct classic 邻接四例为 `4 passed (14.3s)`，旧冻结哈希不漂移；
- 标准 `npm run test:h4:e2e` 连续两轮分别为 `61 passed (3.6m)` 与 `61 passed (3.5m)`，均由 infra 先行、`workers=1`、`retries=0`，每轮各 61 条 cleanup 全部闭合；H4-8A/B/C/D 的 bundle/classic 哈希与副作用跨入口、跨轮一致；
- 完整 `tests` 目录 pytest 为 `1126 passed, 751 subtests passed, 3 warnings in 95.98s`；三条 warning 均来自既有损坏 TIFF 负测触发的 Pillow EXIF 警告；
- Harness replay 保持 17 fixtures、124 events、25 checkpoints、25 checkpoint recoveries、4 explicit recoveries，replay hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`；
- `npm run check:frontend`、三项 Node 语法、Python `py_compile` 与 `git diff --check` 全部通过；
- 结束时 H4/isolated-host/Chromium 相关进程、对应监听、`code-h4-e2e-*` 临时根和仓库 fixture 均为 0；H4 命令的临时 bundled Python PATH 已恢复，pytest 使用已预检的 AppX Python 绝对路径且没有持久修改 PATH，Process/User/Machine `PYTHONPATH` 均未设置；历史诊断与 profile 原样保留；
- H4-8C approved/rejected 十八项冻结值、四条场景和既有投影均未漂移。

上述最终证据对应以下测试字节：

| 文件 | SHA-256 |
|---|---|
| `tests/e2e/h4/infrastructure-selfcheck.cjs` | `9af673413380a689846fa0bb1e2fa2604fe362fff8e22a68e4a6f191e1c4ce94` |
| `tests/e2e/h4/isolated_host.py` | `1d520282cd62b17688d5d05ba7d35fca78ad6947420f3b2bf868ebe3c854ea62` |
| `tests/e2e/h4/smoke.spec.cjs` | `5ebe9b0aca2f836b76db1627ea3b24413c7a25bec0dc422a33cf167975a695c7` |

## 证明边界

H4-8D 只证明隔离项目中固定单文件、固定单 proposal、一次测试控制第三方转换、一次真实 UI 批准、生产已有 stale-edit 冲突结果、同进程完整页面刷新以及固定第三方内容保持。它不证明：

- 任意路径或内容、任意外部编辑器、多个文件、多 proposal、多个 pending authorization、多标签页或并发 actor；
- mtime-only 或 hash-only 竞争、proposal target 已经写入时的 idempotent replay、删除/目录/编码/权限冲突或通用文件系统 race；
- authorization、resume、apply、Session save 或模型 API 失败后的重试与恢复，服务响应丢失或重复点击；
- 崩溃窗口、服务重启、跨进程恢复、background/detached/`/parallel`、queue 或 Child AgentRun；
- 真实模型、真实外部编辑器、外网、凭据、线上配置、Firefox、WebKit 或发布门禁；
- OS syscall exactly-once、通用副作用 exactly-once、自动合并、专属冲突 UX、自动展示冲突原因或主观视觉/无障碍验收。

## 兼容性、回退与共享事实源

H4-8D 没有生产代码、API、authorization 协议、AgentRun/Runtime 协议、Session 格式、JSONL schema 或数据迁移变化，也不会回写真实用户数据。回退只需撤销 `tests/e2e/h4/infrastructure-selfcheck.cjs`、`tests/e2e/h4/isolated_host.py`、`tests/e2e/h4/smoke.spec.cjs` 中的 H4-8D 测试增量并删除本专题；无需迁移、转换或修复任何真实 Session。

统一 TODO、开发日志和日志索引当前属于共享现场，本提交按批准范围不修改这些文件。因此本专题只完成 H4-8D 的独立测试证据收口，不声称统一项目事实源已经同步，也不代表 Harness 第一轮其余完成线已经结束。
