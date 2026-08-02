# Harness H0-2 脱敏轨迹、兼容夹具与测量基线

采集时间：2026-08-02 19:47（Asia/Shanghai）

基线提交：`c692685`

阶段性质：仅测试、文档和离线校验，不修改生产运行行为

## 1. 阶段结论

H0-2 将 H0-1 的 15 条候选场景固化为版本化的合成轨迹套件，并建立 AgentRun v1/v2/v3、旧会话 JSONL 和经典前端的最小兼容样本。所有夹具均由手工构造的短字段组成，不复制真实会话、截图、模型输出、路径、命令、Key 或上游地址。

本阶段只回答四个问题：

1. 后续 replay 以什么离线格式保存输入、恢复点、检查点和终态预期；
2. 当前读取器必须继续接受哪些旧格式事实；
3. 夹具提交前如何自动拒绝凭据、私有路径和真实服务 URL；
4. 在还没有规范 reducer 和浏览器 E2E 时，哪些耗时可以真实测量，哪些不能冒充为用户体验指标。

事件契约、旧事件适配器、状态不变量、reducer、影子投影和生产协议升级均不属于 H0-2。

## 2. 轨迹套件格式

事实源：

- `tests/fixtures/harness/trace-suite.json`
- `tests/fixtures/harness/trace-suite.schema.json`
- `scripts/verify_harness_fixtures.py`

顶层字段：

| 字段 | 含义 |
| --- | --- |
| `fixtureVersion` | 夹具格式版本，当前固定为 `1` |
| `suite` | 套件稳定名称 |
| `source` | 必须为 `synthetic`，禁止把真实会话伪装成测试夹具 |
| `clock` | 固定合成时钟说明 |
| `fixtures` | 独立场景列表 |

每个场景包含：

- `name`：可长期引用的 kebab-case 场景 ID；
- `tags`：用途标签，不参与生产协议；
- `initialSnapshot`：开始状态和初始事件游标；
- `events`：保持当前 `{seq, type, data, createdAt}` 信封的合成耐久事件；
- `recoveryPoints`：页面刷新、轮询断线或服务重启的离线切入点；
- `checkpoints`：指定事件前缀后应达到的状态和时间线；
- `expectedTerminal`：终态与最后一个终态事件。

校验器要求单场景 `seq` 从 1 连续递增、事件名称来自 H0-1 的 22 类现有耐久事件、检查点引用真实序号且时间线与事件前缀一致。当前夹具不是生产 reducer 的输入协议；H2/H3 建立规范 reducer 和 replay runner 后，可以读取该格式，但不能反过来让测试格式驱动生产行为。

## 3. 首批 15 条合成轨迹

当前共 15 条轨迹、106 个事件和 4 个明确恢复点：

1. `plain-text-final`
2. `single-read-tool`
3. `multi-tool-stage`
4. `questionnaire-submit`
5. `edit-authorization-accept`
6. `command-authorization-reject`
7. `auto-compaction-success`
8. `auto-compaction-failure`
9. `cancel-during-model`
10. `cancel-during-command`
11. `refresh-before-first-response`
12. `refresh-during-tools`
13. `server-restart-command-unknown`
14. `poll-disconnect-reconnect`
15. `model-non-action-recovery`

套件规范化 SHA-256 为 `de07e79233f864b00c774b73eb626084136b99395ce907080b2b2888fe5e3750`。该哈希用于发现夹具发生了未说明的机械漂移；场景确需调整时，应连同测试预期和阶段说明一起显式更新。

## 4. 最小兼容样本

### 4.1 AgentRun v1

历史提交 `b8cb63b` 的初始耐久记录版本为 1，不包含 `cwd`、`workspaceRoots`、上下文上限或压缩记录。当前读取器恢复活跃 v1 记录时：

- 工作区根使用旧会话/项目回退逻辑；
- 活跃状态转为 `waiting_credentials`，并保留合法的恢复目标；
- 缺失的上下文和压缩字段使用当前安全默认值；
- 不原地改写旧记录。

### 4.2 AgentRun v2

历史提交 `abf3419` 将版本升级为 2，并新增 `cwd` 与 `workspaceRoots`。当前读取器只有在 `version >= 2` 时才把持久根列表交给工作区归一逻辑。v2 仍没有 `contextLimit`、`contextRecoveryRound` 和 `compactions`，这些字段按模型族默认值和空列表恢复。

### 4.3 AgentRun v3

历史提交 `07775a0` 将版本升级为 3，新增 `contextLimit`、`contextRecoveryRound` 和 `compactions`。当前写入版本仍为 3；夹具锁定显式上下文上限、压缩记录和终态结果能被原样归一到当前内存结构。

### 4.4 旧会话 JSONL

`session-legacy-partial.jsonl` 含 3 条旧式有效消息和 1 条模拟异常退出留下的尾部半行。现有 `read_jsonl()` 继续保留三条有效历史并跳过无法解析的尾行，不修改源文件。样本不包含真实会话 ID、附件或用户正文。

### 4.5 经典前端

`classic-frontend.json` 锁定 `src/frontend-entry.js` 的兼容导入顺序、`agent-runtime.js` 与 `app.js` 的末尾顺序，以及 bundle/经典回退两个必要构建产物。该夹具只做兼容事实核对；实际构建正确性仍由 `npm run check:frontend` 证明。

## 5. 脱敏规则

`scripts/verify_harness_fixtures.py` 只读取仓库内 H0 夹具和 H0-1 机器清单，默认不读取 `data/`、用户会话、浏览器、本地配置或网络。

提交门禁会拒绝：

- `apiKey`、`accessToken`、`Authorization`、`Cookie`、请求头、密码和 Key 列表字段；
- Bearer 值、`sk-` 形式凭据和常见明文 Key/Token 表达；
- `C:\\Users\\...`、`/Users/...`、`/home/...` 私有用户路径；
- 除 `.example.test` 和 `.example.invalid` 外的 HTTP(S) URL；
- 超过 2048 字符的单个夹具字符串；
- 少于 10 个场景、重复名称、未知事件、非连续序号、漂移的事件信封或错误检查点。

示例 ID、模型、文件内容和命令均使用 `fixture-*` 或短的无副作用占位值。扫描不是生产日志脱敏器，也不能代替 H6 的公开字段白名单；其职责仅是防止测试夹具把真实信息提交进仓库。

## 6. 当前测量基线与限制

### 6.1 可重复的离线事件工作量

命令：

```powershell
python scripts/verify_harness_fixtures.py --benchmark
```

本机一次采样结果：

| 合成事件数 | 规范化遍历耗时 | 固定哈希 |
| ---: | ---: | --- |
| 100 | `0.274 ms` | `fb7a6439a77f41fa0e3b2001a611bc8b383e7e2b28f7dd573b22156304631a3c` |
| 1,000 | `2.392 ms` | `989cdffa4b0734d5502280a038dc225f6aabf4e4145bcbd6f9979952c068d6b0` |
| 10,000 | `16.331 ms` | `84205dda88862e7bbfff74077f326547648d8cfba4044c53f358dde51c9887d1` |

这里测量的是 JSON 事件的确定性规范化与哈希工作量，不是 UI 投影、DOM 渲染或生产 replay。它只用于记录 H0 工具自身的数量级，不能作为后续 reducer 性能达标的依据。H2/H3 建立真实 replay runner 后，应沿用相同 100/1000/长轨迹规模并重新建立正式基线。

### 6.2 首次发送自动门禁

三个现有定向守卫验证：用户消息在会话创建前完成乐观投影、同一消息对象被复用、延迟刷新不会覆盖活动运行。当前命令墙钟约 `1.56s`，但其中包含 Python/Node 进程启动和源码读取，不能解释为页面首帧延迟。

真实“点击发送到用户消息/等待状态首帧”的指标必须在 H4 隔离浏览器 E2E 中用 `performance.now()` 和稳定 DOM 标记测量，并使用本地假上游；H0-2 不操作用户浏览器，也不把源码测试时间伪装成用户体验结果。

### 6.3 刷新恢复自动门禁

三个现有定向守卫验证：服务端 checkpoint 可恢复、离线墙上时间不进入活动计时、服务重启后复用已完成工具结果且不再次执行。当前命令墙钟约 `2.04s`，同样包含测试进程和本地假上游开销，不代表浏览器从刷新到正确 DOM 的耗时。

真实刷新恢复指标在 H4 测量“页面开始加载到正确状态、计时、游标和执行轨迹同时稳定”的时间；必须同时覆盖默认 bundle 和经典回退页。

### 6.4 基线解释规则

- 当前毫秒数是 2026-08-02 本机单次采样，只作为诊断记录，不设置易波动的 CI 硬阈值；
- 固定哈希、场景数、事件数、顺序、兼容恢复结果和脱敏扫描是确定性门禁；
- 后续优化不得通过丢事件、跳过持久化、缩短历史或绕过恢复来换取更低耗时；
- 首帧和刷新 DOM 基线必须等浏览器 E2E 可重复后再建立。

## 7. 自动验收

定向命令：

```powershell
python scripts/verify_harness_fixtures.py --benchmark
python -m pytest tests/test_harness_fixtures.py -q -p no:cacheprovider
```

初次定向结果为 `8 passed, 6 subtests passed`。完整回归、前端发布门禁和差异检查在阶段提交前另行执行并记入开发日志。

## 8. 兼容、回退和下一阶段

本阶段没有修改 API、AgentRun 写入、会话 JSONL、工具协议、前端状态、用户界面或生产数据。回退时可以整体删除 H0-2 文档、测试、夹具和只读验证脚本，不需要迁移或回写任何用户数据。

H0-2 验收后，H0 的事实与离线兼容基线即具备进入 H1 的条件。下一阶段应单独确认 H1 的版本化事件信封、旧事件适配、状态不变量和未知字段策略；不得在同一提交中直接替换现有运行时或前端投影。
