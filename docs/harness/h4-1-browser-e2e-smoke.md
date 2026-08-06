# H4-1 浏览器 E2E 基础设施与首批冒烟

## 1. 阶段结论

H4-1 已建立隔离、可重复运行的 Chromium 浏览器 E2E 基础设施，并交付三条首批冒烟：默认 bundle 纯文本、默认 bundle 单只读工具、classic fallback 纯文本。唯一标准入口为：

```text
npm run test:h4:e2e
  -> npm run test:h4:infra
  -> npm run test:h4:smoke
```

基础设施自检先验证子进程环境隔离、工具白名单、初始化失败清理与 `stop()` 幂等；任一自检失败都会通过串行短路阻止 Playwright smoke 启动。Playwright 固定单 worker、`retries=0`，不加入 `release.py`。

## 2. 依赖与浏览器基线

- `@playwright/test`、`playwright`、`playwright-core`：`1.62.1`，以精确开发依赖写入 `package.json` 和 lockfile。
- Playwright Chromium revision：`1234`；浏览器版本：`151.0.7922.34`。
- 本机工具缓存：`%LOCALAPPDATA%\ms-playwright\chromium-1234` 与 `%LOCALAPPDATA%\ms-playwright\chromium_headless_shell-1234`。
- 本阶段未下载 Firefox 或 WebKit；`node_modules`、浏览器二进制和测试输出均不提交。

系统 Chrome 版本不属于正式基线。

## 3. 隔离与安全边界

每条测试使用独立临时根目录及其 `data/`、`project/`、`artifacts/`、`home/`、`tmp/`。生产 `CodeHandler` 和本地假上游均绑定 `127.0.0.1:0`，`CODE_DATA_DIR`、`NEW_API_BASE_URL` 和合成配置由隔离 host 显式设置；浏览器拒绝所有非 loopback 请求。

Python 子进程不继承完整父环境，只接收启动所需的 Windows/进程基础字段、隔离的 home/temp 与 loopback `NO_PROXY/no_proxy`。自检证明父进程合成 secret 不进入子进程，且子环境没有未授权的 `KEY/TOKEN/SECRET/PASSWORD/COOKIE/AUTH` 类变量。

工具包装只允许 `action === "read_file"` 且 `path === "fixture.txt"`。其他 action 或路径在委托生产工具入口前计入 `unsafeToolRequests` 并拒绝；允许路径只读取临时 `project/fixture.txt`，实际生产执行器只被调用一次。

启动、context 初始化、失败诊断、context 关闭和 host 停止都处于可靠清理边界。诊断写入和 `context.close()` 失败不阻断 host 清理；控制命令、readiness 和退出等待均有界，强制终止只针对本测试记录的 PID。`stop()` 可重复调用，并验证子进程退出、活跃子进程数为零、两端口关闭及临时根删除。初始化故障注入自检也闭合相同清理证据。

Playwright 内置 trace 保持关闭。失败时只 best-effort 保存脱敏截图、console 和自定义 `sanitized-diagnostics.json`；该文件不是 Playwright trace。

## 4. 三条冒烟

| 场景 | 上游/工具计数 | DOM 断言 | 运行标记 |
|---|---:|---|---|
| 默认 bundle 纯文本 | 1 次 chat、0 次工具 | 用户消息 1、运行态已观察、最终回答 1 | `bundle-ready` |
| 默认 bundle 单只读工具 | 2 次 chat、1 次 `read_file` | 用户、阶段说明、工具、结果、最终回答各 1，顺序固定 | `bundle-ready` |
| classic fallback 纯文本 | 1 次 chat、0 次工具 | 用户消息 1、最终回答 1 | `classic-fallback` |

每条场景都复用真实生产 `CodeHandler`、前端 bundle/classic、AgentRun 和只读工具入口，不复制前端或 AgentRun 状态机。两轮标准入口均先通过 infra 自检，再以 `3 passed`、零 retry 完成 smoke，浏览器测试耗时分别约 `6.0s` 和 `6.2s`。每轮各阻断 4 个非 loopback 请求；清理后无残留子进程、监听端口、临时根或普通 Playwright output。

生产 Markdown 依赖使用 CDN，而测试网络策略会阻断 CDN，因此浏览器上下文注入了最小、确定性的测试侧 `marked` API 适配器。该适配器只用于让隔离冒烟到达真实投影链，不证明真实 CDN 可用性或完整 Markdown 行为。

## 5. 验证基线

- `npm run test:h4:e2e` 连续两轮：infra 自检通过，smoke 均为 `3 passed`、`retries=0`。
- 自检失败短路：infra 返回非零时 smoke 未启动。
- 前端构建与新鲜度：`npm run check:frontend` 通过。
- 前端模块：`169 passed`。
- 完整 Python 回归：`1111 passed, 739 subtests passed`。
- Node/Python 语法、`git diff --check`、凭据/真实路径/非 loopback URL 扫描及退出清理审计通过。

## 6. 完成边界与后续

H4-1 只证明上述三条确定性浏览器冒烟以及测试基础设施的隔离、安全和清理契约。它不证明自动 bundle-load 降级、页面刷新与 Runtime 重连、问卷、授权、停止、排队、显式并行、Child AgentRun、图片、压缩、真实 CDN/完整 Markdown、EXE 或发布门禁。

特别是首个模型正文增量前刷新、已有正文后刷新、刷新后继续流式追加、计时/暂停恢复和同一 AgentRun/Runtime 复用仍是 H4-2 的独立问题，H4-1 不将其标记为通过。

## 7. 独立回退

撤销 Playwright 配置、`tests/e2e/h4/`、`package.json`/lockfile 中的 H4 脚本与精确依赖，以及本阶段文档即可回退 H4-1。生产代码、AgentRun/Runtime、Session JSONL、Harness replay 与 `release.py` 均未修改。
