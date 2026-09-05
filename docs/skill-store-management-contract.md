# Skill Store v2 内部管理合同

本合同描述 CODE-074 Stage 4D D1 的内部变更引擎。它不是公开 API、界面或迁移命令，也不授权操作真实用户 profile。公开管理入口、旧客户端管理写入门禁和物理清理不在 D1 内。

本文末尾的 D2 接线合同描述在该引擎之上新增的显式管理入口；默认开关和真实 profile 操作授权仍独立保持。

## 所有权与显式边界

- `SkillStoreManager` 必须取得当前进程仍持有、与 Store 根一致的 `DataDirOwner`；Store 还必须显式允许写入。管理操作串行取得同一个 registry 文件锁，线程与跨进程竞争均有超时。
- 必须先有合法的 v1 bootstrap Store，再显式执行 `convert-v2`。新建、导入、启动或模块导入均不会自动转换。转换可先完成一个既有 v1 事务：早期恢复必须显式提供原 catalog loader；已完整捕获的晚期恢复只依靠 Store，不重新读取 catalog 或旧目录。
- profile 启停只控制后续 Skill 准入。D1 不修改旧 Run，不中断正在执行或等待恢复的任务，不影响普通、不使用 Skill 的聊天和编码。
- `disabledNames` 是新请求的进一步排除条件，不能扩大 profile 已允许的集合。旧浏览器偏好仅可通过带 `confirmed=true` 的显式 `migrate-preferences` 请求迁入，且该操作只停用，不重新启用已有停用项。
- 管理引擎没有来源扫描、网络、安装依赖或服务重启功能。包输入是明确提供的目录，或独立捕获并复验的 `CapturedPackage`；journal 仅保存规范化 manifest，不保存输入目录的绝对路径。

## 身份、元数据与选择

物理目录仍为 `skill-store-v1`，对象仍使用 `code-skill-revision/v1` 和原来的 `objects/sha256/<prefix>/<digest>/content` 路径。转换不重写 `root.json`、旧 bootstrap journal、旧 Skill 目录或对象字节，`dataRootId`、既有 `skillId`、`installationId` 和 `revisionId` 保持。

管理后的 registry 使用 `code-skill-install-registry/v2`：

- 每个 installation 保留原有身份字段，增加 `enabled`、`uninstalled` 和有界的 `retainedRevisionIds`。当前修订必须属于保留集合；编辑、升级或回退不会移除已保留的修订。
- 每个 binding 增加 `selectedInstallationId`，将“选择了哪个身份”与“该身份当前是否可准入”分开。被选择项停用或卸载时，`activeCandidate` 为空，但选择本身保留。
- 一个 installation 只属于一个 routing alias；alias 按 casefold 判重，每个 alias 最多两个候选。所有同名选择都必须显式完成。
- 被选择的 local 改名后，旧 alias 上的其他候选保持未选择，不因只剩 bundled 就自动启用。停用、卸载和恢复也不会把 alias 自动切换到另一个 installation。
- 编辑 bundled 必须使用 `fork-bundled` 创建 local 身份和副本，不能以 `edit-local` 覆盖 bundled。local 编辑或改名保持自身 `skillId` / `installationId`。新对象中的 Skill 名称及依赖、资源 sidecar 必须与显式新名称一致，引擎不会猜测或改写正文。
- v1 的 source observations 与 tombstones 原样保留为历史事实，不转化成信任或权限。管理生成的新内容由当前事务记录，不把旧来源观察冒充为新修订来源。

## 操作与幂等

内部调用入口为 `apply(operation_key, request, base_generation=..., base_registry_hash=..., package=...)`。每个请求使用精确字段集；未知操作、schema、字段、非法身份或越界资源均拒绝。

| kind | 主要输入与语义 |
|---|---|
| `convert-v2` | 显式转换；必须以转换前 v1 registry 为 CAS 基线 |
| `create-local` / `import-local` | 明确的 alias、revision、包与冲突选择，创建新的 local 身份 |
| `edit-local` | 既有 local installation、完整新包及名称，保留稳定身份 |
| `fork-bundled` | 既有 bundled installation、完整新包及名称，创建 local 副本 |
| `update-bundled` | 既有 bundled 身份、显式离线 catalog 与完整包；catalog 的稳定 ID、目录和 revision 必须对应 |
| `rollback` | 既有 installation、自身保留的 revision、该包名称与冲突选择；产生新 generation |
| `set-enabled` | installation 与布尔 `enabled`；已卸载项必须先恢复 |
| `uninstall` / `restore` | 逻辑卸载或恢复 installation，保留选择、原启停状态、历史和共享依赖 |
| `select-candidate` | 明确 alias 和其中的 installation；不会顺带启用停用项 |
| `migrate-preferences` | 明确确认并提供已知 alias 的 `disabledNames`，只缩减启用集合 |

涉及包或回退的请求使用 `conflict=reject` 或 `select-new`。后者仅用于明确选择新分配到该 alias 的身份；编辑已在原 alias 中但未被选中的候选，不会偷偷改变选择，需单独 `select-candidate`。

`operation_key` 为区分大小写的 1～128 个 ASCII 字符标识，以字母或数字开头，后续允许字母、数字、`_ . : -`。操作 ID 由 profile 根身份与 key 的哈希派生；冻结请求哈希不包含 CAS 基线，也不依赖临时输入路径。

处理顺序为：验证输入结构 → 查找原操作的冻结请求或收据 → 检查新请求的 CAS → 捕获新包 → 写入新事务。

- 同一 key、同一请求：即使后续已发生多次修改，仍返回原操作的同一收据；不重新读取输入包、不要求旧基线仍是当前基线。
- 同一 key、不同请求：`management_operation_key_conflict`，不能改写原意图。
- 不同 key、旧基线：`registry_cas_conflict`，不覆盖更新后的状态。
- 真正的新用户操作必须使用新 key；内容相同的编辑仍是新的操作和 generation，不被误认为重试。
- 原 v1 bootstrap 收据原样保留；新收据记录当时的 generation、结果状态哈希及结果身份，不绑定到未来最新 registry。

## 提交、恢复与中止

事务使用 `code-skill-store-transaction/v2`，同时固定完整 base / target registry、请求及包 manifest。恢复必须验证所有 journal 构成同一根、连续且无分叉的合法状态链；最多允许一个非终态事务。

```text
prepared → captured → objects-published → registry-published → committed
                                │
                                └─ 原子替换 registry.json 是唯一生效点
```

- `prepared`：目标和 manifest 已固定，但包可能尚未完整落盘。若捕获不完整，必须重新提供与冻结 manifest 完全一致的包；来源漂移不会触发重新规划。完整 staged 对象则可直接恢复，不依赖输入目录。
- `captured` 之后：只验证和发布已有捕获物或已发布对象；不因原目录变化重新读取来源。缺失或损坏的晚期捕获保持错误，不用新来源替代。
- registry 原子替换前，读取看到完整旧状态；替换后看到完整新状态。公开 Reader 使用不创建、不修改文件的同一锁，竞争超时返回 `store_busy`；跨越修改的 admission snapshot 在结束时返回 `registry_changed`。
- registry 已生效后，只完成 journal、收据确认和已知暂存清理，不回退 generation。Skill 回退是另一个新操作，不能倒拨 generation。
- 首次 prepared journal 的临时文件在正式发布前中断时，只有显式的同 key、同请求、同基线、同 manifest 重试可以认领该规范化文件。未知临时文件不能被当成原操作或删除。
- `abort` 仅在 registry 生效前可用，记录终态 journal 但不改变当前 registry。它只清理经过归属及内容校验的 staging / temp；短写文件还需原捕获包证明其前缀。已发布对象一律保留，后续由合法事务记录证明其资格。

启动能够识别并恢复已经显式开始的 v2 事务，但不会发起转换。早期包缺失时报告 `management_capture_required`，flag on 不发布可用启动状态，flag off 保留原有失败降级边界；不会在线猜测输入包或进行 lazy repair。

## 保留与容量

对象资格来自当前引用、明确保留的历史修订及已验证事务。未知对象、未知 staging、非法路径、链接 / reparse、hardlink、manifest 或内容哈希不一致均拒绝；清理不能借已知文件名删除不匹配的字节。

D1 不回收旧 objects，不删除历史或归档 Run，不删除共享依赖，也不暴露物理 GC。既有上限继续适用，包括 512 installations / bindings / receipts / transactions、1024 objects、单包文件与字节限制及 Store 总大小限制；达到容量时稳定拒绝，不通过隐式清理腾空间。

已完成的 v6 Run 继续可在无 Reader 时展示；需恢复的 v6 使用冻结的 installation / revision 和原物理资源路径。`skillLifecycle/v2` 精确支持 registry v1 与 v2，AgentRun 和 Session 外层版本不变，未知 registry schema 不兼容放行。

旧二进制回退不等于关闭准入开关。任何真实 profile 转换、启用、备份恢复或物理清理仍需单独确认，不能从本合同推断授权。

## 验证入口

直接证据位于管理、故障恢复、安全、线程 / 跨进程并发四份 `tests/test_skill_store_management*.py`，以及 `tests/test_skill_runtime_startup.py`、`tests/test_skill_runtime_v2_agentrun.py` 和布局合同。覆盖 A→B→C 后重放 A、同 key 冲突、短写与各持久化阶段中断、原位转换、同一 local 身份的等待门禁 / 已完成工具收据 / 资源路径恢复及旧版本读取。

阶段完成的实际测试计数、失败归因与提交事实以开发日志为准，不将未运行的 UI 或真实 profile 操作记为通过。

## D2 显式管理接线

独立入口为 `/api/skill-management/v1`。snapshot 返回 `legacy`、`immutable-v1`、`managed-v2` 或 `unavailable`，以及当前根、generation、hash 和读写能力。已有 immutable Store 不回落到 mutable Skills；旧管理路由明确返回升级要求。flag OFF 保留管理只读、旧 Run / 原收据恢复和普通无 Skill 任务，不启动转换或依赖安装。

| 请求 | 用途 |
|---|---|
| `GET /` | 只读管理 snapshot |
| `GET /installations/<id>?dataRootId=...&revision=...` | 精确读取安装的保留修订 |
| `GET /installations/<id>/files?dataRootId=...&revision=...&path=...` | 精确读取有界文本资源 |
| `GET /receipts/<key>?dataRootId=...` | 当前指定根的原操作收据 |
| `POST /preview` | 只读构造规范化请求、完整材料与原 CAS 基线 |
| `POST /operations` | 以固定 operation key 提交或恢复原请求 |
| `GET /dependencies?dataRootId=...` | 只读查看唯一依赖操作标记 |
| `POST /dependencies/check`、`plan` | 指定 root / installation / revision / capability 的只读检查或计划 |
| `POST /dependencies/execute`、`cancel`、`recheck` | 确认执行服务器计划、请求取消或显式复检已退出操作 |

POST 必须携带 `protocol=skill-management/v1` 和 JSON。重复 / 非法传输头、跨源请求与超限正文明确拒绝；提前拒绝且关闭连接时发送 `Connection: close`，避免客户端复用已关闭连接。精确读取不接受遗漏身份或重复 query 值。

每个管理请求先核对根身份和同 key 的原请求 / 原收据，再处理真正新操作的 CAS 与材料；原 journal 恢复使用其冻结基线。冲突不会自动换基线重试。编辑提交完整 `SKILL.md`，保留未知元数据；未编辑资源沿用原对象字节。改名仅更新必要的显式 sidecar Skill 身份。目录导入和 packaged catalog 更新均使用明确的本地材料，不扫描来源或访问网络。

现有 Skills 设置布局承载安装身份、显式候选选择、修订回退、启停、逻辑卸载 / 恢复和依赖操作。bundled 编辑生成本地副本；转换与浏览器停用偏好迁入需要显式确认。编辑器保存原 CAS、完整文档和未编辑依赖文件，root / server 变化或冲突时保留草稿；过时的详情 / 列表响应不会覆盖新选择。网络结果不明时只重试原 key / 原请求。

## D2 模型依赖闭环与唯一未结清标记

`check_skill_dependencies` 可返回只属于当前 Run 和精确修订 / capability 的服务器计划。`run_command` 新增可选 `dependencyPlan` 引用；使用它时 `command` 必须为空，实际 argv 始终来自服务器保存并复验的计划。原无该字段的工具协议继续读取，旧 pending authorization 不因新 bypass 路径而被决定。

- 计划只选择当前能力的必需 Python / Node 声明，不自动安装 optional 或全部能力。系统软件、PATH、全局包装与凭据配置不属于该计划。
- bypass 的有效计划直接执行；accept 继续使用原授权，read 的原工具权限仍保留。缺失、失败、忙碌或不确定返回工具事实，由模型决定继续、说明或询问。
- Store 的 DataDirOwner 仍是写者前提。安装与新 Skill 准入 / 恢复共享互斥边界，检查已加载及尚未加载的非终态 Run；请求者已有相关绑定、普通命令、并行工具或其他 Skill 使用者时拒绝进入。
- 唯一标记为 `DATA_DIR/skill-dependency-operation.json`，大小上限 64 KiB，使用原子替换。它绑定 root、installation、revision、manifest、capability、请求者和计划指纹；状态仅 `running → exited → settled`，新操作替换已结清标记，不构成通用队列或历史日志。
- 第一次目录或安装副作用之前先落盘 `running`。专用 Python worker 在读取计划之前进入 Windows Job；执行器依赖该 Job 对安装器及后代的约束，并以其活动进程计数作为退出门禁。主进程退出不足以结清，必须确认 Job 活动进程为零。取消、超时或残留后代会得到真实失败事实；不会宣称环境已还原。该机制的已验证样本与外部进程覆盖限制见下节。
- `exited` 之后只有同目标复检和持久绑定成功才能写 `settled`。读取持久标记也校验状态、结果与 `writerExited=true` 一致，重新计算过的 checksum 不能替代退出证明。绑定写入失败保留阻断；同 Run 的再次检查可完成绑定，不必重新安装。显式修复必须取得新计划，旧计划一经消费不可重放。
- 重启遗留的 `running` 保持未知，不根据 PID 不在或检查 ready 自动清除。没有 force、自动重放或删除整个环境的恢复入口；无法证明退出时保留阻断，界面提供操作 ID 与人工核对路径。Skill 修订回退不等于依赖环境回滚。

自动安装目前要求可用的 Windows Job 与本地 Python。应用打包携带 worker 的最小源文件依赖闭包；打包应用仍使用本地 Python 执行隔离 worker。其他平台或缺少受控 worker 时明确返回不支持，不能回落为任意 shell 安装。既有已就绪依赖的读取 / 使用不因此被删除。

直接验证包括 `tests/test_skill_management_api.py`、`test_skill_management_http.py`、`test_skill_dependency_operation.py`、`test_skill_management_frontend.py` 与 `tests/e2e/h4/code074-d2-management-selfcheck.cjs`。浏览器夹具使用合成账号、离线 Markdown fixture 和受限的非 Skill 路由；管理请求与事务为真实服务端链，不把该验收外推为账号、Markdown 或外网模型验证。

## D2 收尾的验证范围与已知限制

真实离线安装、失败 / 取消、后代未退出、绑定持久化失败、兼容和 UI 样本的通过结果，见开发日志；它们不是所有外部程序进程树均已覆盖的证明。唯一 canonical 仍保留原始失败结果，既有 LibreOffice 渲染超时没有在 D2 中修复。

R079 的两次同安装 Office 对照使用额外的合成 fallback profile 环境与输出观测。exe 首级进程及管道约 23.36 秒结束；com 到 60 秒已有有效 PDF，但首级进程及管道尚未结束。两次 Job 观察均只记录到 Python 包装进程，未取得完整 Office 后代归属 / 退出证据；原始 com 聚合字段只描述包装 Job，应按 deadline 和 worker 退出码 60 解读。事后进程枚举、PDF 存在和 `OfficeRestartInProgress=true` 均不能替代完整证明，也不能据此宣称 D2 安装链已证明发生或不存在相同问题。

用户接受暂不追加渲染专项后允许现有 D2 本地提交收尾。该决定不调整实现、提示词、权限、超时、重试、未知写者阻断或默认开关，也不代表渲染修复、全量通过、真实 profile 启用或发布验收。模型对实际失败的后续判断仍受既有边界约束。
