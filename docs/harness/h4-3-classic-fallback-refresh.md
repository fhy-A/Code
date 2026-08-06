# H4-3 classic fallback 刷新兼容

## 1. 阶段结论

H4-3 已为 classic fallback 直接入口补齐三条同进程模型流式刷新浏览器证据：首个正文增量到达前刷新、已有两段正文后刷新并继续追加、已有两段正文后刷新再取消。classic 页面与默认 bundle 共用同一份生产 `app.js`、`agent-runtime.js` 以及 Session、AgentRun、Runtime 恢复链；本阶段只将 H4-2 的既有浏览器流程参数化为 runtime-aware 入口，没有复制第二套恢复状态机，也没有修改生产代码或协议。

这项结论只适用于直接访问生成的 classic fallback 页面。它不证明 bundle 加载失败后的自动降级，也不证明服务重启、跨进程恢复或其他 H4 生命周期。

## 2. 场景与共用契约

新增的三条 classic 浏览器场景为：

- `classic-refresh-before-first-delta`
- `classic-refresh-after-two-deltas`
- `classic-refresh-then-cancel`

三条 classic 场景与 H4-2 的三条 bundle 场景调用同一组测试辅助流程、合成任务、三阶段流式闸门、模型目录闸门、请求指标、Session JSONL 证据、DOM 时间线及 teardown。入口差异只由 runtime 参数表达：bundle 要求 `data-frontend-runtime="bundle"` 和 `data-code-frontend-ready="true"`；classic 直接入口要求 `data-frontend-runtime="classic-fallback"`，不虚构 bundle ready 标记。

每条场景共同验证：

- 刷新前后复用同一 AgentRun 和 Runtime；AgentRun POST 为 1、Runtime POST 为 0、上游 chat 为 1、工具执行为 0。
- 模型目录闸门仍未释放时，刷新页已经发起 Runtime GET，证明重附着不再被目录刷新串行阻塞。
- user/assistant 投影唯一，不创建第二模型请求或重复 assistant。
- 首增量前刷新后能够继续流式；两段后刷新时，第一个非空 DOM 样本以前缀正文开头，后续样本都以此前样本为前缀，第三段在 terminal 闸门释放前可见。
- 取消只产生一个 AgentRun DELETE；AgentRun 与 Runtime 均收敛为 cancelled，已有正文和唯一暂停说明保留，不出现 `model_completed` 或成功终答。
- 成功终态 JSONL 包含完整正文且不含 `streaming`、`_streamProjection`；取消终态保留既有正文与唯一暂停说明，临时投影字段仍不存在。在途第三片段沿用 H4-2 的诊断边界，不被解释为成功终答。
- 页面错误为 0；每例子进程、端口和临时根清理归零，标准入口无 retry。

## 3. 验证基线

实现复验连续两轮运行标准 `npm run test:h4:e2e`：基础设施自检均通过，浏览器矩阵均为 `9 passed`、`retries=0`。Playwright 部分两轮均约 26.5 秒，完整命令分别约 31.1 秒和 31.3 秒。

classic 三场景的 Runtime GET 观测值分别为：第一轮 8/5/4，第二轮 8/6/4；刷新后取消延迟分别为 238 ms 和 231 ms。这些数值只用于证明本地合成环境确实发生重附着和有界取消，不冻结为跨机器、跨负载或跨浏览器环境的性能阈值。

同轮还通过：

- `npm run check:frontend`
- 前端模块与相关 P0：`199 passed`
- 完整 Python：`1113 passed, 739 subtests passed`
- smoke spec Node 语法及 `git diff --check`
- H4 子进程、端口、临时根和 Playwright output 清理归零

## 4. 证据边界

H4-3 只证明 direct classic fallback 与默认 bundle 共用生产恢复逻辑时的同进程模型流式刷新兼容。它不覆盖自动 bundle-load 失败降级、服务重启、Runtime 原始事件持久化、跨进程恢复、工具流式刷新、问卷/授权、队列/并行/Child AgentRun、图片、压缩、真实 CDN/完整 Markdown、浏览器崩溃、EXE 或发布门禁。

## 5. 独立回退

撤销 `tests/e2e/h4/smoke.spec.cjs` 中的 runtime 参数化与三条 classic 变体，再撤销本专题及本阶段事实源更新，即可独立回退 H4-3。无需修改生产代码、AgentRun/Runtime/Session 协议、持久化数据、H4-1 基础设施或 H4-2 产品修复。
