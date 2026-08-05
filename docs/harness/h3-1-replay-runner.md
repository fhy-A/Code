# Harness H3-1：统一轨迹回放器

## 阶段定位

H3-1 先建立独立、确定性的离线回放入口，为后续状态机、任务契约和完成证据提供可重复验证地基。本阶段最初是在 H2-3 真实影子投影验收前提前完成的工具层准备；当前 H2-3 已收口，H3-2A、H3-2B1 与 H3-2B2 已继续扩展测试证据，但仍不代表完整 H3 发布门禁已经交付。

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

## 测试与回归

- `tests/test_harness_replay.py` 覆盖全量回放、按名称/标签筛选、重复哈希、检查点恢复、重复投递、删除事件、乱序事件、检查点差异与空选择错误。
- `tests/test_harness_multi_run_fixtures.py` 与 `tests/test_harness_multi_run_replay.py` 独立覆盖多 Run fixture/schema、身份关系、固定 schedule、每 Run 生产投影、复合 cursor 恢复、重复投递和定向首差异路径，不改变单 Run 测试语义。
- `tests/test_harness_child_multi_run_fixtures.py` 与 `tests/test_harness_child_multi_run_replay.py` 覆盖 fixture v2 的 Root/Child 身份分支、四方父子映射、Child 终态与父工具结果独立顺序、提前结果拦截、复合恢复和专属首差异路径；v1 测试与哈希保持不变。
- 原有 `tests/test_run_projection.py` 继续保留纯 reducer/View Model 的细粒度契约测试。
- 新测试由默认 `pytest` 完整回归自动执行；发布脚本门禁尚未在本阶段修改。

## 兼容与回退

- 不增加或迁移持久化字段，不修改旧 AgentRun、会话 JSONL、工具协议、默认前端或经典回退页。
- `scripts/replay-agent-traces.cjs` 与对应测试、`package.json` 命令可独立删除，生产行为不受影响。
- H3-2B1 的 v1 schema/suite/tests、H3-2B2 的 v2 schema/suite/tests 及 multi-run runner 的对应版本分支均可按阶段独立回退，不影响单 Run runner 或生产行为；删除 v2 分支不会改变默认 v1 CLI。
- H2-3 曾评估的实验性 completion Guard 已撤回，不属于 H3-1，也不作为当前 H3 正确性的前提。

## 后续边界

1. H2-3 真实影子采样已经收口，H3-2A 已先固化同轮多工具取消和命令失败后模型恢复两条单 Run 轨迹。
2. H3-2B1 已完成 `queue-parallel-multi-run-relations` 的独立多 Run 回放基础设施、静态身份关系、固定顺序、复合恢复与幂等契约；它不证明真实 queue/background/UI/usage 生命周期、DOM、刷新、Runtime 原始事件或发布门禁。
3. H3-2B2 已完成 `child-agent-out-of-order-terminal-parent-results`：严格 v2 身份图、四方父子映射、Child 终态与父工具结果独立顺序、复合恢复和幂等契约已经冻结；它不证明真实并发、worker、usage exactly-once、DOM、刷新或 Runtime 原始事件恢复。
4. 后续仍需按第 6.3 节逐类核对实际证据，并补齐图片降级、手动压缩、更多上游错误和旧记录恢复等缺口；不能只凭 fixture 名称认定完整覆盖。
5. 关键轨迹稳定并覆盖完整场景后，再单独确认 replay 发布门禁和 H4 隔离浏览器 E2E。
