# 同 Session Goal 收尾合同（CODE-080）

本说明对应同一 Code Session 内的多轮相关任务。完成仍由 Goal v2 的条件、证据覆盖与成功事件决定；它不是根据最终回答猜测完成的通用验收引擎。

## 最新上下文与关系绑定

- 每次前台模型请求由服务端重新读取同 Session 的 Goal，插在既有 system/developer 安全指令之后。压缩不会删除下一次请求重建的投影；前端不再把起点缓存的 Goal 快照注入模型请求。
- 投影包含 goalId、revision、step/criterion ID、状态、已有证据代表性摘要及其来源/省略数量、gate 原因。JSON 中的目标、理由和证据是数据，不是新增授权。工具来源只证明记录出处，不表示系统独立验证了测试或用户验收。
- 服务端投影按序列化后的 24,000 字符上限裁剪，保留 ID 并声明裁剪/省略数量。`goal_read` 只读取当前 Run 绑定的 Session：`stepId + offset` 读取一条条件及证据摘要，`textOffset` 按字符游标读取长步骤/条件描述（每段至多 400 字符，以返回游标为准）；不带 stepId 时 offset 按字符游标分段读取目标。返回 revision、nextOffset/descriptionNextOffset/省略数量；stale goalId/revision 拒绝（显式 goal_cancel 保留原取消优先语义，对当前状态执行原 CAS），不用 goal_create 冒充读取。
- `goal_read` 同时记录本 Run 与 Goal 的 related/status/unrelated 关系、理由和调用出处。这是**模型显式声明且可审计的判断**，不是确定性自然语言分类或用户授权。不能仅因 Goal active 就把新消息当继续任务；成功 Goal 操作也是相关性证据，不能事后改称无关来绕过收尾。同一输入的已声明关系固定，只有新用户消息/steer 才重新判断。
- child、background、缺少已核验前台消息身份的 Run 没有该读取/声明工具或 Goal 写权限。关系声明不改变已有权限、工具预算或 Skill 身份。

## 收尾顺序与上限

1. 正常工作依据用户已确认的目标、范围和必要验收。可选改进、未授权 push/release 不应加入硬条件。剩余工作须指明未满足条件和已授权下一动作；真实主观/授权缺口才问用户。
2. 相关任务走原 Goal 完成工具和可信成功回执；新等待由原 goal_raise_gate 记录条件、等待对象及恢复条件。**历史 gate 不代表当前输入已明确等待**：当前输入仍等待时，用 `goal_read(decision=wait)` 指明未完成 criterionIds，并在 nextAction 记录等待对象和恢复条件；该只读声明绑定输入指纹、当前 revision 和调用 ID，不重复写 gate。若当前授权和证据支持解除等待，须显式 goal_clear_gate 后执行原完成动作。状态/无关声明可以答复，不能改写旧 Goal；暂停、取消和 gate 不因 final 文字自动清除。
3. 有最终回答但去向不明时，只有**一个补查阶段**：最多两个元数据模型轮次；仅允许 goal_read、goal_complete_step、旧记录适用的 goal_complete、goal_raise_gate、goal_clear_gate、goal_cancel，每批最多八个调用。取消保留原身份、权限、理由与 CAS；不得为此开放计划变更或业务副作用。停止 Run 传输仍不隐式取消 Goal；原取消 reducer 保留已有 gate 作为历史状态，不新增 blocked gate。
4. 补查中若明确尚有已授权工作，`goal_read(decision=continue)` 必须指出未完成 criterionIds 和 nextAction，才能回到原 Run 的原工具集合。补查起点不重置，最多八个模型轮次，原工具/权限预算仍生效；不由该状态自动创建 successor Run。
5. 完成成功或已记录去向后只允许无工具最终回答。若补查/继续上限耗尽、模型再次跳过去向或试图在补查里派发业务工具，则记录可恢复原因并停止；相关且可写的 active/draft Goal 使用现有 blocked gate，不伪造完成证据。遇并发修改、取消、暂停、其他 gate、归档/删除 fence 或损坏状态，不覆盖原状态。
6. 新 steer 在恢复旧 final 之前消费，旧完成回执/final 不能回答新输入。消费后重判关系、撤销旧输入的等待确认，并持久化 inputRound；补查已耗尽时给该真实新输入至多两个控制轮次，允许原取消/等待/完成路径，不重置 checkRound、业务续跑或 Skill 修复预算。重复 steer、回执重放及重启不重开窗口；真正的新用户输入才产生新输入窗口。原 pending 工具组仍按已有执行/恢复合同完成后再消费 steer，不撤销已派发操作。

既有 Skill 完成检查先行。最后一步 Goal 完成前，已有 Skill 完成/证据要求须满足；Skill 修复已经消耗且仍无法确认 Goal 时不再打开第二次修复，保守记录阻塞并停止。Skill 授权、证据门禁及 CODE-074 不可变 Skill 跨 Run 限制不放宽，也不保证任何任意 Skill/Goal 组合都能自动成功。

## 持久化、恢复与回退

- Run 新增可选 `goalCloseout`，有字段时为 v1（初始 null）。其后绑定 Run/Goal/revision、输入指纹、关系/调用出处、补查起点/触发指纹、阶段及 gate 的原 revision；处理状态不进入 Goal 生命周期枚举。
- 补查标记在后续模型请求前持久化；读取回执记录在原调用下，重复回执不重置阶段或次数。gate 的 revision/idempotency 输入先落盘，崩溃后沿同一标识核对，不改用新 revision 强写。
- R002 在该可选对象内增加可选 `inputRound` 和 `gateDisposition`（revision / inputKey / sourceCallId）。R001 记录缺少二者时分别按无新输入窗口、无本轮等待确认处理；未知字段、错误类型或未来轮次仍拒绝恢复。当前等待确认只有输入和 revision 都匹配才有效，声明理由与条件保留在原工具调用/回执中。取消事件或等待回执已落盘、工具结果尚未完成时，只重放原已准备控制调用，沿原 CAS/幂等补齐结果；不把恢复当成新操作授权。
- 旧 Run **缺少该字段**时维持旧收尾默认，避免替旧在途工具添加控制合同；下一条新前台请求仍获取新的上下文/收尾合同。旧 Goal 事件、旧 ready_for_acceptance 和 reducer/CAS/幂等不迁移。未知版本、非法字段或越界计数拒绝恢复。
- 回退仅撤回本阶段代码/构建输出；不重写、迁移或批量结束历史 Goal。新工具尚在途的 Run 不承诺被旧二进制自动恢复，应在安全停止点回退并用新前台请求读取既有 Goal。已写入的 blocked gate 是原协议可读事件，不因回退静默清除。

## 验证边界

`tests/test_goal_closeout.py` 使用真实 worker/Goal 函数、隔离数据及替代模型传输，覆盖缺失完成/gate、正常回执与唯一 final、等待/状态/无关/取消、上限、stale revision、重启、gate 提交后崩溃、旧 Run、损坏状态、Skill 顺序及实际 JS 格式化函数。既有 Goal、AgentRun、协议恢复和 Skill 套件检查兼容边界。

基线 worker 在“直接宣布完成”和“说仍缺条件但不记 gate”两种脚本响应下均接受 completed；基线实际 JS 格式化函数将十条条件输出为八条，没有稳定 ID 或截断声明。上述均为隔离可复现结果，不是自然模型任务实证。本阶段不调用付费模型、不访问真实评测 Session、不重启业务服务；缺少真实用户样本的限制保留。

R002 的真实 worker 负控另复现：补查耗尽后已消费的取消 steer 没能取消 Goal；旧 waiting_user + 新相关验收输入的遗漏 final 只请求一次模型便成功结束。修正用例覆盖补查前后与 gate final 期间的新取消输入、旧 gate 的状态/无关/继续等待/解除完成分支、真实 Skill 证据满足后的 steer、四个 worker 重启边界、取消提交后崩溃与读取回执落盘后崩溃。等待关系和验收仍由显式模型声明/原证据合同表达，不声称能确定性理解任意自然语言或验证用户观察的真实性。
