# 项目会话批量归档（CODE-072 第一阶段）

本阶段提供项目菜单“全部归档”、固定目标的服务端预览、必要时明确停止并归档，以及归档页按稳定项目 ID 筛选。单项恢复和单项永久删除沿用原行为；不提供批量恢复或批量永久删除。

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
