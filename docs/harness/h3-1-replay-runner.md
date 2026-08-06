# Harness H3-1：统一轨迹回放器

## 阶段定位

H3-1 先建立独立、确定性的离线回放入口，为后续状态机、任务契约和完成证据提供可重复验证地基。本阶段最初是在 H2-3 真实影子投影验收前提前完成的工具层准备；当前 H2-3 已收口，H3-2A、H3-2B1、H3-2B2、H3-2C1、H3-2C2、H3-2D1、H3-2D2 与 H3-2D3 已继续扩展测试证据，但仍不代表完整 H3 发布门禁已经交付。

回放器只读取仓库内已经脱敏的合成轨迹，复用 H2-1 的纯 Run reducer 与 View Model；它不读取 `data/sessions/`，不调用模型、工具、网络或浏览器，也不修改 AgentRun、会话 JSONL 和前端状态。

## 入口与用法

统一入口：

```powershell
npm run verify:harness-replay
```

定向回放：

```powershell
node scripts/replay-agent-traces.cjs --fixture refresh-during-tools
node scripts/replay-agent-traces.cjs --tag authorization
node scripts/replay-agent-traces.cjs --list
node scripts/replay-agent-traces.cjs --json
```

`--fixture` 和 `--tag` 都可重复使用；同时提供时采用交集筛选。`--json` 输出机器可读的事件数、检查点数、恢复点数、单轨迹状态哈希和整套回放哈希。

## 已冻结的验证行为

每条轨迹都会执行以下检查：

1. 事件序号必须从初始游标连续递增；删除或乱序事件在进入投影前立即失败。
2. 每个事件后的顶层状态必须属于 H2-1 冻结的八类状态。
3. 每个检查点的状态子集和时间线必须与夹具一致。
4. 所有检查点都经过 JSON 序列化恢复并继续回放，终态必须与从头回放完全一致。
5. 显式页面刷新、轮询断线和服务重启恢复点按保存游标恢复；落后游标允许重新收到尚未确认的事件。
6. 每个事件重复投递一次，终态必须保持不变。
7. 规范 View Model 计算 SHA-256 状态哈希；相同轨迹重复运行必须得到相同哈希。
8. 失败输出首个相关事件序号、状态路径、期望值和实际值，不只返回笼统失败。

H3-1 交付时的 H0 基线为 15 条夹具、106 个事件、17 个检查点恢复和 4 个显式恢复点。H3-2A 已在不修改 runner/schema 的前提下增加两条单 Run 轨迹，当前统一单 Run 基线为 17 条夹具、124 个事件、25 个检查点、25 次检查点恢复和 4 个显式恢复点；详见 [`H3-2A 单 Run replay 夹具扩展`](h3-2a-single-run-replay-fixtures.md)。

multi-run 数量独立统计：H3-2B1 的 fixture v1 为 1 个场景、3 个 Run、12 个事件、15 个 schedule 步骤、3 个 fact-marker、4 个检查点及 4 次恢复；H3-2B2 的 fixture v2 为 1 个场景、3 个 Run、21 个事件、21 个 schedule 步骤、0 个 fact-marker、6 个检查点及 6 次恢复。现有 multi-run runner 显式兼容 v1/v2，默认 CLI 仍运行 v1；详见 [`H3-2B1 多 Run replay 关系基础设施`](h3-2b1-multi-run-replay-relations.md)与 [`H3-2B2 Child AgentRun replay 关系契约`](h3-2b2-child-agentrun-replay.md)。三套计数互不合并，且仍未等同于优化计划第 6.3 节所列 15 类最终完整场景。

H3-2C1 另增一套带版本化 evidence profile 的上游失败与 non-action suite：6 条轨迹、26 个事件、16 个检查点及 16 次恢复、0 个显式 `recoveryPoints`。它继续复用现有单 Run replay payload 与 runner，但扩展的 `sourceFacts` 只属于 `h3-2c1-upstream-failure-non-action` v1 evidence profile；Runtime/AgentRun 集成测试直接消费同一 case 数据。详见 [`H3-2C1 上游失败与 non-action 恢复证据`](h3-2c1-upstream-failure-non-action-replay.md)。该数量也不并入默认单 Run或 multi-run 基线。

H3-2C2 再新增独立、严格版本化的旧 AgentRun 持久化恢复 evidence manifest，只引用既有 v1～v4 四份最小 compatibility fixture，不复制或修改源记录。四个版本案例分别核对生产 loader 内部规范化、当前公共 snapshot 与 v4 persisted 三层结果，并各执行两次真实临时磁盘加载；详见 [`H3-2C2 旧 AgentRun 持久化恢复契约`](h3-2c2-legacy-agent-run-recovery.md)。它不是 replay 轨迹，不并入任何单 Run或 multi-run 数量。

H3-2D1 新增独立、严格版本化的七格式图片 MIME evidence suite。PNG/JPEG/WebP 经生产图片投影保持 MIME、data URL 和解码字节不变；BMP/GIF/ICO/TIFF 转为可解码 PNG，并以源选择帧/首页与模型 PNG 的尺寸和规范 RGBA 直接相等作为语义契约。七条消息共用生产序列化、临时 JSONL、模型图片投影和 UI HTML 投影链路；详见 [`H3-2D1 七格式图片 MIME 保留与模型投影契约`](h3-2d1-image-mime-preservation.md)。它同样不是 Run replay，不并入任何单 Run或 multi-run 数量。

H3-2D2 新增独立、严格版本化的手动压缩成功路径 evidence suite。测试执行当前 `app.js` 中 `compactConversation()` 的精确源码切片，而不是公开模块 API；被动 stub 只返回固定摘要或捕获调用，状态变化来自真实切片。捕获的 archive payload 随后交给真实 `CodeHandler.archive_session()`，最终消息继续经过生产持久化、模型上下文和 UI HTML 投影入口；详见 [`H3-2D2 手动压缩成功路径与完整可见历史契约`](h3-2d2-manual-compaction-visible-history.md)。它也不是 Run replay，不并入任何单 Run或 multi-run 数量。

H3-2D3 新增独立、严格版本化的手动压缩失败与持久化边界 evidence suite，并在生产侧固定目标 Session 所有权、统一 per-Session 保存链、非阻断 archive 警告、两次自动保存、显式保存重试、脱敏有界错误和可靠操作锁清理。suite 固定 19 个场景，hash 为 `50ff1567e7477d6438bfc7e8175a3936f04177a089a4b4ae5acc0a93a0a2a657`；详见 [`H3-2D3 手动压缩失败与持久化边界`](h3-2d3-manual-compaction-failure-boundaries.md)。它同样不并入 Run replay 数量。

## 测试与回归

- `tests/test_harness_replay.py` 覆盖全量回放、按名称/标签筛选、重复哈希、检查点恢复、重复投递、删除事件、乱序事件、检查点差异与空选择错误。
- `tests/test_harness_multi_run_fixtures.py` 与 `tests/test_harness_multi_run_replay.py` 独立覆盖多 Run fixture/schema、身份关系、固定 schedule、每 Run 生产投影、复合 cursor 恢复、重复投递和定向首差异路径，不改变单 Run 测试语义。
- `tests/test_harness_child_multi_run_fixtures.py` 与 `tests/test_harness_child_multi_run_replay.py` 覆盖 fixture v2 的 Root/Child 身份分支、四方父子映射、Child 终态与父工具结果独立顺序、提前结果拦截、复合恢复和专属首差异路径；v1 测试与哈希保持不变。
- `tests/test_harness_upstream_failure_fixtures.py` 与 `tests/test_harness_upstream_failure_replay.py` 覆盖 H3-2C1 evidence profile、401/429/502/首响应超时、empty/reasoning-only 当前顺序、检查点恢复、重复投递和专属首差异路径；`tests/test_model_runtime.py` 与 `tests/test_agent_runtime.py` 使用同一 case 数据驱动本地假上游并对照当前生产分类与规范事件。
- `tests/test_harness_legacy_agent_run_recovery.py` 覆盖 H3-2C2 manifest/schema、固定缺失字段、loader/snapshot/persisted 分层结果、两次真实磁盘加载、v1 重启事件自动持久化、v2～v4 显式写回、输入不变性、副作用隔离和专属首差异路径。
- `tests/test_harness_image_mime_preservation.py` 覆盖 H3-2D1 严格七格式矩阵、同一消息的序列化/临时 JSONL/模型/UI 生产链、3 个原样字节保持案例、4 个尺寸与 RGBA 等价转 PNG 案例、重复稳定性、零外部副作用和专属首差异路径。
- `tests/test_harness_manual_compaction_visible_history.py` 覆盖 H3-2D2 精确源码切片执行、一次性 confirm、完整 archive payload、真实临时归档、最终 JSONL、模型上下文旧消息排除、UI 可见哨兵、确定性哈希、零外部副作用和专属首差异路径。
- `tests/test_harness_manual_compaction_failure_boundaries.py` 覆盖 H3-2D3 的 19 个失败、Session 切换、保存恢复、响应丢失、pending 阻止、显式重试与操作锁异常场景；每条场景冻结调用顺序、marker、最新状态保存、UI、脱敏、监听器清理和专属首差异路径。
- 原有 `tests/test_run_projection.py` 继续保留纯 reducer/View Model 的细粒度契约测试。
- 新测试由默认 `pytest` 完整回归自动执行；发布脚本门禁尚未在本阶段修改。

## 兼容与回退

- 不增加或迁移持久化字段，不修改旧 AgentRun、会话 JSONL、工具协议、默认前端或经典回退页。
- `scripts/replay-agent-traces.cjs` 与对应测试、`package.json` 命令可独立删除，生产行为不受影响。
- H3-2B1 的 v1 schema/suite/tests、H3-2B2 的 v2 schema/suite/tests 及 multi-run runner 的对应版本分支均可按阶段独立回退，不影响单 Run runner 或生产行为；删除 v2 分支不会改变默认 v1 CLI。
- H3-2C1 的独立 evidence schema/suite/tests 可单独删除；其 `sourceFacts` 不属于默认 fixture v1 协议，回退不需要修改默认单 Run runner/schema、B1/B2 或生产数据。
- H3-2C2 的独立 manifest/schema/test 可单独删除；它只引用既有 compatibility fixture，不修改生产持久化协议、默认单 Run runner/schema 或 multi-run 基线。
- H3-2D1 的独立 evidence fixture/schema/test 可单独删除；它不修改生产图片投影、会话 JSONL、既有图片测试、默认单 Run runner/schema 或 multi-run 基线。
- H3-2D2 的独立 evidence fixture/schema/test 可单独删除；它不修改生产压缩状态机、archive handler、会话 JSONL、模型/UI 投影、默认单 Run runner/schema 或 multi-run 基线。源码切片哈希变化必须触发人工语义复审，不能机械更新。
- H3-2D3 可按阶段整体回退生产压缩/消息/i18n 改动、三个 D3 evidence 文件、必要的旧源码断言适配和 D2 受控重基线；它不新增 Session JSONL 顶层结构、HTTP endpoint、AgentRun/Runtime 或 replay 协议。回退 D2 基线时必须同时恢复切片、fixture 和测试文件哈希。
- H2-3 曾评估的实验性 completion Guard 已撤回，不属于 H3-1，也不作为当前 H3 正确性的前提。

## 后续边界

1. H2-3 真实影子采样已经收口，H3-2A 已先固化同轮多工具取消和命令失败后模型恢复两条单 Run 轨迹。
2. H3-2B1 已完成 `queue-parallel-multi-run-relations` 的独立多 Run 回放基础设施、静态身份关系、固定顺序、复合恢复与幂等契约；它不证明真实 queue/background/UI/usage 生命周期、DOM、刷新、Runtime 原始事件或发布门禁。
3. H3-2B2 已完成 `child-agent-out-of-order-terminal-parent-results`：严格 v2 身份图、四方父子映射、Child 终态与父工具结果独立顺序、复合恢复和幂等契约已经冻结；它不证明真实并发、worker、usage exactly-once、DOM、刷新或 Runtime 原始事件恢复。
4. H3-2C1 已完成 401、429、502、首响应超时、empty 与 reasoning-only 的独立证据 suite：离线 replay 证明合成事件投影，本地假上游集成证明当前 Runtime 分类和 AgentRun 事件顺序；它不证明真实网络、所有状态 fallback、浏览器、刷新或 Runtime 原始事件恢复。默认 suite 的 `model-non-action-recovery` 仅保留为历史投影样本，当前生产精确顺序以 H3-2C1 为准。
5. H3-2C2 已完成既有 v1～v4 最小 AgentRun 的缺字段恢复契约：四份源 fixture 哈希和显式缺失字段固定，生产 loader、公共 snapshot、v4 serializer 与两次临时磁盘加载闭合；它不证明损坏记录、Session JSONL、worker/工具外部状态、模型、网络、浏览器或发布门禁。
6. H3-2D1 已完成七格式图片证据：PNG/JPEG/WebP 原样字节保持，BMP/GIF/ICO/TIFF 以尺寸和直接 RGBA 相等证明语义转 PNG，JSONL 与 UI HTML 保留原格式；GIF/TIFF 只覆盖首帧/首页，ICO 只覆盖单尺寸，转换 PNG 编码哈希仅作诊断。它不证明 SVG/AVIF/HEIC、恶意输入、真实浏览器、刷新、模型、网络或发布门禁。
7. H3-2D2 已完成手动压缩成功路径证据；H3-2D3 进一步完成 19 个失败与持久化边界场景、Session 绑定、最新状态重试、响应丢失收敛、failed+persistence failed 正确显示和异常锁清理。D3 仅受控更新 D2 切片 SHA、长度、replayHash 与文件哈希，源历史、最终 messages、archive、save、model context 和 UI 等领域哈希全部不变。两阶段仍不证明真实网络、真实摘要质量、页面刷新、完整 DOM 生命周期、Runtime、H4 或发布门禁。
8. 关键轨迹稳定并覆盖完整场景后，再单独确认 replay 发布门禁和 H4 隔离浏览器 E2E；刷新恢复已知限制继续留在 H4，不因 D3 自动或隔离显示证据而标记为通过。
