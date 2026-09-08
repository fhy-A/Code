# Code 发版指南

> 适用于人工操作者和 AI Agent。最后更新：2026-09-08。

---

## 快速开始

```powershell
# 一条命令发版（需要 GitHub CLI 已登录）
python release.py 0.5.8

# AI Agent 使用（跳过交互确认）
python release.py 0.5.8 --yes

# 两阶段：先做完整验证和构建，不创建提交、标签或远端对象
python release.py 0.5.8 --prepare --yes

# 发布完全匹配的 prepared 候选
python release.py 0.5.8 --publish-prepared --yes

# 外部发布中断后，审计并续接同一候选
python release.py 0.5.8 --resume --yes

# 预演：只检查，不改任何文件
python release.py 0.5.8 --dry-run

# 兼容入口：只接受当前候选的有效 prepared 凭证
python release.py 0.5.8 --skip-tests
```

版本优先的 `--prepare`、`--publish-prepared`、`--resume` 是 canonical 写法。已有自动化可继续使用等价兼容别名 `python release.py prepare 0.5.8`、`python release.py publish-prepared 0.5.8`、`python release.py resume 0.5.8`；两套语法进入同一实现、凭证和安全门禁。

---

## 脚本做了什么

| 阶段 | 操作 | 校验 |
|------|------|------|
| 1 | 同步版本号到 `VERSION`、`file_version_info.txt`、`README.md` | 3 个文件版本号一致；README 徽章 URL / alt 与 EXE 下载名同版 |
| 2 | `git diff --check` → `node --check` / `py_compile` → 前端构建/freshness/语法 → `npm run verify:harness-replay`（30 秒）→ `pytest -q --durations=30`（1500 秒） | 原11项共享检查全部执行一次，廉价失败先阻断耗时步骤 |
| 3 | `python build_exe.py` 打包 | EXE 文件生成 |
| 4 | 读取 EXE 版本元数据 + 计算 SHA-256 | `ProductVersion` / `FileVersion` / `OriginalFilename` 正确 |
| 5 | 保留预先准备的中文正文，刷新 `docs/releases/vX.Y.Z.md` 产物信息 | 正文、版本、文件大小和hash校验通过后才签发prepared凭证 |
| 6 | `git add` + `git commit` + `git tag` | 提交和标签创建成功 |
| 7 | `git push` + `gh release create` | 分支、标签、Release 均已推送 |

任何阶段失败，脚本立刻停止并打印错误原因和补救命令。

默认完整发布现在复用同一个 sealed 流程：没有本版本凭证时，完整 prepare 一次后发布；存在有效 `prepared` 时严格校验后复用；`publishing` 审计续接同一候选；`published` 只作只读审计，远端对象缺失或变化时拒绝重建。损坏、未知或漂移凭证直接失败，不静默覆盖或退回重新发布。原必测集合、各项超时、fail-fast 和 H4 排除边界不变，仅把廉价检查前置。`--dry-run` 保持只做预演检查，不新增 replay 执行。replay 失败、超时或无法启动都会在 EXE 构建前阻断。

`--skip-tests` 不再接受“刚跑过”的人工声明。非 dry-run 下它只作为 `--publish-prepared` 的兼容入口：必须存在与当前 HEAD、index、tracked 候选、发布文件、验证定义、环境、发布说明和 EXE 完全绑定的有效凭证，否则立即失败并提示重新运行 `--prepare`。

---

## 日常验证与发布风险检查

完整pytest使用已确认的1500秒（25分钟）上限，并报告最慢30项耗时；全部测试和断言保留，其他检查的超时不变。失败或超时即停止，不自动延长预算或重试prepare；新预算和命令参数进入共享定义指纹，旧凭证不能复用。

日常先按变更影响运行直接相关测试，再补相邻兼容、恢复与构建检查。只有影响难以界定的关键变更或冻结发布候选才运行全量；不把每个开发阶段或微小修正都变成一次全量验证。现有根目录和 Code 协作规则中的分层验证及不机械重复原则继续适用。

长验证和构建实时显示输出、阶段、耗时与退出状态；每条公开执行命令在临时 `code-check-*` 目录保存 UTF-8 `stdout.log`、`stderr.log` 和 `result.json`。超时或取消保留已取得输出，并收尾本次创建的进程树；Windows复用现有Job容器，命令在容器绑定后才放行。不按进程名终止程序，也不触碰日常服务。身份、凭据和远端查询继续使用quiet入口，不全局打印环境或密钥。

`CHECK_PASS`、`CHECK_FAILED`、`NOT_RUN` 区分通过、失败及后续未运行项。失败或中断不能生成有效凭证，prepare继续按原发布白名单回滚。日志是诊断证据，不能代替绑定当前候选、环境、验证定义和产物的凭证；不引入跨版本或逐测试缓存。dry-run继续保持原只读检查子集，不构建、发布或写版本元数据。

---

## 推荐：两阶段发布与断点续发

### 1. Prepare：昂贵验证与本地候选

```powershell
python release.py 0.5.8 --prepare --yes
```

`prepare` 在第一次修改版本元数据前先校验已有发布说明正文、Node/npm/PyInstaller可用性，再执行远端只读预检并记录验证环境：

- `gh` 可用且已登录，origin 可达；
- 远端 `master` 是当前候选 HEAD 的祖先；
- 目标本地/远端 tag、GitHub Release 和资产没有冲突；
- 暂存区为空，当前分支是 `master`。

README 的 canonical 版本元数据只包括 `img.shields.io` 版本徽章 URL、同一徽章的 `Version X.Y.Z` alt 和具体的 `Code-vX.Y.Z.exe` 下载名。版本同步会在该精确范围内同时更新三者，不改写其他图片 alt、链接或正文；重复同步同一版本不产生新内容差量。dry-run 必须确认三者均为当前旧版本，正式一致性校验必须确认三者均为目标版本；canonical 徽章或具体 EXE 名缺失、重复、陈旧或彼此不一致都会在构建前失败。

预检通过后，脚本同步版本号、按共享manifest的新顺序运行完整 release 门禁、构建 EXE、严格核对 PE 元数据和 SHA-256、生成并校验发布说明。成功时：

- 保留本地 prepared 元数据、发布说明和 EXE，临时 spec 仍只位于已忽略的 build 目录；
- 将机器可校验凭证写入 Git 内部路径 `.git/code-release/vX.Y.Z.json`，因此不会出现在工作树或提交中；
- 不 commit、不 tag、不 push、不创建 GitHub Release。

凭证只保存相对发布路径、哈希、Git 候选摘要、共享验证定义指纹、必要的工具/平台摘要和发布进度，不保存 token、业务数据或不必要的绝对路径。`prepare` 中途失败会恢复本次命令涉及的发布白名单元数据并删除无效凭证；EXE 即使残留也不能在没有有效凭证时发布。

发布说明必须在 `prepare` 前已有无占位的中文正文。脚本会保留正文并刷新版本、日期、大小和 SHA-256；正文缺失、为空或含占位时在耗时验证前失败；只含正文的旧输入格式继续支持，标题和下载信息在构建后生成。验证环境在前后再次比对，变化时拒绝签发凭证。

### 2. Publish prepared：精确复用

```powershell
python release.py 0.5.8 --publish-prepared --yes
```

脚本只有在以下证据全部一致时才跳过昂贵门禁：

- 版本、基线 HEAD、`master`、index tree 与发布白名单外 tracked 差量摘要；
- 发布白名单文件的大小、SHA-256 和 Git blob；
- `devtools/verification.py` 中正式 release 检查的 ID、顺序、命令和超时指纹；
- 发布说明正文与 EXE 大小、SHA-256、`ProductVersion`、`FileVersion`、`OriginalFilename`；
- Git/gh/Python/平台和 GitHub 仓库身份；
- origin 基线、目标 tag 与 Release 仍无冲突。

任一文件、环境、门禁定义、远端基线或凭证摘要变化都会 fail-closed，要求重新 `prepare`。H4 仍只属于 runtime profile，不会进入 release 门禁或凭证。

### 3. Resume：审计后只补缺失步骤

```powershell
python release.py 0.5.8 --resume --yes
```

`resume` 只接受已经由 `publish-prepared` 启动的同一凭证。它按顺序审计发布提交、`master`、本地/远端 tag、GitHub Release 正文和 EXE 资产：

| 观察结果 | 行为 |
|---|---|
| 与凭证完全一致 | 跳过该步，继续审计下一步 |
| 对象缺失且前置状态一致 | 只补做该步 |
| 提交、分支、tag、Release 正文、资产名/大小/SHA-256 任一不同 | 立即停止 |
| Release 已存在但资产缺失 | 使用不带 `--clobber` 的上传补齐 |
| 资产存在但摘要不同，或存在凭证外资产 | 立即停止，不覆盖 |

流程禁止 force-push、删除/重建 tag 或 Release、覆盖不同资产。即使命令实际成功但响应丢失，下一次 `resume` 也会先读取真实状态，再决定跳过或补做。

---

## 前置条件

运行脚本前确保：

| 条件 | 检查命令 |
|------|----------|
| 工作区干净 | `git status` — 不应有未提交的本阶段改动 |
| 上一阶段已提交 | `git log --oneline -3` — 确认最近的提交是上一个功能阶段 |
| 开发日志已更新 | 本版本的所有改动已记录到当天日期文件，且 `docs/development-log/README.md` 索引已同步 |
| 私有计划已核对 | 内部工作区的 `../../workbar-private/TODO.md` 已移除完成项并记录新发现待办；公开短期待办摘要不得据此自动选择或启动任务，也不得从私有 TODO 自动同步；私有事实源缺失的外部 clone 只按用户显式发布范围核对 |
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

### 3. 校验发布说明与准备结果

发布说明正文须在运行前写好，默认使用中文，只覆盖上一标签以来实际完成的改动；缺失、空白或占位会在耗时验证前阻断。构建后脚本保留正文并刷新标题、版本、SHA-256与文件大小，然后再次校验，不能用 `--yes` 绕过。

需要先人工检查产物时，使用 `--prepare --yes`；核对候选后再执行 `--publish-prepared --yes`。prepared生成后修改正文、候选或产物会使凭证失效，不能编辑后直接复用旧凭证。

### 4. 脚本自动完成

默认完整入口会在同一确认范围内完成prepare和已验证候选的提交、标签、推送与Release。看到 `Code v0.5.8 两阶段发布完成` 表示对应流程已完成；中途失败按保留的凭证状态审计续接，禁止覆盖远端冲突。

### 5. 验证

```powershell
# 检查 GitHub Release 是否可见
gh release view v0.5.8

# 浏览器确认
start https://github.com/fhy-A/Code/releases/latest
```

---

## AI Agent 使用指南

### 一次性发版（全自动）

```powershell
python release.py 0.5.8 --yes
```

### 两阶段发版（推荐）

```powershell
python release.py 0.5.8 --prepare --yes
python release.py 0.5.8 --publish-prepared --yes

# 如果第二条命令在提交、推送或 Release/资产步骤中断
python release.py 0.5.8 --resume --yes
```

### 限制

- `--yes` 会跳过交互确认，但不能绕过发布说明硬性校验。
- Agent 应先写好 `docs/releases/v0.5.8.md` 的无占位中文正文，再运行 `python release.py 0.5.8 --yes`。Phase 5 会保留正文，并刷新日期、版本号、文件大小与 SHA-256。
- 如果未预先准备正文，prepare 会在耗时验证前停止并提示补充；已有正文继续保留。
- 无论采用人工还是 Agent 流程，创建标签和 GitHub Release 前都必须再次检查发布说明为中文主体、没有占位文案，并且只覆盖上一标签以来的真实改动。
- Agent 不得把 `--skip-tests` 当作人工信任开关；没有有效 prepared 凭证时必须重新运行 `--prepare`。
- `--prepare` 成功不代表已经获得 push、tag 或 Release 授权；执行 `--publish-prepared` / `--resume` 前仍需当前阶段的明确发布操作授权。

### Agent 无法处理的情况

以下情况脚本会退出，需要人工介入：

| 情况 | 脚本提示 | 人工处理 |
|------|----------|----------|
| 测试失败 | `全量测试未通过` | 修复代码，重新跑测试 |
| Harness replay 失败或超时 | `Harness replay 门禁失败` | 运行 `npm run verify:harness-replay`，核对首差异与固定哈希 |
| 构建失败 | `PyInstaller 构建失败` | 检查 PyInstaller 日志，修复依赖 |
| prepared 凭证损坏、陈旧或定义/环境漂移 | `请重新 prepare` | 保留事实证据，重新运行 `prepare`，不得手工改凭证 |
| 远端 master/tag/Release/资产与凭证不同 | `禁止覆盖` | 停止并核对远端对象，不 force-push、不删除重建 |
| 推送失败 | `推送分支失败` | 检查网络和权限，手动 `git push` |
| `gh` 未安装 | `未找到 GitHub CLI` | 安装并登录 GitHub CLI |
| `gh` 未登录 | `GitHub CLI 未登录` | `gh auth login` |
| Release 创建失败 | `GitHub Release 创建失败` | 代码已推送，手动上传 EXE 到 Release 页面 |

---

## 手动发版（不用脚本时的完整步骤）

如果脚本不可用，以下是手动操作清单：

### 1. 改版本号（3 个文件）

```
VERSION                              → 改内容为 "0.5.8"
file_version_info.txt                → 改 filevers/prodvers/FileVersion/ProductVersion/OriginalFilename
README.md                            → 同步版本徽章 URL / alt 和具体 EXE 下载名
```

### 2. 验证一致性

```powershell
# 确认三个文件中的版本号都指向 0.5.8
findstr "0.5.8" VERSION file_version_info.txt README.md
```

### 3. 质量检查

```powershell
npm run check:frontend
python -m pytest tests -q
npm run verify:harness-replay
git diff --check
node --check app.js
node --check agent-runtime.js
python -m py_compile server.py launcher.py build_exe.py
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
git add VERSION file_version_info.txt README.md docs/releases/v0.5.8.md
git commit -m "chore: prepare v0.5.8 release metadata"
git tag v0.5.8
```

### 8. 推送

```powershell
git push origin master
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
| `devtools/release_state.py` | prepared 凭证封印、原子写入和文件哈希校验 |
| `devtools/verification.py` | 共享验证定义与 release 门禁指纹事实源 |
| `VERSION` | 纯文本版本号 |
| `file_version_info.txt` | Windows EXE 版本元数据 |
| `README.md` | 项目首页（含版本徽章和下载链接） |
| `build_exe.py` | canonical PyInstaller 打包入口；临时 spec 只生成到已忽略的 `build/` |
| `docs/releases/vX.Y.Z.md` | 单版本发布说明 |
| `docs/development-log/README.md` | 开发日志索引；详细记录位于同目录的日期文件，早期记录位于 `archive/` |
| `TODO.md` | 用户批准的公开、脱敏、非执行短期待办摘要；内部 canonical 路线位于 `../../workbar-private/TODO.md`，摘要仅在用户明确批准后人工更新 |
