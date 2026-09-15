# 项目会话批量归档与分组永久删除（CODE-072）

第一阶段提供项目菜单“全部归档”、固定目标的服务端预览、必要时明确停止并归档，以及归档页按稳定项目 ID 筛选。第二阶段在归档分组内增加明确确认的批量永久删除，合同见本文后半部；单项恢复、单项永久删除和第一阶段历史保留，不提供批量恢复或跨项目一键清空。

## 确认与执行合同

- `POST /api/project-session-archive/preview` 接收 `projectId`，失败项重试另传 `retryOf`。服务端从活动 Session 文件读取该项目的目标，返回 `operationId`、一次确认令牌、动作、数量、活动项和固定 ID 列表。客户端不能提交另一组目标。
- 预览只驻留内存，十分钟过期。取消调用 `cancel`，不移动 Session、不停止 Run，也不写批次文件。索引就绪检查沿用已有服务，不改变业务内容。
- `confirm` 必须绑定原操作 ID、令牌和动作。确认后先落盘，再逐项执行；同一项目的并发请求串行化，每项保留独立结果。
- 项目设置、Session 项目位置/创建身份、生命周期代次、新增 Run/队列身份会使该项冲突。预览后新加入的 Session 不会进入旧批次。预览时空闲的项不会因同批另有活动项而获得停止新工作的授权。
- Run 的普通输出、usage、Session revision、mtime、模型轮次、已冻结 Run 的自然结束不使停止确认失效。服务器 Run 第一次投影到浏览器检查点时，只允许原冻结 Run 的身份；浏览器自持轮次另按运行身份追踪。
- 每项在已有停止 fence 内校验；最终移动使用既有 Session lifecycle → AgentRun → JSON 写锁顺序。停止等待不持有这些共享锁。项目迁移和新的 Run 准入受相同 fence/锁约束。
- 活动判定复用原规则：允许静止 paused，保留未完成 Goal；未完成 Goal 本身不被当作需停止的 Run。

## 持久化与恢复

新增数据位于 Session 数据根旁的 `project-session-archive/`，不修改旧 Session 的 JSON 格式。

| 数据 | 用途 |
| --- | --- |
| `operations/<operationId>.json` | 固定目标、确认绑定、动作和逐项进度 |
| `generations/<sessionId>.json` | 已关注 Session 的生命周期代次；预览期仅内存，确认后才持久化 |
| `effects/<operationId>/<sessionId>.json` | 不可变的完成凭据，绑定本批次与本次 archive token |

这些文件仅保存必要 ID、摘要、时间和状态，不复制标题、消息、项目路径、凭据或工作区文件。写入使用临时文件、fsync、原子替换和内容校验；路径链接、损坏状态、缺失的已确认身份/完成凭据均拒绝执行。依赖应用既有的数据根进程所有权，不启动额外调度进程。

批次继续使用原 v1 archive bundle 和 manifest。只有批次的短期单项事务 journal 使用 `code-session-archive-transaction/v2`，附加操作 ID 和预先确定的 archive token；原单项事务仍写 v1。批次 journal 在删除前必须已写完成凭据。恢复也验证绑定并遵守同一顺序，因此响应丢失后，即使用户又单项恢复或永久删除了 Session，旧批次仍可认出已完成项，不会再次归档。

`GET /api/project-session-archive?projectId=...` 只读取已确认批次。弹窗的“读取本批次结果”根据原操作 ID 读取，不重发变更。`resume` 仅继续已确认批次：已完成项不重放；停止中断且仍有非终态 Run 时返回结果不确定，不自动重复停止；能够证明冻结工作已终止时才继续归档。缺失 Session 的 404 不表示成功。

失败、冲突和“已停止但归档失败”逐项保留。重试通过旧批次失败项生成全新预览和确认，成功项以及后来新增的 Session 不纳入重试。结果不确定的项需要先核对该会话，再由用户发起新的明确预览，不能当作普通自动重试。

## 界面边界

预览显示项目名称和稳定 ID；同名项目筛选项用 ID 区分。归档列表、项目选项和搜索使用同一份已加载数据；选中项目最后一项消失时，先复位筛选再更新列表。未归属项目与已删除项目的历史 ID 分开显示。

导航只在本批报告当前 Session 成功、服务端读取明确返回 `session_archived`、且当前导航代次未变化时切换。分页中未出现、无关会话、已经恢复的会话不据此切走。

## 兼容与回退

旧归档不需要迁移，可以直接列出、筛选、单项恢复或删除。完成凭据独立于归档 bundle，因此正常单项删除不会破坏旧批次的去重事实。

回退旧程序前，需要用当前程序完成或核对已确认批次，尤其是 `stopping`、`stopped`、`archiving` 项，并让所有 v2 单项事务 journal 完成恢复；不要直接删除 journal、代次或完成凭据。之后停止当前服务，保留整个数据根备份和 `project-session-archive/` 辅助目录，再启动旧程序。没有未完成 v2 journal 时，旧程序仍可读取原 v1 bundle。

旧程序不维护新代次，因此在旧程序修改数据后再次升级，不能直接恢复旧程序运行前遗留的未完成批次；应核对其逐项结果并创建新的预览。辅助目录保留供审计和已完成项去重，不由本阶段自动清理。损坏或无法核实的事务须先恢复数据完整性，不能通过删状态文件强行继续。

## 隔离验证入口

- `python -X utf8 -B -m pytest tests/test_project_archive_batch.py -q -s -p no:cacheprovider`：父进程不导入 server，子进程使用临时 `CODE_DATA_DIR`，覆盖持续输出延迟确认、新工作/迁移冲突、HTTP 并发、响应丢失、重启阶段、损坏状态及旧 Goal/paused 语义。
- `node tests/e2e/h4/code072-project-archive.cjs`：现有 H4 临时宿主，限定归档接口的写入白名单，覆盖 bundle/classic、中英、390px 窄屏、冷加载筛选、导航保护和原批次读取；自建浏览器/服务/数据根按夹具合同清理。
- 原归档生命周期、项目迁移、前端模块及 i18n 规定检查继续适用。以上入口不会连接真实模型，也不覆盖生产故障或外部程序直接修改数据根的强隔离保证。

- R004 真正进程恢复入口：`python -X utf8 -B -m pytest tests/test_project_archive_process.py -q -s -p no:cacheprovider`。每例进程 A 在持久断点 `os._exit(73)` 后，父进程确认其退出，再以相同临时 `CODE_DATA_DIR` 启动全新进程 B；覆盖已成功/未开始分项、停止完成归档前、bundle 提交凭据前，并核对完成项与已恢复 Session 不重放。该证据独立于前述清空内存表的进程内模拟；停止场景走真实持久准入/取消路径但 `start_worker=False`，不代表真实模型或执行线程停止测试。

## 第二阶段：按归档分组永久删除

归档页的“删除本组归档”先请求服务端预览。预览展示名称、可区分的项目 ID、权威数量和不可恢复提示；处理该分组全部已归档会话，搜索/分页不是授权来源。服务端冻结的清单不包含随后新增归档。页面顶部的删除批次记录只读取既有批次，在分组被清空后仍可查看历史，不创建跨项目删除。

scope 是严格对象，只有以下三种形式：

| scope | 含义 |
| --- | --- |
| `{"kind":"project","projectId":"..."}` | 当前仍存在的指定项目 |
| `{"kind":"deleted-project","projectId":"..."}` | 指定历史项目 ID，当前项目目录中不存在 |
| `{"kind":"unassigned"}` | 归档元数据未归属项目 |

空字符串、空 projectId 或多余字段不会解释为全部项目。同名项目按 ID 区分，历史项目重新出现会使旧 scope 冲突。`POST /api/project-archive-delete/preview` 接收 scope 和可选 retryOf；固定 Session ID、当前 archiveToken、manifest 摘要和项目归属版本。`confirm` 绑定原操作 ID、确认 nonce、scope 与 `permanent_delete` 动作；另一项目、另一批次、第一阶段归档确认均不能替代。取消只移除内存预览，不执行删除。

本阶段继续使用原单条永久删除的产品事实边界：归档核心与派生索引、该 Session 的 Goal、终态 Run、按原归属规则管理的生成资产，以及既有分支重挂载。共享上传附件没有新增清理规则；不删除项目、roots、未归档会话本体或真实工作区文件。已经成功删除的项不可批量回滚，失败项重试仅从旧失败 ID 生成新的预览/确认；成功项和后来新增归档不纳入重试。

### 删除批次和 v3 单项事务

独立辅助目录 `project-archive-delete/` 的 operations 保存 `code-project-archive-delete/v1` 固定确认/逐项进度，effects 保存 `code-project-archive-delete-effect/v1` 事实删除提交凭据。cleanup 保存 `code-project-archive-delete-cleanup/v1` 原归档副本清理凭据，绑定 operationId、Session ID、archiveToken 和 transactionId，在副本移除后、原 journal 移除前持久化。只保留必要 ID、摘要、时间、状态，不复制会话标题、消息或工作区路径；与第一阶段归档命名空间、schema、动作独立校验，不互认成功。

删除按分组互斥和逐项 lifecycle → AgentRun → JSON 既有锁顺序有界执行。每项在锁内复检归档独占位置、archiveToken、manifest 和 scope；恢复/重新归档、重建或归属变化产生冲突。并发请求超过既有一秒等待上限可返回明确 busy，调用方只能读取或重试同一个已确认操作，不用新操作 ID 隐藏重复。

旧单项永久删除继续写 v1 journal，第一阶段批量归档继续写 v2；只有本阶段批量删除使用 `code-session-archive-transaction/v3`，绑定删除 operationId/archiveToken。沿用 `prepared → core_restored → facts_deleted` 阶段，但 v3 对活动核心实行额外所有权检查：

- `prepared` 尚无活动文件归属证据。只有两个目标都不存在时才允许以 `xb` 独占创建，绝不覆盖已有对象。若崩溃发生在部分核心写入后、身份凭据持久化前，不能仅凭字节像旧 bundle 就认领，须保留现场并停止自动恢复。
- `core_restored` 在 journal 内保存 Session/messages 的 SHA、长度、mtime、ctime、device、inode。新进程恢复先核对完整文件身份和内容，匹配才继续删除，不再次覆盖恢复核心。修改、同字节重建、缺失或文件身份不可得均返回恢复冲突；缺少核心也不等于删除完成。删除部分事实后但尚未获得 `facts_deleted` 持久证明的模糊窗口同样保守停止。
- `facts_deleted` 是原事务已完成事实清理的持久证明。该状态不重执行事实删除；验证原批次绑定及无异常活动位置后，先形成不可变删除 effect，再清除旧 bundle、写入 cleanup 凭据、移除原 journal。只有 effect、cleanup 凭据和原事务记录已消失的证据同时成立，才返回永久删除完成；仅有 effect 或旧进度写为 deleted 都不足以判定完成。新事务或后来重新归档的同 ID 对象不属于旧清理范围。

归档副本或原事务记录清理失败时，API 返回 `cleanup_pending`、`factsDeleted=true`、`cleanupComplete=false` 和非空失败原因，界面显示“归档清理未完成”，保留读取和“继续清理旧归档”入口。部分批次仍逐项展示成功与未完成，不把已提交事实删除再次放入新预览重试。原操作恢复只允许清理匹配原 operationId/token/transaction 的对象，绝不再次调用事实删除。原归属无法核实、archiveToken 已替换或凭据缺失时保留现场并报告冲突；不能靠缺失文件冒充清理完成。降级前必须处理或核对这些清理未完成项，保留 cleanup、effect 与原事务证据。

`GET /api/project-archive-delete` 可以读取全部删除历史，也可以传明确 JSON scope 做读取筛选；这是只读范围，不提供全部删除。弹窗“读取本批次结果”只按原 operationId 读取。`resume` 仍需原 scope/action，仅在有原确认且未完成项仍有可核实原归属时继续；遇到外来事务或缺失证据保守停止。损坏的批次、journal 或 effect 不通过删除文件或把 404 当成功绕过。

### 删除恢复和回退限制

活动文件恢复冲突时，新文件、旧 bundle 和事务记录均保留。应先检查该 Session 的文件归属、备份及原批次状态，不能反复提交旧确认，也不能删除凭据来隐藏失败；需要实际数据修复时另行明确操作边界。内部锁协调本应用写者，文件身份检查不宣称对任意外部文件系统写者实现强隔离。

回退到不识别 v3 的版本前，先用本版处理或核对所有未完成删除批次及 v3 journal，并保留完整数据根备份和两阶段辅助凭据。存在模糊状态或新对象冲突时不可直接降级强行恢复，不能要求删除证据换取回退。无未完成 v3 journal 时，旧 v1 bundle 与第一阶段 v1/v2 读取保持兼容；已经永久删除的内容不会因软件回退而恢复。旧程序运行后再次升级也不能直接重用此前未结清删除授权，应先核对逐项状态和当前归属。

### 第二阶段隔离验证

- `python -X utf8 -B -m pytest tests/test_project_archive_delete_batch.py -q -s -p no:cacheprovider`：独立临时数据根的服务/HTTP、scope/action/token、代次竞态、部分失败/重试、Goal/终态 Run/生成资产及共享附件保护。
- `python -X utf8 -B -m pytest tests/test_project_archive_delete_process.py -q -s -p no:cacheprovider`：真实 A 进程 `os._exit` 后启动全新 B，覆盖两个早期阶段正例、删除事实/凭据窗口、已完成/未开始分项，以及两个阶段分别修改/重建 Session/messages 的反例；同字节重建也核对文件身份，不能用清空内存表冒称重启。另有四项 cleanup 场景覆盖副本清理失败、journal 移除失败、journal 已移除但批次进度未更新，以及有效新 token 的归档替换保护，断言 B 不再次调用事实删除。
- `node tests/e2e/h4/code072-archive-delete.cjs`：限定归档接口写入的隔离浏览器，检查完整分组授权、不可恢复提示、丢响应直接读取、失败项新预览、历史入口、单项操作、中英与窄屏。此夹具显式启用临时宿主的清理故障注入，浏览器仍走真实 HTTP 和删除事务；两类清理失败均检查部分完成、非空原因、原结果读取和仅补清理，事件断言事实删除与副本/journal 成功移除各一次。故障开关仅限测试宿主，不进入产品设置或接口；其他 H4 默认关闭。第一阶段 H4、旧归档/删除、项目、前端和 i18n 的相关回归继续适用。
