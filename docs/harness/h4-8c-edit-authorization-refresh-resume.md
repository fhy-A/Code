# H4-8C 编辑授权刷新恢复与单次决策

## 目标与完成范围

H4-8C 冻结一个受控 `propose_edit` 的浏览器授权生命周期：模型只提出一份固定编辑建议，页面在等待授权时执行完整刷新，用户再通过真实 UI 批准或拒绝，随后同一 AgentRun 继续到终态，并在终态完整刷新后证明没有重放。

场景只操作隔离项目根内的固定相对路径 `h4-propose-edit-fixture.txt`。初始内容与目标内容分别为固定 marker，对应 SHA-256 为：

- initial：`f12af1cc9275e5511341e977ac8ad5b13050b8eb8951b4a78555018cdbcaebe3`；
- target：`26ed22af144d40ac7a02a4a6087bbfa8bcb2024782e90fdac3ed6cb2abbbf3ef`。

批准与拒绝分别覆盖 bundle 和 direct classic。四条用例共用生产 UI/API、Chromium 页面操作和隔离 loopback 假上游，不调用真实模型、外网或凭据。模型工具仍是 `propose_edit`；生成建议后，公开授权请求的现有 action 为 `apply_edit`。

## 根因与生产修复

前台编辑授权链在两处已经更新了内存消息投影，但既有 `saveSessionState()` 只保存 Session 元数据和 `runState`：

1. 等待授权时，proposal diff 与编辑建议卡已经投影进 `messages`，`runState.authorizationRequest` 也已建立，但保存没有同步完整消息；完整刷新后授权面板可以从 `runState` 恢复，proposal diff 与编辑建议却可能缺失。
2. 批准或拒绝后，消息中的 decision 投影已经更新、pending authorization 已清空，但提交后的保存同样没有同步完整消息；在 resolver 或同 Run 恢复前存在一段决策投影尚未耐久化的窗口。

生产修复只在 `app.js` 的这两处现有、已等待的前台 `saveSessionState()` 调用上增加 `{ persistMessages: true }`。等待态仍保持“先完成 proposal 投影与 waiting runState，再完整保存”；决策态仍保持“先提交授权、标记 approved/rejected、清 pending 并更新 runState，再完整保存，最后 resolver 或恢复”。background 分支和原控制流不变。

修复复用既有 serializer、Session JSONL 与消息 meta，不新增字段、版本、迁移或持久化入口，也不修改 API、AgentRun、Runtime、authorization 协议或 `server.py`。

## 固定场景与公共生命周期证据

隔离假上游只发送一个 schema-valid 固定 payload：`path`、`oldText`、`newText` 三个键及其固定值必须精确匹配。proposal 阶段只生成建议，不修改文件；用户决策后由生产既有授权链处理 apply 或 rejected receipt。

两条分支的共同计数为：

| 观察层 | 计数 |
|---|---:|
| AgentRun 总数 / 浏览器 AgentRun POST | 1 / 1 |
| Runtime 总数 / 浏览器 Runtime POST | 2 / 0 |
| 上游 chat | 2 |
| authorization POST | 1 |
| resume POST | 1 |
| registered proposal delegation / execution | 1 / 1 |
| AgentRun durable tool execution | 1 |

AgentRun 的 12 个事件严格为：

```text
created → model_started → model_completed → tool_started
→ authorization_required → authorization_submitted → tool_completed
→ waiting_credentials → resumed → model_started → model_completed → completed
```

其中 `waiting_credentials` 是现有恢复链的耐久事件名，不表示本场景使用真实凭据。两个 Runtime 的实测事件 cursor 为 `[4, 3]`。

等待态中，AgentRun pending authorization、Session `runState.authorizationRequest`、Session 唯一 server-managed proposal/diff 消息与 DOM 唯一 authorization panel/edit suggestion 在 authorizationId、toolCallId、proposalId、固定相对路径和 unified diff 语义上逐层闭合。Session diff 直接证明旧/新 header 与旧/新 marker 各出现一次；DOM 以唯一卡片和 `+1/-1` 语义对应，不冻结完整 HTML 或本地化文案。

等待态完整刷新后仍是同一 AgentRun、同一授权和同一 proposal，文件仍为 initial SHA；AgentRun/Runtime 写入、上游 chat、authorization/resume、proposal execution、apply、write 与 backup 增量均为 0。终态 Session 的五条逻辑消息保持：

```text
user → assistant tool-owner → propose_edit tool-call
→ server-managed tool-result / edit suggestion → assistant final
```

批准或拒绝后都只产生一个终态回执和一个 final。终态完整刷新保持 Session、AgentRun、两个 Runtime 与 DOM 语义投影不变，AgentRun/Runtime 写入、chat、authorization/resume、proposal/apply/write/backup 增量仍全部为 0。这里的“零增量”针对受控写入、模型和工具观察层；刷新本身的读取请求不在该表述内。

## 批准与拒绝的文件副作用

批准分支只点击一次真实批准入口。生产授权链的逻辑 apply、有效 write 与 backup 计数精确为 `1 / 1 / 1`，`replayed=false`，文件由 initial SHA 变为 target SHA，备份内容对应原始 initial 字节。这里的 write 是受控生产写入时间线中的一次有效逻辑写入，不宣称操作系统层只有一次 write syscall。

拒绝分支只点击一次真实拒绝入口。apply、有效 write 与 backup 均为 `0 / 0 / 0`，文件从等待态到终态始终保持 initial SHA；唯一 rejected 回执进入第二轮模型上下文，同一 AgentRun 最终完成。拒绝不会调用 apply，也不会创建备份。

## 隔离宿主安全边界

隔离宿主只对白名单 `propose_edit` 和固定三键 payload 开放生产 proposal 委托，并在委托前核对固定相对路径、初始/目标字节及 base/new SHA。apply 包装只接受由该受控 proposal 生成且 proposalId、path、base/new hash 均匹配的私有 proposal，随后仍委托生产既有 apply 入口；测试代码不自行模拟授权状态机或改写文件。

基础设施自检证明：

- 路径逃逸、额外字段、错误字节，以及错误 action/path/字段/内容的 apply proposal 均在生产委托前拒绝；
- `write_file` 与 `delete_file` 继续被 registry 边界拒绝；
- `run_command` 由入口 reject stub 硬拒，stub 不引用或调用捕获的原生产 executor，output/process callback 增量均为 0；
- 合法 probe 只生成一次 proposal，apply/write/backup 均为 0，fixture 与备份状态不变；
- project、home、artifacts 三棵目录树的相对路径、类型、大小与 SHA 指纹均保持不变。

因此该测试扩展不是通用文件写入、删除或命令执行能力；所有受控编辑与备份都位于每条用例自己的临时隔离根，并在用例清理时移除。

## 冻结语义哈希

随机 AgentRun、Runtime、Session、authorization 与 proposal 原始身份、端口、时间、绝对路径、完整 diff、完整 HTML、原始请求体和私有 proposal 内容均不进入哈希。随机身份使用 alias 或 match 布尔归一；固定 action、decision、role、kind、相对路径、marker、数量、顺序和状态作为受控语义进入。

### Approved

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3` |
| `waitingSnapshot` | `9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2` |
| `waitingDom` | `880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618` |
| `decisionSubmissionProjection` | `10ee72f265dd84bd02f177a7ed8330f2b949f6a4c9bb57ee661381ded560179a` |
| `runtimeProjection` | `b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540` |
| `sessionRoleContent` | `f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0` |
| `sessionAuthorizationMeta` | `817262e2d16999b26b98a8c25711160d387e238f5c62fa385e3132ff1382aac2` |
| `terminalDom` | `30a687f6910faf0e82f18e0097187cd7b021957270c18370c7cab2774c65602d` |
| `refreshLifecycle` | `8cd5d4b2c4c6de7fa02758a00429fcdca4877a25f6ae7e4b58fa24dc4ad67c04` |

### Rejected

| 投影 | SHA-256 |
|---|---|
| `waitingEventProjection` | `87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3` |
| `waitingSnapshot` | `9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2` |
| `waitingDom` | `880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618` |
| `decisionSubmissionProjection` | `2e4006664b0b78311fbb351d43957db74af5cea392479b9b5b3df69646faad3e` |
| `runtimeProjection` | `b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540` |
| `sessionRoleContent` | `f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0` |
| `sessionAuthorizationMeta` | `789eb128e116eede40ace51e8118457fab6214bfb58692afe708cac7b3434275` |
| `terminalDom` | `292de41a94f02fdbe4ba3a58cf6be4a9e218b34157a8fc191a240282cc18fb12` |
| `refreshLifecycle` | `a020554dd7822809017c01e41e0fbcf85879e2ea019f9ad16670c76d0a599ed3` |

bundle 与 direct classic 在 approved/rejected 各自分支中逐项相等；H4-8A 与 H4-8B 的既有冻结值也在同一最终文件树下保持原样。

## 验证事实

- H4-8C approved/rejected 的 bundle 与 direct classic 四个 frozen 单例均通过；每个分支的九项运行结果分别与冻结值严格相等，bundle/classic 对等；
- `npm run test:h4:infra` 通过，固定 proposal、危险入口硬拒绝、目录树指纹、child/ports/temp root 清理全部闭合；
- production/frontend/edit/Agent/route/projection 邻接回归为 `425 passed, 247 subtests passed`；
- H4-8A/H4-8B bundle/direct classic 四例为 `4 passed (26.5s)`，既有哈希逐项不变；
- 连续两轮标准 H4 均为 `59 passed (3.7m)`，`workers=1`、`retries=0`；两轮各 59 条 cleanup 均闭合，H4-8A/H4-8B/H4-8C 的 bundle/classic 哈希跨运行一致；
- 完整 pytest 为 `1131 passed, 751 subtests passed`，另有 3 条固定损坏 TIFF 输入触发的预期 Pillow EXIF 警告；
- Harness replay 为 17 fixtures、124 events、25 checkpoints、25 checkpoint recoveries、4 explicit recoveries，replay hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`；
- `npm run check:frontend` 证明 bundle/classic 构建新鲜；Node/Python 语法、`git diff --check` 与尾随空白检查通过；
- 结束时 H4/Chromium/isolated-host 相关进程、对应监听、`code-h4-e2e-*` 临时根和仓库内 fixture 均为 0，Process/User/Machine `PYTHONPATH` 均未被持久修改；既有失败诊断原样保留。

上述浏览器与回归证据对应以下最终实现/测试字节：

| 文件 | SHA-256 |
|---|---|
| `app.js` | `dddf849536732ca8bc9d5b3d932fb49305984b7c136b38089944e3480d358c08` |
| `tests/test_frontend_modules.py` | `8107a2bed5ce36afb6ebb9ff243fd8cc80f33561426780ab520753e4ea9d7062` |
| `tests/e2e/h4/isolated_host.py` | `c3019fcb4603d920c60dbd5a618f970e0c0b6e91b7e5ee0672f38ff193a29cfd` |
| `tests/e2e/h4/smoke.spec.cjs` | `65383ca31f89ba1c2ffa998b4f6e1b7b9098ec6754bae983d6e3f887f5f73419` |
| `tests/e2e/h4/infrastructure-selfcheck.cjs` | `a6ec58067d1aef7aa7fab768d8e47b8613cd7f9ce887aa60f54abe78b344567f` |

## 证明边界、兼容性与回退

H4-8C 只证明固定单一 `propose_edit`、固定相对路径与内容、同进程完整页面刷新、一次真实批准或拒绝、同 Run 继续和终态刷新。它不证明：

- 其他 authorization action、任意文件编辑、多 proposal、并发授权、多标签页或多个 pending authorization；
- Session save、authorization、resume、proposal、apply 或模型请求失败与重试；
- 编辑冲突、mtime/base hash 竞争、第三方并发修改、stale proposal 或 replay/crash 窗口；
- 服务重启、跨进程 Runtime/活跃授权恢复或通用 exactly-once；
- authorization 之外的 Child、queue、steer、detached/background 生命周期；
- 真实模型、外网、凭据、Firefox/WebKit、发布门禁、主观视觉或无障碍验收。

回退只需撤销 `app.js` 两处 `{ persistMessages: true }` 参数增量、四份测试/宿主文件的 H4-8C 增量以及本专题。没有数据迁移或回写；已经按标准 Session 消息格式写出的记录仍可读取。

统一 TODO、开发日志和日志索引仍由并行 workbar 协作者现场占用，本提交不修改这些共享事实源。因此本专题是 H4-8C 的独立证据收口，不代表统一项目总账已经归档；待共享现场释放后，应另做 docs-only 归档。
