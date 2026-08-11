# H4-8F 编辑授权到达服务端前失败与单次安全重试

## 目标与阶段定位

H4-8F 为固定、单一、前台 `propose_edit` 授权补齐一条真实浏览器证据：主 AgentRun 已经完整刷新并恢复到 `waiting_authorization` 后，用户通过现有批准按钮发起授权；第一次批准请求只在当前 Playwright page 的传输层被一次性中止，没有到达生产 `CodeHandler`；失败 UI 恢复后，用户再通过同一个现有批准入口点击一次，第二次请求进入真实生产链并完成。

本阶段不是新增产品功能，也不是生产修复。实现差异只位于 `tests/e2e/h4/smoke.spec.cjs`，复用 H4-8C 的 waiting、complete 与 terminal reload 生命周期，以及现有隔离宿主的固定 proposal、文件和指标事实源。`app.js`、`server.py`、AgentRun/Runtime、授权 API、Session/JSONL、持久化格式、队列或安全边界均未改变，也没有新增 UI、host 控制命令或写入能力。

这里的“安全重试”只指**请求在到达生产处理器之前失败**的固定窗口，并且重试是用户再次点击现有按钮一次，不是自动重试。下列另外两种语义不在本阶段内：

- 服务端已经耐久保存 decision，但响应丢失；
- decision 已完成，而随后 `/resume` 失败。

现有证据不能把这两种窗口等同于 pre-handler failure，也不能据此宣称 authorization POST 具有通用服务端幂等重发契约。

## 固定场景与注入边界

场景沿用 H4-8C approved 分支的固定单文件、单 proposal 与初始/目标内容：

1. 主 AgentRun 产生唯一 `propose_edit`，进入 `waiting_authorization`；
2. 先执行等待态完整刷新，恢复同一 AgentRun、authorization、proposal、Session、diff、DOM 与 initial 文件；
3. 在当前 origin、编码后的同一 AgentRun 和精确 `/authorization` URL 上安装 `times: 1` 的 page route；
4. 用户真实点击 approve；测试在放开 abort gate 前严格核对捕获请求为 POST、精确 JSON key 集、同一 authorizationId 与 `decision=approved`，随后 route 只调用 `abort("failed")`；
5. 失败 UI 恢复后，用户通过现有批准按钮再点击一次；第二次请求不再被 page route 拦截，进入生产 authorization、apply 与 resume 链；
6. 同一父 AgentRun 完成，再执行终态完整刷新。

注入不会 `fetch`、`continue`、`fallback` 或 `fulfill` 请求，也不会伪造 loopback、AgentRun、Session 或文件状态。它不是 HTTP 503、服务端 fault endpoint 或 host 注入命令；测试只观察真实 page `request` / `requestfailed` 与生产 loopback/metrics 的边界。

## 首次失败：传输、UI 与耐久状态

首次点击后的浏览器授权传输计数为：

| 事实 | 值 |
|---|---:|
| client attempts | 1 |
| request failed | 1 |
| page fault injected | 1 |
| forwarded to production | 0 |

因此首次失败发生在生产 handler 之前。该窗口内 production authorization、`/resume`、apply、有效 write 与 backup 增量均为 0；registered proposal delegation/execution、upstream chat、AgentRun/Runtime 创建以及受控 unsafe 指标的增量也为 0。apply/write/backup 三条受控时间线均为空，文件保持 initial SHA，备份数量不变。

public AgentRun 仍为 `waiting_authorization`，cursor 为 `5`，pending decision 为 `pending`，execution authorization decision 为空。事件序列保持精确五项：

```text
created → model_started → model_completed → tool_started → authorization_required
```

失败前后的 AgentRun 事件、execution、规范化 waiting snapshot、Session/diff 投影、授权 DOM 投影与 control IDs 均保持一致；这里不宣称完整 Session/DOM 字节或 DOM 节点身份不变。文件仍为 initial SHA。

提交尚未失败返回时，authorization row 处于 submitting，原选择与 approve 控件禁用，错误 toast 数为 0。abort 返回后，同一 row 语义和原选择保留，row 不再 submitting，approve 按钮恢复可用；唯一 error toast 可见且非空。测试只冻结 toast 的数量、可见性与非空布尔，不冻结浏览器错误全文。

## 第二次点击：同一 Run 完成且副作用唯一

用户只通过现有 approve 操作重试一次。全场景浏览器 authorization POST 的 attempts / failed / injected / forwarded 最终为：

```text
2 / 1 / 1 / 1
```

第二次请求进入生产链后，durable authorization decision、`authorization_submitted`、production authorization POST、`/resume`、`resumed`、apply、有效 write 与 backup 各恰好 1 次，`replayed=false`。这里只把受控生产指标和耐久事件记为一次，不外推到 `_persist_agent_run` 调用次数或操作系统 write syscall exactly-once。

整个场景固定为 1 个 AgentRun、2 个 Runtime 与 2 次 upstream chat；两个 Runtime 的 cursor 为 `[4,3]`。registered proposal delegation/execution 总量为 `1/1`，来自等待失败之前已经发生的唯一 `propose_edit`；首次失败阶段对应增量为 `0/0`，不能写成“整个场景没有工具执行”。

父 AgentRun 的完整十二事件为：

```text
created → model_started → model_completed → tool_started
→ authorization_required → authorization_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

其中 `waiting_credentials` 是既有耐久恢复事件名，不表示本场景使用真实凭据。

终态 Session 的五条逻辑消息保持：

```text
user initial → assistant tool-owner → propose_edit tool-call
→ server-managed tool-result / edit suggestion → assistant final
```

终态 DOM 顺序为：

```text
initial-user → stage → tool-process → edit-suggestion → final
```

授权面板已隐藏，唯一 tool trace、proposal result、edit suggestion 与 final 保持。文件由 initial 变为 target，唯一 backup 保存 initial 字节。

## 完整刷新与零业务重放

等待态完整刷新发生在故障注入之前，恢复同一 AgentRun、authorization、proposal、Session/diff、DOM、permission 与 initial 文件，所有受控业务写入增量为 0。

成功重试后的终态完整刷新保持同一 AgentRun、十二事件、两个 Runtime、Session 五角色、authorization meta、DOM 与 target 文件；AgentRun/Runtime 创建、chat、authorization、resume、registered delegation/execution、proposal/apply/write/backup 的业务增量均为 0。刷新允许正常 GET，本专题的“零业务重放”不表示零网络请求。

## 十项冻结语义哈希

bundle 与 direct classic 共用同一 lifecycle、投影和常量门禁，十项哈希逐项一致：

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3` |
| `waitingSnapshot` | `9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2` |
| `waitingDom` | `880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618` |
| `failedAttemptProjection` | `d906f98034b76a14083d4bd3bbe9f7e0d8cf05584de83eaf68ca20c20a636e70` |
| `retrySubmissionProjection` | `5de63672ddec48bf0de379cf9f24abf06eff143b2309d73da2a3a70669694c13` |
| `runtimeProjection` | `b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540` |
| `sessionRoleContent` | `f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0` |
| `sessionAuthorizationMeta` | `817262e2d16999b26b98a8c25711160d387e238f5c62fa385e3132ff1382aac2` |
| `terminalDom` | `30a687f6910faf0e82f18e0097187cd7b021957270c18370c7cab2774c65602d` |
| `refreshLifecycle` | `fc229f1032cb024b68f1b4755e69c590e58f2ad2a1a0ef7c604e8c38359403d3` |

随机 AgentRun、Runtime、Session、authorization 与 proposal 原始 ID，完整 URL、端口、时间、原始请求体、headers、错误文案、绝对路径、完整 diff/HTML、文件正文和 backup path 均不进入哈希或脱敏 evidence；冻结内容只包含受控 alias/match、计数、事件、角色、顺序、状态与布尔因果。

## 验证事实

- Node 语法、固定 WindowsApps Python 3.12.10 语法、`git diff --check`、前端 build/freshness 与独立 H4 infra 自检通过；测试差异期间 smoke SHA-256 为 `5ab3a3f33558272ad74b59645964a7345869788d077ca7c75e30efe931635d76`。
- 相关七文件回归为 `607 passed, 260 subtests passed, 1 warning in 34.34s`；warning 是既有损坏 TIFF/EXIF 负测。
- H4-8C approved/rejected bundle/classic 四例为 `4 passed (13.4s)`；H4-8A/B bundle/classic 四例为 `4 passed (20.9s)`，旧冻结哈希未漂移。
- Harness replay 保持 `17 fixtures / 124 events / 25 checkpoints / 25 checkpoint recoveries / 4 explicit recoveries`，suite hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`。
- 完整 `tests` pytest 为 `1126 passed, 751 subtests passed, 3 warnings in 91.51s`；三条 warning 均来自既有损坏 TIFF/EXIF 负测。
- 标准 H4 精确枚举 65 例；连续两轮分别为 `65 passed (4.2m)` 与 `65 passed (4.1m)`，均为 1 worker、0 retry、各 65 条 cleanup。A～F 全部冻结哈希跨 bundle/classic、跨两轮零差异；H4-8F 四份规范化 evidence 除 label/runtime 外完全相同。
- 终态 H4-owned child、isolated host、Chromium、相关监听端口、`code-h4-e2e-*` 临时根、fixture、backup 与 H4 pyc 均为 0；既有专用 output 与 profile 未被清理或改写。

## 非产品诊断插曲

- 一次独立 infra 在浏览器前以 child exit 103 停止，没有生成 H4 业务 evidence，也未计为通过；随后独立 infra 与两轮标准入口中的 infra 均通过。该现象没有改写为产品失败或产品通过证据。
- R058C 使用全锚定 grep 时在 test discovery 阶段得到 `No tests found`，测试体、host 和浏览器均未启动；失败 `.last-run.json` 原样保留。R058D 使用经 `--list` 证明唯一匹配的选择器后，bundle bootstrap 通过。
- 前端构建第一次受执行沙箱目录访问限制而报 `Access denied`；相同命令和参数在获准环境中通过，没有修改构建配置。
- 裸 `python` 曾命中损坏的 Hermes venv launcher，矩阵尚未开始便停止。后续只使用既有 WindowsApps Python 3.12.10 的固定绝对路径完成 Python 预检、语法和 pytest，没有安装依赖或修改 PATH/venv。

这些均是选择器、执行环境或基础设施诊断，不是 H4-8F 产品行为失败，也不能替代最终通过矩阵。

## 证明边界

H4-8F 只证明隔离环境中固定单文件、单 proposal、前台 approved 分支、单标签页/actor、第一次 authorization POST 在到达生产 handler 前失败、用户随后单次手动重试的行为。它不证明：

- 服务端已经耐久 decision 后响应丢失，或同一 authorization POST 的通用幂等重发；
- decision 后 resume、Session save、apply、write 或 backup 失败与重试；
- 多 authorization、多 proposal、多 pending、多标签页、并发 actor、重复点击、reject 重试或自动重试；
- 网络抖动矩阵、backup/write crash window、进程崩溃、服务重启或跨进程恢复；
- background、detached、`/parallel` 或其他工具授权组合；
- 真实模型、外网、凭据、Firefox/WebKit、主观视觉/无障碍、发布或 OS syscall exactly-once。

因此，本阶段关闭的是第一轮完成线中“授权请求失败后的安全重试”的固定 pre-handler 证据项，不表示 Harness 第一轮已经完成；`/parallel` 编辑授权恢复只读审计/条件实施与最终整体收口仍是后续独立阶段。

## 兼容性与回退

本阶段没有生产代码、API、协议、Session/AgentRun/Runtime、JSONL schema、持久化、迁移、安全边界或交互变化。回退只需撤销 `smoke.spec.cjs` 中 H4-8F 的常量、薄故障 bridge/lifecycle 与两个测试入口，并移除本专题及对应日志/索引增量；不需要迁移或回写任何真实数据，也不应回退 H4-8C。
