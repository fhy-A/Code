# 自定义 Skill 本地资源合同

自定义 Skill 如需让模型执行随 Skill 分发的本地辅助脚本，必须在该 Skill 的**当前活动目录**内同时携带辅助文件和 `code-resources.json`。不要在正文中只写相对路径，也不要让模型搜索父目录、相邻仓库、用户目录或旧快照。

`code-resources.json` 使用如下最小结构：

```json
{
  "schemaVersion": 1,
  "skill": "my-skill",
  "resources": [
    {
      "id": "build-report",
      "path": "scripts/build_report.py",
      "sha256": "<该文件的 SHA-256>",
      "kind": "python",
      "protocol": "my-skill-report/v1",
      "modelVisible": true,
      "arguments": ["<input>"]
    }
  ]
}
```

约束如下：

- `path` 必须是 Skill 自身目录内的相对普通文件路径；不得使用绝对路径、`..`、隐藏目录、符号链接或 Windows reparse point。
- 每个 helper 必须有唯一 `id`、准确 SHA-256、允许的 `kind`（当前为 `python` 或 `python-library`）和至少一个模型可见资源；文本文件哈希按 LF 换行归一化计算。
- 有意修改 helper 后，同时刷新其 SHA-256；移动 `.code` 或活动数据根后，无需也不得保存旧绝对路径，Code 会从当前活动 Skill 目录重新解析。
- 自定义合同不要写 `compatibleInstalled`。该字段只属于 Code 自带 Skill 的兼容安装身份；同名自定义 Skill 绝不会借用 bundled helper。

合同有效时，`use_skill` 会以 `runtimeResources.source = "custom"` 返回当前目录中的精确绝对路径和“不搜索、不复制”的指引。没有合同的自定义 Skill 不会获得任何 helper 路径；解析器已经识别并投影该无资源自定义条件时，会返回 `custom-no-resources` 的“不搜索、不猜测路径”指引。若任务确实需要 helper，应先补齐合同而不是让模型猜测位置。

这个合同只负责模型指引、资源身份和正确性，不改变 Code 自动模式的 full access、文件/命令工具权限或用户明确提供外部路径的既有语义。

开发或打包前可运行 `python scripts/audit_skill_resources.py`。该审计只检查当前 Code `data/skills` 下由 `code-resources.json` 显式声明的本地 helper：会发现缺失、哈希不符、路径穿越或 reparse 风险，但会忽略 Skill 正文中的示例和普通 prose，也不会扫描活动用户 Skill 目录或其他位置。
