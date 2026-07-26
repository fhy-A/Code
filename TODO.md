# Code TODO

_上次更新：2026-07-26_

本清单只保留尚未完成的工作；已交付内容统一查阅 `CHANGELOG.md`。

---

## P0 · workbar 上线后收口

- ~~workbar品牌统一为小写字母~~ ✅ Code 部分已完成
- ~~确定正式 API 上游、模型组合与定价方案~~ ✅ BoxYing + ByteCatCode，9 款模型
- ~~更新重启机制修复~~ ✅ v0.5.23 改为 batch 方式，待 v0.5.24 端到端验证
- 创建令牌时选择模型限制加入供应商级联下拉框
- 确认 workbar 服务器国内可访问性
- 开发推送 `GENERATE_DEFAULT_TOKEN` + `QuotaForNewUser` 配置
- 寻找 Gemini 替代渠道（LinkAI 不可用）
- ~~`tests/test_new_skills_routing.py` `sys.exit(0)` 导致 pytest 无法收集用例~~ ✅ 已加守卫 + 同步修复 updater 测试签名
- 完成 workbar 品牌 Logo、首页内容与用户文档。
- workbar登录/注册页改造
- 配置并启用企业域名邮箱。
- 完成生产环境运维闭环：备份、监控、告警、安全检查与恢复演练。
- 完成商业主体、经营许可和后续支付渠道升级准备。


---

## P1.5 · 会话导入收尾

- ~~在新侧栏中把 `source` 仅作为来源徽标/筛选信息，不再生成 Codex / Claude Code 二级分组~~ ✅
- Codex 导入的模型名提取（turn_context.model） ✅
- 导入时更新时间戳为当前时间 ✅
- Codex 导入内容块类型兼容（input_text/output_text/text） ✅
- 导入窗口交互：标签切换即时 + 搜索 + 全选/多选 ✅

## P1 · Code 核心能力

- 排查 workbar 网关/上游渠道兼容问题：切换到新中转站后出现「该令牌无权访问模型 deepseek-v4-pro」授权失败，且疑似渠道对模型名映射、工具调用格式（tools/tool_choice）转换与原本地 New API + deepseek 组合不一致。需核对令牌实际授权模型、渠道对工具调用的支持情况，并明确 Code 自身运行链路建议先用已验证组合以隔离变量。
- ~~修复 AgentRun”过程性承诺被误判为完成”~~ ✅ v0.5.29 三分类逻辑：空文本+有思考→continue、空承诺检测（限2次）、error_code 体系
- 排查流式输出不流畅：回复呈「一段文字一段文字」块状跳出，而非平滑增量。需确认是上游渠道 SSE 分块粒度、Code 事件缓冲聚合节奏，还是前端渲染节流导致；与新接入渠道同时出现，需一并纳入渠道兼容排查。
- 实现统一委托 `Context Envelope`：为模型子任务与用户并行任务提供受限、可预算、可审计的上下文。
- ~~增强错误分类与恢复建议~~ ✅ v0.5.29 后端 error_code 7 分类 + 前端 _errorCodeDisplay 映射 + _formatAgentError 差异化展示
- 重做登录后的新手指引，使 workbar 授权、Key 获取、模型选择与首次任务形成连续流程；旧版指引已移除。
- 加强 Skill 执行证据校验，避免只输出结论而未实际完成 Skill 要求。
- ~~**完成 Codex 风格项目/会话界面第二阶段**：移除 `Project > Source Group > Session` 和 `__unclassified__`；改为 `Project > Session`，每个项目默认显示 3 条最近会话，当前会话始终可见，并提供“显示全部/收起”~~ ✅
- ~~**完成会话运行目录闭环**：项目选择、当前会话、文件树根目录和 Agent 工具 `cwd` 必须保持一致；未归属会话继续使用自身 `cwd`~~ ✅
- ~~为上述界面补齐中英文即时切换、窄屏布局和来源徽标，并按人工测试步骤验证后提交~~ ✅
- 继续拆分 `app.js` 第四阶段，迁移剩余高耦合的会话与运行时逻辑。
- 补全 workbar 用量体验：在不暴露敏感信息的前提下展示账号、会话和任务维度的 Token / 成本信息。
- ~~**EXE 安装路径与桌面快捷方式**~~ ✅✅✅ v0.5.27→v0.5.28 端到端更新重启验证通过

---

## P2 · 规划与自动化

- 在现有 AgentRun / Child AgentRun 上实现结构化计划：步骤依赖、并发槽位、预算、验证证据和恢复状态。
- 结构化计划稳定后，再评估 Cron、Monitor、Workflow 与 worktree 隔离。
- 评估 macOS / Linux 支持与原生客户端形态。
- 准备公开发布所需的产品演示、使用案例和推广素材。

---

详细 Agent 路线：

- [`docs/agent-refactoring-execution-plan.md`](docs/agent-refactoring-execution-plan.md)
- [`docs/codex-claude-code-agent-design-analysis.md`](docs/codex-claude-code-agent-design-analysis.md)
