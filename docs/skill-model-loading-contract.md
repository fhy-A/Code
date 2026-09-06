# 主模型按需加载 Skill 合同

本合同描述 CODE-074 的 `model-driven-v1`。`CODE_SKILL_IMMUTABLE_ADMISSION_V1` 与 `CODE_SKILL_MODEL_LOADING_V1` 在未配置或空值时默认开启；`0`、`false`、`no`、`off` 可显式关闭，非空未知值仍按关闭处理。主模型按需加载仍要求 immutable admission profile 可用。直接 server、Code Dev 与打包 launcher 复用同一解析和启动入口；`CODE_SKILL_COMPLETION_ENFORCEMENT_V1` 独立且继续默认关闭，其它实验开关不随之开启。

默认开启沿用既有 DataDirOwner、首次 immutable 初始化与事务恢复，不自动转换为 managed-v2、不确认冲突来源，也不重置启用、选中、修订或浏览器旧停用选择。已有本地 Skill 和旧记录保持原兼容边界；来源未确认、损坏或未完成事务继续按原流程阻断或要求处理，不静默修复。真实服务启停、旧数据显式转换及旧二进制回退仍需相应操作授权。

打包入口的新安装沿用原内置 Skill 同步再初始化；直接 server / Code Dev 指向没有旧 Skill 目录的空数据根时，仍保留 `legacy-root-missing` 来源阻断，共享开发目录仍保留来源确认要求。默认开关不能代替这些来源决定。

## 发现与加载

- heartbeat 继续公布 `skillActivationProtocol: canonical-v1`，另以精确值 `skillLoadingProtocol: model-driven-v1` 协商新模式。新请求使用 `skillActivationRequest.schemaVersion=2`；未协商的旧请求不能在启用的新模式下悄悄采用另一种选择方式。
- 服务端从已选中、可用且未停用的 immutable bindings 冻结目录，向本次执行的主模型提供名称和真实描述。名称冲突、不可执行描述与客户端进一步停用项不进入目录；描述只是发现数据，不授予权限。目录仍遵守既有条数、正文和 token 上限。
- 主模型可以不使用 Skill，也可以开始时或普通工作中途单独调用 `use_skill({name, role:"owner"})`，之后最多追加一个 `role:"modifier"`。没有格式/关键词语义路由、独立选择模型、卸载、owner 替换或权限恢复。
- 经用户确认，`dispatching-parallel-agents`、`subagent-driven-development`、`executing-plans`、`writing-plans` 在新模式中具有普通加载资格，不再标注“仅显式调用”。旧协议仍保留原静态规则；这不是委托授权或 Skill 元数据迁移。
- `/skill` 保留显式独占。服务端在首次模型请求前完成一次真实加载操作，保存原始工具事件；不伪造模型的 assistant/tool 消息。未知或不可用的显式目标产生失败加载记录，不替换目标。
- 对已经加载的 Skill，仅传 `name` 的 `use_skill` 继续原受控资源读取路径；带 `role` 的重复请求返回原加载收据。加载正文自身不会安装依赖或运行资源。

## 权限与兼容边界

- 新加载继续取当前工具与 Skill 声明的交集。既有 Goal 元数据控制工具保持原独立规则。已被移除的工具不会因后来追加 Skill 而返回。
- 既有 task 规则继续有效：用户没有明确请求委托，且加载到当前时没有任何 Skill 声明 task 时，移除 task。此限制在每次追加时单调保持；后来声明 task 的 modifier 不能恢复此前已收回的权限。
- 权限模式、工具预设与用户原授权照旧；目录中出现某个 Skill，不代表当前模式获得 `use_skill` 或其它工具。child 继续原有 Skill 工具限制，不继承新的加载协议。
- 新加载必须是本轮唯一工具调用；混合批次中的新工具均拒绝，不能先产生相邻文件写入或子任务。待决授权、输入、证据门禁、活动进程、其它非终态工具或已开始的完成修复阶段不能被新加载替换。
- Store 读写和 D2 依赖操作继续原 mutex / owner / revision 规则。有未结清依赖写者时不能新加载；已有绑定、已运行普通命令或其它不满足静止条件的请求不能用后加载 Skill 绕过 late-install guard。bypass 下有效依赖计划仍走原授权路径，其它模式和旧 pending 不放宽。
- 已有 owner completion 计划和证据义务保留。若追加会让原义务不可执行或产生歧义，拒绝该追加；不清空旧证据、不重建已开始的修复轮次。

## 持久记录与失败

新运行使用 **AgentRun v7**，增加 `skillLoading.version=1`，并保留既有 `skillLifecycle/v2` 作为当前已加载集合的投影。Session 格式不变。加载记录保存目录身份、原 prompt 模板、原工具集合、委托意图和最多两份已验证的正文/身份/声明捕获；每份带原 `callId`、来源、角色和确定性收据。

一次成功提交同时落盘正文、固定 revision、系统提示、收窄工具、当前 lifecycle、completion 状态和原调用的成功收据。正文放入受控系统提示，避免被通用工具结果截断；工具结果只报告事实与收据。每个工具 execution 保存加载数量前缀 `skillLoadCount`，恢复和重放只使用该时刻的身份集合。取消前尚未执行的工具和委托记录同样保存前缀。先前普通结果不会成为后来 Skill 的完成证据。

- 失败于原子替换前：读回确认仍是原记录才还原内存，返回明确失败，原正文、工具和收据保持。
- 原子替换后响应失败：若读回等于完整候选，承认已提交并返回原收据，不补做一次加载。
- 无法判断替换结果：本进程停止继续写入、恢复或重放该 Run；重新读取磁盘中的精确记录后才能恢复。不会在不确定状态上覆盖一份猜测记录。
- 恢复校验 loading/lifecycle/prompt/tools 的一致性、原成功 execution 收据、每条调用前缀以及非终态的 pinned 对象。未知版本、半记录、篡改或身份冲突均拒绝。
- 首次加载使用 Run 开始时冻结的目录：registry 变化会拒绝新的加载，给出事实错误，不自动改选新版。已加载对象及重复原请求继续固定 revision，不受后来停用或选版变化影响。

## 展示、OFF 与回退

耗时标题不再显示 Skill 胶囊。真实 `use_skill` 操作沿用普通工具轨迹，显示“加载 Skill / Load Skill”和名称，并沿用运行、成功与失败状态。显式加载只记一次；仅有旧 active 元数据、缺少加载事件的历史运行不补造工具调用。

新二进制在加载 flag OFF 时仍可读取 v7 和其固定对象；OFF 只阻止新协议准入，不抹掉已完成加载。已有 v5/v6 保持其原读写格式和行为，不迁移为 v7。支持范围止于此：旧二进制不支持 v7，回退前须排空相关运行并保留完整数据；不能改写 version 或删除 loading/lifecycle 字段来伪装兼容。若未排空而直接使用旧二进制，原 lifecycle 版本门禁会明确拒绝，不能当作成功恢复。

## 可复验边界

- `tests/test_skill_default_enablement.py` 验证新进程未设/空值/显式开关、import 零初始化、三个真实入口的 owner/Skill 启动段以及合成新旧数据根；监听、托盘与后续无关后台工作在夹具中隔离。启动恢复矩阵和 HTTP 测试继续验证事务、损坏、独立 OFF、协议拒绝与固定对象保留；旧 v5/v6 样本仅在其显式旧模式下构造，不把整个测试环境切成旧默认。
- `tests/test_skill_model_loading.py` 覆盖真实对象捕获、目录/普通与中途加载、角色边界、显式与四个新资格、证据/completion、单调 task 权限、混批、取消、重复、失败持久化和恢复。
- `tests/test_skill_dependency_operation.py` 包含 v7 的离线真实 pip 安装、安装后复检、绑定失败后的只复检恢复、继续执行、原权限与 late-install/未结清写者边界。包与数据均为新合成样本。
- `tests/e2e/h4/code074-skill-model-loading-selfcheck.cjs` 使用真实 HTTP、前端、AgentRun 和 Skill 操作；上游的模型选择是明确标注的模拟结果。覆盖实时、真实 UI 终态、失败、刷新、OFF 展示、旧 v6 无伪造事件，以及中文深色/英文浅色。

这些结果不等于真实模型自然任务验收，也不覆盖 Office 渲染或生产全量回归；既有相关剩余问题不据此关闭。
