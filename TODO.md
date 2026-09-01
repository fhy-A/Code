# 公开计划兼容说明

<!-- workbar-private-plan-stub/v1 -->

workbar 的内部未完成计划不存放在公共 Git 仓库。本文件是稳定兼容 stub，不包含任务、优先级、渠道、已知缺口、下一动作或未批准设计。

- 内部工作区唯一事实源：`../workbar-private/TODO.md`。
- 内部事实源存在时，Agent 必须优先读取并只在那里维护未完成事项。
- 私有事实源缺失时，外部 clone 仍可按用户显式任务、公共代码和已完成开发日志工作；必须停止恢复内部路线，不得创建、扩写或从历史推测重建本公开 stub。
- 已完成事实继续写入 `docs/development-log/YYYY/YYYY-MM-DD.md` 并更新索引。
