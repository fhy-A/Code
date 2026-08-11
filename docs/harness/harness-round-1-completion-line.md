# Harness 第一轮完成线

## 文档目的与判定原则

本文为 Harness 第一轮工程建立一个有限、可复现、可验收的完成边界。它定义“何时可以宣布第一轮完成”，不替代统一 `TODO`、开发日志、日志索引或活动交接，也不把正在开发、仅完成 bootstrap 或尚未提交的证据提前记为完成事实。

第一轮只有在本文“完成定义”中的必选项和最终门禁全部通过后才能结束。单条用例通过、候选哈希生成、局部实现完成或一次环境补证都不构成阶段完成。各专题在收口时引用本文，并按各自真实文件树、验证结果和独立本地提交记录完成事实。

截至 2026-08-12 的综合核对，本文五项完成定义已经在冻结证据树 `618f876fb7d09f821b302eaf5a731f367fd894ac` 全部闭合。该结论只适用于本文定义的有限第一轮边界，不扩张任何专题的证明范围。

## 完成定义

Harness 第一轮必须同时满足以下五项。

### 1. 收口 H4-8D 过期编辑建议冲突

建立固定、隔离的 `propose_edit` stale conflict 浏览器证据：页面在等待授权时完整刷新；随后唯一受控文件被固定“第三方”内容修改；用户通过真实 UI 批准后，生产 apply 返回现有 conflict 结果，且不得覆盖第三方内容、产生有效生产写入或创建 backup；同一 AgentRun 正常继续到终态，终态完整刷新不重放模型、授权、apply 或文件副作用。

H4-8D 只有在独立语义哈希固化后，bundle 与 direct classic 逐项相等、组合用例通过、H4-8C 已冻结证据不漂移、相关回归与资源清理闭合，并完成专题文档和独立本地提交后，才可记为完成。bootstrap、候选哈希或单一 bundle 证据不满足该完成条件。

### 2. 补齐问卷等待态与队列刷新顺序

新增一个最小、固定的生产队列组合证据，证明 AgentRun 处于问卷等待态时，完整刷新不会改变待答问卷、队列身份或既有顺序；用户完成问卷后，问卷回执、队列状态与后续模型继续按现有生产语义形成唯一、稳定顺序，终态刷新不重复 input、resume、队列提升、AgentRun、Runtime 或模型请求。

该证据必须直接复用已冻结的 H4-8A/H4-8B 等待态、Session、DOM、请求与刷新投影，不复制问卷状态机、不另建第二套 questionnaire helper，也不重基线既有哈希。实际队列顺序以只读审计和首个真实 bundle 证据为准，不在实现前虚构新的排队算法或交互语义。

### 3. 补齐授权请求失败后的安全重试

在现有授权协议和 UI 入口内冻结一个固定失败与恢复场景：授权请求失败后，用户可通过产品现有入口执行一次安全重试；失败尝试不得提前应用 proposal 或产生持久副作用，恢复链不得重复耐久 decision、resume、apply、有效 write 或 backup。

该门禁必须分别核对请求层、AgentRun/Runtime、Session、DOM 与文件副作用层，区分“HTTP 尝试次数”与“耐久决策或生产副作用次数”。测试不得通过吞掉异常、放宽断言、模拟产品状态机或新增隐式重试来满足要求；若现行产品没有可复用的安全重试入口，必须停止并走新的产品决策门禁，不能自行改变协议或交互。

### 4. 审计后台 `/parallel` 编辑授权恢复

对 background、detached 或 `/parallel` 编辑授权等待、刷新与恢复做一次只读价值和可行性审计。只有同时满足以下条件时，才纳入第一轮实施：

- 不需要新的产品决策或交互定义；
- 不改变 authorization、Session、AgentRun、Runtime、JSONL 或恢复协议；
- 不扩大文件、命令或凭据安全边界；
- 可以用固定隔离场景和自动化证据完成，不依赖主观人工验收。

任一条件不满足时，审计结论必须说明阻塞点、风险和后续验收方向，并把实施明确延期。完成这次审计本身是第一轮门禁；被合理延期的 `/parallel` 授权实现不阻塞第一轮完成，也不得由前台 H4-8C 证据或既有并行失败隔离证据拼接成“已经覆盖”。

### 5. 通过最终集成与收口门禁

完成上述必选实现后，最终文件树必须一次性通过：

- 每个新增浏览器场景的 bundle 与 direct classic 语义哈希逐项相等，既有 H4-8A/H4-8B/H4-8C 及其他冻结哈希不漂移；
- 标准 H4 入口连续两轮全部通过，`workers=1`、`retries=0`，实际用例清单和总数逐项核对；
- 受影响的生产、Agent、Runtime、Session、queue、authorization、route 与 frontend 定向回归全部通过；
- 完整 pytest、前端构建新鲜度、Node/Python 语法、尾随空白和 `git diff --check` 全部通过；
- `npm run verify:harness-replay` 保持当前已提交基线：17 fixtures、124 events、25 checkpoints、25 checkpoint recoveries、4 explicit recoveries，suite hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`；
- 每轮结束时 H4/isolated-host/Chromium 相关进程、对应监听、受控临时根和仓库 fixture 均归零；成功与失败诊断按批准规则保留，不用清理掩盖结果；
- 每个完成专题准确记录证明边界、兼容与回退，最终以明确白名单创建独立本地提交；第一轮收口不自动授权 push、tag、release 或下一阶段工作。

## 完成证据矩阵

下列事实均已形成专题和独立本地提交。这里引用各提交对应最终文件树上的历史验证事实；本次综合收口不重新运行、重基线或改写既有 H4 测试。

| 完成项 | 已完成边界 | 专题 | 提交 | 判定 |
|---|---|---|---|---|
| H3 replay 发布门禁 | 离线 replay、检查点恢复与发布门禁基线 | [`h3-final-coverage-release-gate.md`](h3-final-coverage-release-gate.md) | `7705b3d414446c19c22b4799498cd7ec2b3bfadd` | 已完成 |
| H4-8A | 固定 required single-choice 问卷等待态刷新、一次 input/resume、同 Run 完成与终态零重放 | [`h4-8a-request-user-input-refresh-resume.md`](h4-8a-request-user-input-refresh-resume.md) | `b8349ade4ed45eadebd9f2bef9f03bfb3e3c62fc` | 已完成 |
| H4-8B | 固定三题 mixed questionnaire 的渐进进度、Q2 完成后且 Q3 尚未填写时刷新、一次提交与终态零重放 | [`h4-8b-mixed-questionnaire-progress-refresh.md`](h4-8b-mixed-questionnaire-progress-refresh.md) | `68d8165cc27695d7e3f13fe7b68341c6f42bc058` | 已完成 |
| H4-8C | 固定单一编辑建议的前台批准/拒绝、等待态与终态刷新恢复、受控副作用边界 | [`h4-8c-edit-authorization-refresh-resume.md`](h4-8c-edit-authorization-refresh-resume.md) | `282636a9297054a47db311b2e47c73f2d92b6450` | 已完成 |
| 完成定义 1：H4-8D | 固定 approved stale conflict 保留第三方内容，生产 apply/write/backup 为 `1/0/0`，刷新零业务重放 | [`h4-8d-approved-stale-edit-conflict.md`](h4-8d-approved-stale-edit-conflict.md) | `0e349e3d34264263567d1297732552af5f1f587e` | 已完成 |
| 完成定义 2：H4-8E | 固定问卷等待态、唯一队列项跨刷新保持，主 Run 完成后只提升一次并形成独立 Run | [`h4-8e-questionnaire-queue-refresh-order.md`](h4-8e-questionnaire-queue-refresh-order.md) | `387a3a3bff5e432f4362998c19680df9ce7e53ac` | 已完成 |
| 完成定义 3：H4-8F | 第一次 authorization POST 在生产 handler 前失败，用户通过现有入口单次手动重试，耐久决策与副作用唯一 | [`h4-8f-authorization-request-failure-retry.md`](h4-8f-authorization-request-failure-retry.md) | `8cd6116aa2b7fcc71c5919b90d733a4869a1b12a` | 已完成 |
| 完成定义 4：H4-8G | 只读审计确认无需新产品决策或协议/持久化/安全扩张后，完成固定 detached `/parallel` 编辑授权刷新恢复 | [`h4-8g-detached-parallel-edit-authorization-refresh.md`](h4-8g-detached-parallel-edit-authorization-refresh.md) | `618f876fb7d09f821b302eaf5a731f367fd894ac` | 已完成 |
| 完成定义 5：最终集成门禁 | A～G 哈希对等、双轮 H4、相关回归、完整 pytest、replay、构建/语法/diff 与资源审计在最终证据树闭合 | 同上及各专题 | `618f876fb7d09f821b302eaf5a731f367fd894ac` | 已完成 |

H4-8A/B/C 继续作为后续组合的既有基线，H4-8D/E/F/G 没有重新冻结它们。完成定义 4 的审计结论是“满足条件并实施固定场景”，不是把 background、detached 或 `/parallel` 的所有授权恢复路径声明为已经覆盖。

## 综合完成判定

冻结证据树上的最终门禁为：

- 标准 H4 第一轮为 `67 passed (3.9m)`，独立 infra 后专用 output 的第二轮为 `67 passed (4.4m)`；两轮均为 1 worker、0 retry、各 67 条 cleanup，A～G 受门禁哈希跨 bundle/direct classic、跨轮一致；
- 相关十文件回归为 `680 passed, 260 subtests passed, 1 warning in 34.74s`；唯一 warning 为既有损坏 TIFF/EXIF Pillow 负测；
- 完整 `tests` pytest 为 `1126 passed, 751 subtests passed, 3 warnings in 93.48s`；三条 warning 均为既有损坏 TIFF/EXIF Pillow 负测；
- Harness replay 保持 `17 fixtures / 124 events / 25 checkpoints / 25 checkpoint recoveries / 4 explicit recoveries`，suite hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`；
- `npm run check:frontend`、`npm run verify:frontend`、Node 语法、Python AST 与 `git diff --check` 均通过；既有 `server.py:4949` invalid escape `\C` SyntaxWarning 不计入 pytest warning；
- H4/isolated-host/Python/Chromium 相关进程、监听、临时根、fixture、backup 与 H4 pyc 均归零；R059C～R059L ignored outputs、R059M passed output 和 `%TEMP%` 诊断证据按批准边界保留，未通过清理掩盖结果。

据此，Harness 第一轮在本文定义的有限工程边界内完成。该判定不表示通用 exactly-once、授权恢复完整覆盖、并发/多标签页/多 actor 组合穷举、服务重启或跨进程 active 恢复、Firefox/WebKit、真实外网/模型/凭据、主观视觉或可访问性已经通过，也不授权启动 H4-8H、H5 或任何下一 TODO。

## 延期边界

第一轮不追求场景组合穷举。以下内容转入后续轮次，不阻塞第一轮完成：

- Child AgentRun 生命周期的进一步深化；
- 超出本文固定场景的更多真实并发、并行组合、多 proposal、多 pending、多标签页或竞态排列；
- 超出必选刷新证据的跨进程恢复、服务重启和崩溃窗口扩张；
- Firefox、WebKit 与其他浏览器矩阵；
- 真实外网、模型、凭据、线上配置或发布链验证；
- 需要主观视觉、体验、可访问性或人工时序判断且没有等价自动证据的场景；
- 经本文条件审计后明确延期的 background、detached 或 `/parallel` 编辑授权实现。

延期项不得反向扩大第一轮完成定义。后续如主动把某一延期项纳入第一轮，必须先明确新增范围、自动验收和风险，再重新评估计划时间；不能在实施过程中无边界追加组合。

## 历史计划时间

本文起草时曾按不出现新产品决策、协议/安全范围扩张或基础设施阻塞的前提估算 **2～3 个工作日**；主动纳入延期项时曾估算为 **5～8 个工作日**。这些数字只保留为历史计划，不再表示当前剩余工期或新的实施承诺。

第一轮已经按本文有限边界完成。延期项继续作为后续候选存在，但不得自动并入第一轮、启动 H4-8H/H5，或由本完成判定选择下一项。
