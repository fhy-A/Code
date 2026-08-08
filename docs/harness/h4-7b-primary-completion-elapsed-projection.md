# H4-7B 主任务完成计时唯一投影

## 完成范围

H4-7B 统一主任务、普通排队任务与 detached/background/`/parallel` 回复的耗时展示所有权：主任务及随后真正执行完成的普通排队任务只在各自用户消息后的顶部完成状态展示一次耗时，对应 assistant 页脚只保留 Token 用量；detached/background/`/parallel` 回复不拥有主任务完成状态，继续在自身 assistant 页脚展示一次独立耗时。

中文顶部完成态使用新的 `completedElapsedLabel=用时`，英文保持 `Worked for`。运行中首个模型内容后的 `processedLabel=已处理`、等待模型、工具继续、恢复、暂停、取消和失败等状态文案均保持原语义与调用点。

## 投影所有权修正

原投影的完成状态、执行轨迹和最终回答收集器都会忽略 detached 用户消息，但可见消息投影曾允许 detached 用户更新 `currentUserIndex`。当 `/parallel` 用户消息插入主任务期间时，这会使主任务终答误判顶部完成状态不属于当前 turn，进而把同一 `_responseTime` 回退显示在 assistant 页脚。

修正后 detached 用户消息仍正常显示，但不再接管主任务 turn、完成状态或工具轨迹的所有权；detached assistant 仍以 `includeElapsed=true` 保留自己的页脚耗时。detached 消息插入工具任务时，执行轨迹保持原主任务归组、顺序和展开所有权，不通过 CSS 隐藏、清除 `_responseTime` 或全局移除页脚计时来规避重复。

真实 DOM 契约为：

- 主任务完成状态 `data-completed-run-status` 恰好 1 个，中文为“用时 + 时长”，英文为 `Worked for + elapsed`；主任务 `.response-info` 保留 2 个 Token 指标，`.run-time` 为 0。
- 普通排队消息成为下一主任务并完成后，同样拥有恰好 1 个顶部完成状态，页脚保留 Token 且 `.run-time` 为 0。
- `/parallel` detached 用户不创建完成状态；其 detached assistant 页脚 `.run-time` 恰好 1 个。
- 完整刷新和中英文即时切换后，上述所有权与计数保持，不产生第二份消息、完成状态或耗时。

## 后台耗时持久化

统一后台结果构造入口 `buildBackgroundResultMessage` 只对 `responseTime` 做一次字符串规范化，并把同一个值同时写入顶层 `_responseTime` 与 `meta._responseTime`：顶层供当前页面立即投影，`meta` 供现有 Session 序列化器按既有规则保存并在刷新后恢复。成功与失败后台终态遵循同一契约。

本阶段没有修改 `src/services/persistence.js`、Session JSONL 格式、计时算法、`_responseTime` 的生成方式、AgentRun、Runtime 或事件协议，也没有新增第二套时间事实源。序列化往返后只依赖既有 `meta._responseTime` 恢复；重复保存、读取和重投影仍只显示一个后台页脚耗时。修正前已经丢失耗时的旧持久化消息不迁移、不补算。

## 浏览器证据与人工验收

默认 bundle 与 `/dist/frontend/index.classic.html` direct classic 共用同一计时投影流程。每个场景均在主任务运行期间插入一条普通排队消息和一条 `/parallel`，随后闭合主任务、parallel 与排队任务，并完整刷新：

| 证据 | bundle | direct classic |
|---|---:|---:|
| 顶部完成状态 | 2（主任务、排队任务） | 2（主任务、排队任务） |
| 主任务页脚耗时 | 0 | 0 |
| 排队任务页脚耗时 | 0 | 0 |
| parallel 页脚耗时 | 1 | 1 |
| 主任务 Token 指标 | 2 | 2 |
| 排队任务 Token 指标 | 2 | 2 |
| 刷新 AgentRun POST / Runtime POST / chat / tool 增量 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

用户已在 3011 开发实例完成人工验收：bundle 案例 1、2 和 direct classic 案例 3 均通过；主任务顶部计时唯一、页脚仅 Token，`/parallel` 回复保留独立页脚耗时，排队任务完成态计时正确，完整刷新和中英文切换正常。direct classic 是 3011 下的独立前端入口，不是 3010 正式版或自动 bundle 故障降级。

## 实现哈希

文档收口前冻结、收口后复核的 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `src/agent/subagents.js` | `ead8cbd7eab26b178536d17d7816ad1504309b0a38a4e63a1c1001ba2fd0a1a6` |
| `src/core/i18n.js` | `c2bb8b1dc6faf6d3dad6a8c3ce85d5e890eea859e595f5459769fad5f20f2800` |
| `src/ui/messages.js` | `67565d96d7a438e70fbe4e52f8009ee9d0c97c0ef98b77cd105a5117c24b232f` |
| `tests/e2e/h4/isolated_host.py` | `a35fcb34e6d70acf47b3ae0a16a10e34e4c92803c906365e26f40566f9252455` |
| `tests/e2e/h4/smoke.spec.cjs` | `b28f5a0455345495ce8389ef0ab7065762d7adf45bc77d9c248bef8e2b93be1e` |
| `tests/test_frontend_modules.py` | `17e4d768d11489564d46aa5e3cd996d89b9173ec3769d0cb42c4198036f25211` |
| `tests/test_subagent_frontend.py` | `cee48bdfc6e85cf73868e422851458c9bf805ca6dc5c010e69bdb37ec8633bc8` |

## 验证

同一实现文件形态已经完成：

- 前端相关回归：`230 passed`。
- 标准 H4 连续两轮：各 `39 passed`、单 worker、`retries=0`。
- 完整 Python：`1122 passed, 751 subtests passed`。
- `npm run check:frontend`、Node/Python 语法、`git diff --check` 与资源清理：通过。

文档收口只在上述七个文件哈希不变时执行 H4-7B 前端/后台持久化定向、bundle/direct classic 两条计时 H4、`check:frontend`、语法和 diff 轻量门禁。连续两轮标准 H4 与完整 pytest 沿用同一实现哈希下的有效结果，不描述为文档收口后重新运行。

## 证明边界与回退

H4-7B 只证明修正后新产生的主任务、普通排队任务和 detached/background/`/parallel` 终态耗时在当前页面、完整刷新和 bundle/direct classic 中的唯一投影。它不迁移或补算已经丢失耗时的旧持久化消息，不改变计时算法、排队/并行调度、消息完成顺序、Session JSONL、AgentRun/Runtime 或事件协议，也不证明发布包中的行为。

独立回退只需撤销本阶段七个实现/测试文件增量和四份收口文档；没有数据迁移、持久化格式回退或协议兼容动作。
