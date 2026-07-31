# 活动任务交接

## 元数据

- 状态：`active`
- 任务 ID：`upstream-channel-formal-admission`
- 任务名称：现有上游渠道正式准入与持续评估
- 任务范围：workbar 已启用的 12 条上游渠道，不新增模型分组，不重新录入基础价
- 最近执行 Agent：Codex（可由 Claude Code 或其他遵守项目规则的 Agent 接续）
- 上次更新：2026-07-30 22:30（Asia/Shanghai）
- 当前分支：`master`
- 记录时 HEAD：`d001d08 文档：记录初始令牌自动分组验收`

## 目标与验收条件

### 目标

按模型身份、跨时段稳定性、并发、SSE、Code 工具闭环、错误率、账单一致性和故障切换累计证据，最终给出主渠道、备份、试用、观察或淘汰结论，以及优先级、权重和充值建议。

### 验收条件

- 试用候选：至少 90 次请求、3 个自然日、3 个本地时段、有效成功率不低于 95%；
- 备份候选：至少 200 次请求、5 天、并发至少 2、有效成功率不低于 97.5%，并完成故障切换演练；
- 主渠道候选：至少 500 次请求、7 天、并发至少 5、有效成功率不低于 99%，并完成账单和商务复核；
- 一次短测或后台连通测试不得作为正式准入。

## 事实源

- 已完成事实：`docs/development-log/README.md` 及索引中的最新日期日志；
- 未完成事项：`TODO.md` 的“完成当前渠道的正式准入与持续评估”；
- 人工测试规范：`../../模型定价/渠道采购体系/规范/06_Workbar人工渠道模型测试与协作SOP.md`；
- 首轮汇总：`../../模型定价/渠道采购体系/outputs/20260730/workbar-code-hard-gate-round1/round1-summary.md`；
- DeepSeek 官方对照：`../../模型定价/渠道采购体系/outputs/20260730/workbar-code-hard-gate-round1/deepseek-official-comparison.md`；
- Git 现场：进入 `code` 后运行 `git status --short`、`git log -8 --oneline`。

> 本交接只记录尚未完成任务的进行中差量。与 Git、开发日志、TODO、采购体系记录或可复现结果冲突时，以现场为准并修正本文件。

## 已完成

- 模型人民币基础价、分组倍率和模型广场反算已经完成；本阶段不得重复录入基础价或重新划分模型组。
- 2026-07-30 20:31—21:35 完成单一晚间窗口的首轮 H1 精确指令、H2 流式、H3 Code 文件工具闭环及后台费用核对。
- 12 条渠道首轮分类：
  - 硬门槛通过 4 条：`BoxYing-Codex-Plus`、`BoxYing-Codex-Premium`、`UUAPI-Domestic-OpenAI`、`deepseek官方`；
  - 条件通过 / 观察 6 条：`ByteCatCode-Codex-Value`、`ApiNebula-Codex`、`BoxYing-Claude-Official`、`ApiNebula-Grok`、`ApiNebula-Gemini-Antigravity`、`ApiNebula-Gemini-GCP`；
  - 未通过 2 条：`Unity2-Claude-Max`、`ApiNebula-Claude-Kiro`。
- DeepSeek 官方的 `deepseek-v4-flash` 和 `deepseek-v4-pro` 均通过本轮精确指令、真实流式和文件读取工具闭环；workbar 用户侧账单可以按模型基础价、缓存价和 `1.18x` 倍率反算。
- `BoxYing-Codex-Plus` 和 `BoxYing-Codex-Premium` 定向测试时临时改为优先级 20，用户已确认恢复为 0。
- 已建立可复用的人工测试 SOP、单轮记录模板、首轮汇总和 DeepSeek 对照报告。

## 当前进行中

- 等待用户选择下一个不同本地时段后继续人工扩样；
- 保持首轮结论为“硬门槛筛查”，不提前升级为试用、备份或主渠道；
- 当前不执行浏览器操作，由用户负责 workbar 选择、发送消息、Key 和截图。

## 尚未完成

- 上午、午间/高峰、晚间及必要的低谷跨时段复测；
- 3 天试用、5 天备份和 7 天主渠道所需样本；
- 并发、限流、退避、首请求成功率与最终成功率统计；
- 故障切换和独立故障域验证；
- workbar 与供应商上游账户逐单账单核对；
- DeepSeek 官方高峰期双倍扣费规则；
- 最终渠道等级、优先级、权重和充值建议。

## 修改现场

### 本任务相关

- `TODO.md`：保留渠道正式准入主线，并新增消息流垂直间距待办；
- `AGENTS.md`、`CLAUDE.md`：新增新会话自助启动和跨 Agent 活动交接规则；
- `docs/development-handoff.md`：本活动交接；
- `docs/development-handoff-template.md`：跨 Agent 中立模板；
- `docs/development-log/README.md` 与当天日志：协作机制和阶段事实索引；
- 项目根目录 `AGENTS.md`、`CLAUDE.md`：子项目路由和活动交接规则；
- `../../模型定价/渠道采购体系/`：人工测试 SOP、模板、首轮报告、截图和索引。

### 共享工作区既存修改

记录时 `code` 工作区已有大量未提交文档迁移和发布资料修改，包括 `CHANGELOG.md`、`docs/GUIDE.md` 删除、多个发布说明和 `release.py`。接手 Agent 必须重新运行 `git status --short`，不得恢复、清理或顺带提交不属于当前阶段的改动。

### 临时配置

- BoxYing 两条 Codex 渠道临时优先级：已恢复为 0；
- 其他线上优先级、权重和余额：未修改；
- 浏览器与 Key：始终由用户操作，Agent 不读取真实 Key。

## 验证结果

| 检查 | 结果 |
|---|---|
| 首轮人工硬门槛 | 4 条通过、6 条观察、2 条未通过 |
| DeepSeek 官方对照 | 两个模型 H1/H2/H3 通过 |
| workbar 用户侧费用 | 首轮合计 ¥1.096064；只代表 workbar 费用，不代表采购账户实际扣费 |
| 临时优先级恢复 | 用户确认两条 BoxYing Codex 渠道均恢复为 0 |
| 正式准入 | 尚未达到任何渠道的正式试用、备份或主渠道门槛 |

## 阻塞与待授权

- 当前无技术阻塞；下一轮人工测试等待用户选择合适时段。
- 线上渠道、模型、分组、倍率、优先级、权重和余额修改必须获得明确授权。
- Git 推送、标签和发布必须获得明确授权。
- 不得读取、显示或写入真实 API Key、Access Token、Authorization、Cookie。

## 准确下一步

1. 新 Agent 先读取开发日志索引、最新日期日志、`TODO.md`，并核对 Git 现场；
2. 阅读人工测试 SOP 和首轮汇总，不重新执行已完成的晚间首轮；
3. 向用户确认当前本地时段和本轮可测试范围；
4. 每次只发送一个包含“workbar 令牌、分组、模型、测试消息”的测试卡；
5. 用户回传前台结果、流式体感和后台记录后，分析方核算并追加跨时段证据；
6. 当渠道准入阶段全部完成时，把最终事实写入开发日志和 TODO，随后移除本活动交接文件。

## 禁止重复或不得触碰

- 不重复录入模型基础价，不重新划分现有模型组；
- 不把一次短测、重试后的最终成功或后台连通测试写成正式准入；
- 不操作用户浏览器，不读取或输出真实 Key；
- 不覆盖共享工作区的既存修改；
- 未经授权不改线上配置、不推送、不打标签、不发布。
