# Harness H3 最终覆盖与 replay 发布门禁

## 收口结论

H3 已完成计划第 6.3 节十五类轨迹在非浏览器层的证据闭合，并把默认单 Run replay 纳入正式发布流程的独立门禁。证据由 Run replay、multi-run replay、生产集成、持久化恢复、生产 HTML 投影和隔离人工显示检查共同组成；不同证明层不被合并成一套虚构状态机。

H3 不把浏览器生命周期当作已经通过。第 4 类工具组真实展开保持，以及问卷、手动压缩、图片、队列的真实页面刷新与 DOM 行为继续属于 H4。现有源码切片、HTML 字符串和持久化测试只证明各自明确的非浏览器边界。

## §6.3 十五类轨迹证据映射

下表中的回放断言缩写为：`S` 状态合法，`H` 确定性哈希，`R` 检查点恢复，`I` 重复投递幂等，`M` 删除/乱序或错误改写的首差异，`T` 固定时钟。只有真正经过 Run replay 或 multi-run replay 的场景才使用这组六项；生产集成、持久化和 HTML 投影按其实际契约描述，不借用 replay 名义。

| # | 轨迹类别 | 现有 fixture / scenario / case | 主要测试 | 证明层与 H3 断言 | H3 结论与未覆盖边界 |
|---|---|---|---|---|---|
| 1 | 纯文本一次完成 | `plain-text-final` | `tests/test_harness_replay.py` | Run replay：S/H/R/I/M/T | H3 已满足；不证明真实流式 DOM。 |
| 2 | 阶段说明后单工具，再输出最终回答 | `single-read-tool` | `tests/test_harness_replay.py` | Run replay：S/H/R/I/M/T | H3 已满足；真实模型与工具执行不在离线回放范围。 |
| 3 | 同阶段多工具及完成统述 | `multi-tool-stage` | `tests/test_harness_replay.py`、`tests/test_frontend_modules.py::TestFrontendCoreModules::test_messages_ui_owns_grouping_projection_and_response_status` | Run replay：S/H/R/I/M/T；生产 HTML 投影核对当前工具和终态统述 | H3 已满足非浏览器状态与投影；真实 DOM 生命周期归 H4。 |
| 4 | 用户展开工具组，后续保持展开，终态后外层折叠 | `multi-tool-stage` 的投影输入；`expandedActiveTailHtml` / `completedCollapsedTailHtml` | `tests/test_frontend_modules.py::TestFrontendCoreModules::test_messages_ui_owns_grouping_projection_and_response_status` | 生产 HTML 投影直接断言运行中展开及完成后折叠；没有伪造 Run 状态 | H3 只满足投影结构证据；点击后的真实展开保持、重渲染与 DOM 折叠明确归 H4。 |
| 5 | `request_user_input` 等待、刷新、提交、继续 | `questionnaire-submit` | `tests/test_harness_replay.py`、`tests/test_agent_runtime.py::test_agent_questionnaire_waits_durably_and_continues_after_valid_answer`、`test_http_questionnaire_submit_endpoint_resumes_same_agent_run`、`tests/test_frontend_modules.py::test_server_agent_questionnaire_uses_durable_submit_and_reload_path` | Run replay：S/H/R/I/M/T；生产 AgentRun/持久化/前端结构契约 | H3 已满足耐久等待、提交和恢复契约；真实页面刷新与表单 DOM 归 H4。 |
| 6 | 文件修改授权接受与拒绝 | `edit-authorization-accept`、`command-authorization-reject` | `tests/test_harness_replay.py`、`tests/test_agent_runtime.py::test_accept_profile_waits_for_durable_edit_authorization`、`test_rejected_edit_authorization_keeps_file_unchanged` | Run replay：S/H/R/I/M/T；生产授权集成 | H3 已满足状态、决策和副作用边界；真实授权卡 DOM 归 H4。 |
| 7 | 命令执行中取消 | `cancel-during-command`、`cancel-multi-tool-terminal-closure` | `tests/test_harness_replay.py`、AgentRun 命令取消与进程终止回归 | Run replay：S/H/R/I/M/T；生产进程/AgentRun 集成 | H3 已满足取消终态闭合与重复取消边界；不证明浏览器关闭或真实线程竞争。 |
| 8 | 服务重启后复用已完成工具回执 | 精确生产案例 `test_restart_recovery_reuses_completed_tool_execution`；相邻诊断轨迹 `server-restart-command-unknown` 不代替该案例 | `tests/test_agent_runtime.py::test_restart_recovery_reuses_completed_tool_execution`、`tests/test_harness_replay.py` | 生产持久化与重启集成直接证明已完成回执复用；相邻 replay 仅证明未知运行中命令投影 | H3 已满足真实生产恢复契约；没有把相邻 fixture 名称误报为精确证据，不证明浏览器刷新。 |
| 9 | 自动上下文压缩后继续同一 AgentRun | `auto-compaction-success`、`auto-compaction-failure` | `tests/test_harness_replay.py`、`tests/test_agent_runtime.py::test_agent_compaction_plan_keeps_active_task_and_latest_complete_tool_group`、`tests/test_frontend_modules.py::test_auto_context_compaction_is_rendered_inside_execution_trace` | Run replay：S/H/R/I/M/T；生产压缩计划与 HTML 投影 | H3 已满足成功/失败投影和同 Run 继续；真实上游摘要与 DOM 归 H4/外部集成。 |
| 10 | 手动压缩保留完整可见历史 | `h3-2d2-manual-compaction-visible-history`、`h3-2d3-manual-compaction-failure-boundaries` 19 cases | `tests/test_harness_manual_compaction_visible_history.py`、`tests/test_harness_manual_compaction_failure_boundaries.py` | 精确 `app.js` 源码切片、真实 archive/JSONL/model context/HTML 投影；确定性哈希、固定时钟、专属首差异和一次性副作用 | H3 已满足成功与失败持久化边界；真实 HTTP、页面刷新、完整 DOM 生命周期及摘要质量归 H4/外部验证。 |
| 11 | 不支持 MIME 的图片历史：模型降级、UI 原图 | `h3-2d1-image-mime-preservation`：PNG/JPEG/WebP/BMP/GIF/ICO/TIFF | `tests/test_harness_image_mime_preservation.py`、`tests/test_image_vision_and_browser_refresh.py` | 生产序列化与 JSONL、模型图片投影、HTML 投影；fixture/语义哈希、重复稳定和专属首差异 | H3 已满足七格式生产链；真实浏览器显示与刷新归 H4，SVG/AVIF/HEIC 不在本矩阵。 |
| 12 | 排队消息和显式并行任务同时存在 | `queue-parallel-multi-run-relations` | `tests/test_harness_multi_run_fixtures.py`、`tests/test_harness_multi_run_replay.py`、`tests/test_message_queue.py`、`tests/test_subagent_frontend.py` | multi-run replay：S/H/R/I/M/T；生产 queue/background 直接函数与集成契约 | H3 已满足独立 Run 投影、静态身份、固定 schedule、复合恢复；真实队列提升、后台调度、usage/UI exactly-once、DOM 与刷新归 H4。 |
| 13 | Child AgentRun 完成顺序不同于父模型调用顺序 | `child-agent-out-of-order-terminal-parent-results` | `tests/test_harness_child_multi_run_fixtures.py`、`tests/test_harness_child_multi_run_replay.py`、`tests/test_agent_runtime.py::test_plan_delegation_runs_persistent_child_and_merges_usage_once` | multi-run replay：S/H/R/I/M/T；生产 Child 集成 | H3 已满足父子身份闭合、Child 终态与父工具结果独立顺序；不证明真实线程竞争、worker 或 DOM。 |
| 14 | 401、429、502、超时、空响应和 reasoning-only 恢复 | `upstream-401-config-terminal`、`upstream-429-transient-terminal`、`upstream-502-transient-terminal`、`model-first-response-timeout-terminal`、`model-empty-output-recovery-current`、`model-reasoning-only-recovery-current` | `tests/test_harness_upstream_failure_fixtures.py`、`tests/test_harness_upstream_failure_replay.py`、`tests/test_model_runtime.py`、`tests/test_agent_runtime.py` | Run replay：S/H/R/I/M/T；本地假上游生产分类与 AgentRun 规范事件集成 | H3 已满足当前分类和耐久事件顺序；429/502 的 HTTP 差异只由 Runtime 集成证明，不证明真实网络或所有 fallback。 |
| 15 | 旧 AgentRun 缺少新增字段时恢复 | manifest cases `agent-run-v1`～`agent-run-v4` | `tests/test_harness_legacy_agent_run_recovery.py` | 生产 loader、公共 snapshot、v4 persisted 三层；fixture/manifest 哈希、两次真实临时磁盘加载和专属首差异 | H3 已满足四份最小兼容记录；不证明损坏记录、Session JSONL、worker/工具外部状态或浏览器刷新。 |

## H3 证明边界

H3 的完成声明覆盖：

- 单 Run 与多 Run 的生产 reducer/View Model 离线回放、状态合法性、确定性哈希、检查点恢复、重复投递和首差异诊断；
- Runtime、AgentRun、授权、问卷、Child、队列和重启路径的现有生产集成契约；
- 旧 AgentRun、会话消息、图片与压缩证据中的真实临时持久化往返；
- 使用生产入口得到的模型请求归一化和 HTML 字符串投影；
- D3 的最小隔离 i18n 人工显示检查。

H3 不覆盖真实模型或外部网络、真实浏览器/DOM、页面刷新与重连生命周期、真实线程竞争、完整 usage exactly-once、Runtime 原始事件恢复或发布产物 E2E。特别是第 4 类真实展开生命周期，以及问卷、压缩、图片、队列的真实刷新/DOM 部分，均保留为 H4 验收目标。

## 发布门禁

正式、非 `--skip-tests`、非 `--dry-run` 的发布顺序固定为：

1. 前端门禁；
2. 完整 `pytest`，超时 180 秒；
3. `npm run verify:harness-replay`，独立超时 30 秒；
4. `git diff --check`；
5. Node/Python 语法检查；
6. EXE 构建。

replay 命令返回非零、超时或无法启动时立即阻断，不会进入 EXE 构建。`--skip-tests` 继续同时跳过完整 pytest 与 replay 门禁；`--dry-run` 不执行 replay，现有语义不变。B1、B2 与 C1 的独立 CLI 不在发布脚本中重复执行，因为它们已由默认 `pytest tests -q` 收集；发布门禁显式增加的是默认单 Run CLI 入口、命令接线和 Node 进程本身的验证。

当前 CLI 基线固定为 17 条 fixture、124 个事件、25 个检查点、25 次检查点恢复、4 个显式恢复点，suite replay hash 为 `166a8141c50e8cf17748a04e2b6aa994323c563e9d8d22d3aa4f6d17682030c2`；本轮实测耗时约 730 ms。30 秒独立超时为启动和异常环境留有余量，同时避免发布流程无限等待。

H4 浏览器 E2E 必须使用独立门禁，不与 replay CLI 混合；其测试服务、临时 data、浏览器进程与假上游都必须可靠清理，并设置独立超时。默认 bundle 与经典回退也应分别验证。

## 验证与回退

本阶段发布测试定向验证为 `16 passed, 7 subtests passed`，默认 replay CLI 基线及哈希如上；新增门禁后的完整回归已完成 `1111 passed, 739 subtests passed`。纯文档收口没有改变 `release.py` 或 `tests/test_release_script.py`，因此沿用该完整回归结果。

本阶段可通过撤销 `release.py`、`tests/test_release_script.py` 和本次 H3 收口文档恢复原发布流程；不需要回退既有 Harness fixture/runner、生产 Agent 逻辑或 H3 各专题实现。H4 尚未开始，不属于本阶段回退范围。
