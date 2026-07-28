# Code 发版指南

> 适用于人工操作者和 AI Agent。最后更新：2026-07-23。

---

## 快速开始

```powershell
# 一条命令发版（需要 GitHub CLI 已登录）
python release.py 0.5.8

# AI Agent 使用（跳过交互确认）
python release.py 0.5.8 --yes

# 预演：只检查，不改任何文件
python release.py 0.5.8 --dry-run

# 刚跑完全量测试，跳过测试步骤
python release.py 0.5.8 --skip-tests
```

---

## 脚本做了什么（7 个阶段）

| 阶段 | 操作 | 校验 |
|------|------|------|
| 1 | 同步版本号到 `VERSION`、`file_version_info.txt`、`README.md`，复制 `.spec` | 4 个文件版本号一致 |
| 2 | `pytest -q` + `git diff --check` + `node --check` + `py_compile` | 全量测试通过，语法无误 |
| 3 | `python build_exe.py` 打包 | EXE 文件生成 |
| 4 | 读取 EXE 版本元数据 + 计算 SHA-256 | `ProductVersion` / `FileVersion` / `OriginalFilename` 正确 |
| 5 | 生成 `docs/releases/vX.Y.Z.md` 模板 | **暂停等你编辑发布说明** |
| 6 | `git add` + `git commit` + `git tag` | 提交和标签创建成功 |
| 7 | `git push` + `gh release create` | 分支、标签、Release 均已推送 |

任何阶段失败，脚本立刻停止并打印错误原因和补救命令。

---

## 前置条件

运行脚本前确保：

| 条件 | 检查命令 |
|------|----------|
| 工作区干净 | `git status` — 不应有未提交的本阶段改动 |
| 上一阶段已提交 | `git log --oneline -3` — 确认最近的提交是上一个功能阶段 |
| CHANGELOG.md 已更新 | 本版本的所有改动已记录到 `CHANGELOG.md` |
| TODO.md 已更新 | 已完成条目已移除，新发现的待办已加入 |
| GitHub CLI 已安装 | `gh --version` |
| GitHub CLI 已登录 | `gh auth status` |

### 安装 GitHub CLI（如果还没有）

```powershell
winget install GitHub.cli
gh auth login
```

---

## 人工发版完整流程

### 1. 确认一切就绪

```powershell
git status                    # 工作区是否干净？
python -m pytest tests -q     # 测试是否全过？
git log --oneline -3          # 最近的提交是否就位？
```

### 2. 运行发版脚本

```powershell
python release.py 0.5.8
```

### 3. 脚本在 Phase 5 暂停

此时 `docs/releases/v0.5.8.md` 已生成，SHA-256 和文件大小已填入。你需要：

- 打开 `docs/releases/v0.5.8.md`
- 把 `[发布说明待补充 -- 请在此描述本版本的主要改动]` 替换为实际改动描述
- 默认使用中文撰写，仅保留模型名、参数名、错误码、命令和哈希等必要英文技术字段
- 以“上一标签至当前标签”的 Git 提交和 `CHANGELOG.md` 为依据，只记录本次实际包含的改动，不写入尚未交付的计划
- 确认全文不存在“待补充”、示例版本号或其他占位文案
- 保存文件

回到终端，回答 `y` 继续。

### 4. 脚本自动完成

Phase 6-7 自动执行 git 提交、打标签、推送、创建 GitHub Release。看到 `Code v0.5.8 发版完成!` 就结束了。

### 5. 验证

```powershell
# 检查 GitHub Release 是否可见
gh release view v0.5.8

# 浏览器确认
start https://github.com/fhy-A/Code/releases/latest
```

---

## AI Agent 使用指南

### 发版（全自动）

```powershell
python release.py 0.5.8 --yes
```

### 限制

- `--yes` 会跳过所有交互确认，但**不会跳过 Phase 5 的暂停**——发布说明仍需要人工编辑。
- 如果发布说明已经提前编辑好，Agent 可以分两步：
  1. 先写 `docs/releases/v0.5.8.md`
  2. 再跑 `python release.py 0.5.8 --yes`（此时脚本在 Phase 5 检测到文件已有实际内容，但仍会询问）
- 无论采用人工还是 Agent 流程，创建标签和 GitHub Release 前都必须再次检查发布说明为中文主体、没有占位文案，并且只覆盖上一标签以来的真实改动。

### Agent 无法处理的情况

以下情况脚本会退出，需要人工介入：

| 情况 | 脚本提示 | 人工处理 |
|------|----------|----------|
| 测试失败 | `全量测试未通过` | 修复代码，重新跑测试 |
| 构建失败 | `PyInstaller 构建失败` | 检查 PyInstaller 日志，修复依赖 |
| 推送失败 | `推送分支失败` | 检查网络和权限，手动 `git push` |
| `gh` 未安装 | `未找到 GitHub CLI` | 安装并登录 GitHub CLI |
| `gh` 未登录 | `GitHub CLI 未登录` | `gh auth login` |
| Release 创建失败 | `GitHub Release 创建失败` | 代码已推送，手动上传 EXE 到 Release 页面 |

---

## 手动发版（不用脚本时的完整步骤）

如果脚本不可用，以下是手动操作清单：

### 1. 改版本号（4 个文件）

```
VERSION                              → 改内容为 "0.5.8"
file_version_info.txt                → 改 filevers/prodvers/FileVersion/ProductVersion/OriginalFilename
README.md                            → 改版本徽章和下载链接中的版本号
Code-v0.5.7.spec → Code-v0.5.8.spec  → 复制并替换内部的版本号
```

### 2. 验证一致性

```powershell
# 确认四个文件中的版本号都指向 0.5.8
findstr "0.5.8" VERSION file_version_info.txt README.md Code-v0.5.8.spec
```

### 3. 质量检查

```powershell
python -m pytest tests -q
node --check app.js
node --check agent-runtime.js
python -m py_compile server.py launcher.py build_exe.py
git diff --check
```

### 4. 构建

```powershell
python build_exe.py
```

### 5. 验证 EXE

```powershell
# 检查 Windows 文件属性中的版本号
(Get-Item "dist\Code-v0.5.8.exe").VersionInfo | Format-List

# 计算 SHA-256
(Get-FileHash "dist\Code-v0.5.8.exe" -Algorithm SHA256).Hash
```

### 6. 写发布说明

在 `docs/releases/v0.5.8.md` 中填写改动描述、文件大小、SHA-256。

### 7. 提交 & 打标签

```powershell
git add VERSION file_version_info.txt README.md Code-v0.5.8.spec docs/releases/v0.5.8.md
git commit -m "chore: prepare v0.5.8 release metadata"
git tag v0.5.8
```

### 8. 推送

```powershell
git push origin main
git push origin v0.5.8
```

### 9. 创建 GitHub Release

```powershell
gh release create v0.5.8 dist/Code-v0.5.8.exe `
  --title "Code v0.5.8" `
  --notes-file docs/releases/v0.5.8.md
```

或者打开 https://github.com/fhy-A/Code/releases/new?tag=v0.5.8 手动上传。

---

## 版本号规则

- 格式：`主版本.次版本.修订号`（如 `0.5.8`）
- `修订号`（第三位）：Bug 修复、小改进、Skill 更新
- `次版本`（第二位）：新功能、新能力
- `主版本`（第一位）：架构变更、不兼容改动

---

## 相关文件索引

| 文件 | 作用 |
|------|------|
| `release.py` | 自动发版脚本 |
| `VERSION` | 纯文本版本号 |
| `file_version_info.txt` | Windows EXE 版本元数据 |
| `README.md` | 项目首页（含版本徽章和下载链接） |
| `Code-vX.Y.Z.spec` | PyInstaller 打包配置 |
| `build_exe.py` | PyInstaller 构建入口 |
| `docs/releases/vX.Y.Z.md` | 单版本发布说明 |
| `CHANGELOG.md` | 所有版本的开发记录 |
| `TODO.md` | 待办路线 |
