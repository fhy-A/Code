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

新凭证为最小v2：在原单候选凭证上增加输入/构建环境/前端证明与正文边界摘要，不建立逐测试缓存。Git/gh之外的环境、全部代码/测试、打包输入及未分类文件都参与绑定；Skill正文和资源按实际打包树纳入，不按扩展名排除。esbuild绑定实际解析入口及二进制摘要，Node/npm、Python构建包版本及已安装Python发行包版本摘要在门禁前记录，门禁后与封印前核对。凭证不保存token、业务正文或不必要的绝对路径。首次`prepare`中途失败恢复进入时的四文件元数据并删除无效凭证；EXE即使残留也不能无有效凭证发布。受控`--reprepare`失败则保留不可发布的`reprepare_pending`和原审计，修复原因后可再用同一入口，不能绕过为publish。

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
git log --oneline -3          # 最近的提交是否就位？
```

只核对现场与已完成的定向证据，不先手动再跑一次全量；下一步 canonical 入口会执行一次正式门禁。完整入口与两阶段入口二选一，不连续重复准备同一候选。

### 2. 运行发版脚本

```powershell
python release.py 0.5.8
```

### 3. 校验发布说明与准备结果

发布说明正文须在运行前写好，默认使用中文，只覆盖上一标签以来实际完成的改动；缺失、空白或占位会在耗时验证前阻断。构建后脚本保留正文并刷新标题、版本、SHA-256与文件大小，然后再次校验，不能用 `--yes` 绕过。

需要先人工检查产物时，使用 `--prepare --yes`；核对候选后再执行 `--publish-prepared --yes`。prepared生成后不能编辑完直接发布；仅本版本正文允许区域或Git/gh版本变化可按下方`--refresh-prepared`重新核对，其他变化走受控重新准备或停下。

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
- Agent 不得把 `--skip-tests` 当作人工信任开关；没有有效 prepared 凭证不得发布。先核对候选/版本/发布状态，再按下方失败边界处理；不能循环重试同版本prepare或手改凭证。
- `--prepare` 成功不代表已经获得 push、tag 或 Release 授权；执行 `--publish-prepared` / `--resume` 前仍需当前阶段的明确发布操作授权。

### Agent 无法处理的情况

以下情况脚本会退出，需要人工介入：

| 情况 | 脚本提示 | 人工处理 |
|------|----------|----------|
| 测试失败 | `全量测试未通过` | 保留失败日志，定位后只复验直接相关场景；修复稳定并重新冻结候选后再执行一次完整门禁 |
| Harness replay 失败或超时 | `Harness replay 门禁失败` | 运行 `npm run verify:harness-replay`，核对首差异与固定哈希 |
| 构建失败 | `PyInstaller 构建失败` | 检查 PyInstaller 日志，修复依赖 |
| prepared失效 | 输入/定义/环境不匹配 | 尚未发布且来源完整时，正文/Git/gh窄差量用`--refresh-prepared`，其他失效用`--reprepare`；坏seal/未知来源停下，不手改版本或凭证 |
| 远端 master/tag/Release/资产与凭证不同 | `禁止覆盖` | 停止并核对远端对象，不 force-push、不删除重建 |
| 推送失败 | `推送分支失败` | 保留凭证，先只读核对命令是否已成功；网络/权限恢复且同一候选匹配后使用 `--resume --yes`，不手工补推绕过审计 |
| `gh` 未安装 | `未找到 GitHub CLI` | 安装并登录 GitHub CLI |
| `gh` 未登录 | `GitHub CLI 未登录` | `gh auth login` |
| Release 创建或资产上传失败 | `GitHub Release 创建失败` 或上传错误 | 先读实际Release与资产状态，匹配同一凭证后使用 `--resume --yes`，不手工上传、覆盖或重建对象 |

---

## 尚未发布候选的受控刷新与重新准备

```powershell
# 只更改本版本已生成说明的正文，或升级Git/gh
python release.py 0.5.8 --refresh-prepared --yes

# 完整可验证的prepared已失效，VERSION仍是已同步目标版本
python release.py 0.5.8 --reprepare --yes
```

两入口也支持动作优先的兼容写法。它们不创建提交、标签或远端对象，也不自动开始发布；后续publish仍需原操作授权。

- **刷新**：只接受尚未发布的v2、原HEAD/index和远端基线。除了唯一正文标记内的中文内容及Git/gh版本，四文件、前端、实际输入、构建环境、EXE大小/哈希/PE均须一致。正文外生成信息不能改；重新检查占位、版本、freshness/syntax和远端身份/冲突后原子写入新绑定，保存原审计、具体检查和旧全量时间，不把复用记成新全量通过。
- **候选必须可提交对应**：新的prepare/刷新/重新准备在昂贵验证前拒绝四个发布文件之外的未提交tracked改动和未跟踪的实际发布输入，提示先提交产品/测试修复；原三项不打包运行数据排除且不读取内容。EXE的输入不能超出发布tag所含来源。
- **重新准备**：接受完整有效封印的prepared来源或此前的`reprepare_pending`。必须能证明publication从未开始、当前VERSION为目标、HEAD中仍为原oldVersion、原基线是当前祖先、cached为空且本地/远端无对象冲突。不会先把版本手改回旧值；先归档原凭证并写入不可发布状态，再执行完整门禁与打包。成功原子替换，失败恢复进入时四文件内容，保留审计和`--reprepare`重试入口，旧证据不复活。
- **旧v1**：继续原严格校验/续发，不静默补字段或享受细粒度复用。符合未发布来源条件时可显式完整重新准备为v2；旧工具不识别v2即拒绝，不能降级伪装。
- **发布已开始**：`publishing`只对原候选使用resume；`published`仅只读核验。两者拒绝刷新、重准备或重绑。若工具/定义不再匹配，保留原凭证和工具版本供审计，不自动转换或外部回滚。

EXE的独立`python build_exe.py`仍自行构建并核验前端。release内部可传入本次精确前端证明，在打包入口和调用PyInstaller前再次核对源码、输出及实际工具链，匹配才省去重复生成；证明不是通用跳过构建开关。旧发布helper直接非dry-run执行会明确拒绝，所有正常CLI仍共用sealed入口。

Release创建使用verify-tag并绑定目标提交；创建后、续发和已发布审计统一要求非draft、非prerelease、有效发布时间，v2目标为发布提交，唯一资产必须为uploaded且名称/大小/SHA256一致。缺字段或冲突停下，不自动修改远端对象。

---

## 脚本不可用时的故障边界

手工路线只用于只读诊断，不是另一套绕开凭证的发布程序。保留当前 HEAD、index、版本元数据、凭证、EXE、完整日志及已观察到的远端对象；不要手改版本、补写凭证、手工提交/推送/上传或删除重建对象。

- 尚未产生发布副作用：先修复脚本或提出独立、明确授权的一次性恢复方案。普通失败不能自动转成“信任已测试”的例外；既有例外记录也不构成后续版本的豁免。
- 已进入 `publishing`：仅在原候选、制品、权限及远端对象一致时走 canonical `--resume --yes`。响应丢失先查事实，不盲重试；冲突或坏凭证先停下，不能重新prepare掩盖已经发生的外部操作。
- 已是 `published`：仅作只读核验，缺失或漂移不授权重建。后续代码或文案变化属于新阶段，不能移动发布标签。
- `gh` 未安装、未登录或网络不可用：报告具体边界，由操作者处理环境；Agent 不自动安装、登录或修改凭据。环境恢复后仍核对同一候选与实际发布状态。

---

## Skill 管理性能专项

默认pytest保留当前31项规模的真实准备、独立可写副本、启停响应、完整性/计数、跨请求篡改拒绝及并发读取。只读模块准备基线在本轮pytest内复用，每项仍复制并校验内容，不持久缓存真实数据或共享可写profile。

旧实现成本对照、五次预热启停、逐函数耗时与重复测量属于可手动运行的专项，不进入默认pytest文件发现：

```powershell
python -B -m pytest tests/performance/skill_management_read_view.py -q -s
```

专项仍保留原对照断言和完整诊断，仅使用合成库；不能指向真实运行数据。耗时只反映当次环境，不设计时通过阈值，不代替默认正确性、安全、兼容或恢复验证。前后比较须注明是否包含准备成本，不把不同基线的耗时直接相减为收益。

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
