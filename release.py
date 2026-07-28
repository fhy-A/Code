"""
Code 自动发版脚本

严格按照项目已有发版流程执行：
  1. 版本号同步（VERSION / file_version_info.txt / README.md / .spec）
  2. 一致性校验
  3. 全量测试 + 语法检查
  4. PyInstaller 构建 EXE
  5. EXE 元数据 + SHA-256 校验
  6. 生成发布说明
  7. Git 提交 + 打标签
  8. 推送到 GitHub + 创建 Release

任何步骤失败都会立即停止并给出明确错误信息，由人工介入处理。

用法：
  python release.py 0.5.8                发版 0.5.8
  python release.py 0.5.8 --skip-tests   跳过测试
  python release.py 0.5.8 --dry-run      预演模式
  python release.py 0.5.8 --proxy 127.0.0.1:18081  指定代理
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "VERSION"
VERSION_INFO_FILE = ROOT / "file_version_info.txt"
README_FILE = ROOT / "README.md"
RELEASES_DIR = ROOT / "docs" / "releases"
BUILD_SCRIPT = ROOT / "build_exe.py"
DEFAULT_BRANCH = "master"
RELEASE_NOTES_PLACEHOLDER = "[发布说明待补充 -- 请在此描述本版本的主要改动]"
RELEASE_NOTES_BODY_START = "<!-- code-release-notes:body:start -->"
RELEASE_NOTES_BODY_END = "<!-- code-release-notes:body:end -->"

_RELEASE_NOTES_GENERATED_HEADINGS = (
    "\n## Packaging\n",
    "\n## 打包信息\n",
    "\n## Download / verification\n",
    "\n## 下载与校验\n",
)
_RELEASE_NOTES_PLACEHOLDER_PATTERNS = (
    (re.compile(r"待补充"), "包含“待补充”占位文案"),
    (re.compile(r"\bTBD\b", re.IGNORECASE), "包含 TBD 占位文案"),
    (re.compile(r"\[\s*TODO(?:\s|:|\])", re.IGNORECASE), "包含 TODO 占位文案"),
    (re.compile(r"DRY_RUN_SHA256"), "包含预演 SHA-256 占位值"),
    (re.compile(r"\bv?X\.Y\.Z\b", re.IGNORECASE), "包含示例版本号 X.Y.Z"),
)

# 当前脚本级代理设置（由 main() 中的检测/参数设置）
_proxy_url = None


# ═══════════════════════════════════════════════════════════════
# 代理检测
# ═══════════════════════════════════════════════════════════════

def detect_windows_proxy():
    """从 Windows 系统代理设置读取代理地址，返回 'host:port' 或 None。"""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        ) as key:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
        if enabled and server:
            first = server.split(";")[0].strip()
            if "=" in first:
                first = first.split("=", 1)[1].strip()
            return first
    except Exception:
        pass
    return None


def _build_proxy_env(proxy_url):
    """返回带代理环境变量的 dict，若 proxy_url 为空则返回 None（继承父进程）。"""
    if not proxy_url:
        return None
    proxy_value = f"http://{proxy_url}"
    return {
        "HTTP_PROXY": proxy_value,
        "HTTPS_PROXY": proxy_value,
        "http_proxy": proxy_value,
        "https_proxy": proxy_value,
        "NO_PROXY": "localhost,127.0.0.1,.local",
        "no_proxy": "localhost,127.0.0.1,.local",
    }


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def run(cmd, *, cwd=None, timeout=300, description=None):
    """运行命令，返回 (returncode, stdout, stderr)。自动注入代理环境变量。"""
    cwd = cwd or ROOT
    label = description or (" ".join(cmd) if isinstance(cmd, list) else cmd)
    print(f"\n  [{label}]")

    env = os.environ.copy()
    if _proxy_url:
        env.update(_build_proxy_env(_proxy_url))

    result = subprocess.run(
        cmd, cwd=str(cwd),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=timeout,
        shell=isinstance(cmd, str),
        env=env,
    )
    if result.returncode != 0:
        if result.stderr:
            print(f"  STDERR:\n{result.stderr[-500:]}")
        if result.stdout:
            print(f"  STDOUT:\n{result.stdout[-500:]}")
    return result.returncode, result.stdout, result.stderr


def die(message):
    print(f"\n{'='*60}")
    print(f"  X 发版失败: {message}")
    print(f"{'='*60}")
    sys.exit(1)


def warn(message):
    print(f"  !  {message}")


def ok(message):
    print(f"  V  {message}")


def ask(prompt):
    answer = input(f"\n  ?  {prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


# ═══════════════════════════════════════════════════════════════
# Step 1: 读取 & 校验版本号
# ═══════════════════════════════════════════════════════════════

def get_current_version():
    if not VERSION_FILE.exists():
        die(f"找不到 VERSION 文件: {VERSION_FILE}")
    v = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.match(r"^\d+\.\d+\.\d+$", v):
        die(f"VERSION 格式不正确: {v}")
    return v


def parse_version(version_str):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str)
    if not m:
        die(f"版本号格式不正确: {version_str}（需要 X.Y.Z）")
    return tuple(int(x) for x in m.groups())


# ═══════════════════════════════════════════════════════════════
# Step 2: 版本号同步到 4 个文件
# ═══════════════════════════════════════════════════════════════

def update_version_file(new_version):
    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    ok(f"VERSION -> {new_version}")


def update_version_info(new_version, version_tuple):
    content = VERSION_INFO_FILE.read_text(encoding="utf-8")
    old = content

    vt = version_tuple + (0,)
    content = re.sub(
        r"filevers=\(\d+,\s*\d+,\s*\d+,\s*\d+\)",
        f"filevers=({vt[0]}, {vt[1]}, {vt[2]}, {vt[3]})",
        content,
    )
    content = re.sub(
        r"prodvers=\(\d+,\s*\d+,\s*\d+,\s*\d+\)",
        f"prodvers=({vt[0]}, {vt[1]}, {vt[2]}, {vt[3]})",
        content,
    )
    content = re.sub(r"'FileVersion',\s*'\d+\.\d+\.\d+'", f"'FileVersion', '{new_version}'", content)
    content = re.sub(r"'ProductVersion',\s*'\d+\.\d+\.\d+'", f"'ProductVersion', '{new_version}'", content)
    content = re.sub(r"'OriginalFilename',\s*'Code-v\d+\.\d+\.\d+\.exe'", f"'OriginalFilename', 'Code-v{new_version}.exe'", content)

    if content == old:
        # Already at the target version (e.g. from a previous partial run).
        ok(f"file_version_info.txt 已为 {new_version}，跳过")
    else:
        VERSION_INFO_FILE.write_text(content, encoding="utf-8")
        ok(f"file_version_info.txt -> {new_version}")


def update_readme(new_version):
    content = README_FILE.read_text(encoding="utf-8")

    new_badge = f"version-{new_version}-2563EB"
    if new_badge not in content:
        content = re.sub(r"version-\d+\.\d+\.\d+-2563EB", new_badge, content)

    new_dl = f"Code-v{new_version}.exe"
    if new_dl not in content:
        content = re.sub(r"Code-v\d+\.\d+\.\d+\.exe", new_dl, content)

    README_FILE.write_text(content, encoding="utf-8")
    ok(f"README.md -> {new_version}")


def create_spec_file(new_version, old_version):
    new_spec = ROOT / f"Code-v{new_version}.spec"

    # Find the newest existing versioned spec file that is not the new one.
    spec_files = sorted(ROOT.glob("Code-v*.spec"), reverse=True)
    old_spec = None
    for sf in spec_files:
        if sf.stem != f"Code-v{new_version}":
            old_spec = sf
            break

    if old_spec is None:
        die(f"找不到旧版 spec 文件作为模板（搜索: Code-v*.spec，排除: {new_spec.name}）")

    content = old_spec.read_text(encoding="utf-8")
    content = content.replace(f"Code-v{old_spec.stem[5:]}", f"Code-v{new_version}")
    content = content.replace(f"name='{old_spec.stem}'", f"name='Code-v{new_version}'")

    new_spec.write_text(content, encoding="utf-8")
    ok(f"{new_spec.name} 已创建（基于 {old_spec.name}）")


# ═══════════════════════════════════════════════════════════════
# Step 3: 一致性校验
# ═══════════════════════════════════════════════════════════════

def verify_version_consistency(new_version, old_version, dry_run=False):
    print("\n-- 版本号一致性校验 --")

    if dry_run:
        # 预演模式：确认当前文件都指向旧版本号（发版前的已知状态）
        v = VERSION_FILE.read_text(encoding="utf-8").strip()
        if v != old_version:
            die(f"VERSION 文件内容与预期不符: {v} != {old_version}（发版前应为旧版本号）")
        ok(f"VERSION = {v}（旧版本号，符合预期）")

        vi = VERSION_INFO_FILE.read_text(encoding="utf-8")
        expected = f"Code-v{old_version}.exe"
        if expected not in vi:
            warn(f"file_version_info.txt 中未找到 {expected}，但预演模式不阻止")
        else:
            ok(f"file_version_info.txt 包含 {expected}（旧版本号）")

        readme = README_FILE.read_text(encoding="utf-8")
        if f"Code-v{old_version}.exe" in readme:
            ok(f"README.md 包含 Code-v{old_version}.exe（旧版本号）")

        old_spec = ROOT / f"Code-v{old_version}.spec"
        if old_spec.exists():
            ok(f"旧 spec 文件存在: {old_spec.name}")
        else:
            die(f"找不到旧 spec 文件: {old_spec.name}")

        print("  预演模式一致性校验通过（将基于 v{0} 发版 v{1}）".format(old_version, new_version))

    else:
        # 正式模式：确认所有文件已更新到新版本号
        v = VERSION_FILE.read_text(encoding="utf-8").strip()
        if v != new_version:
            die(f"VERSION 文件内容不一致: {v} != {new_version}")
        ok(f"VERSION = {v}")

        vi = VERSION_INFO_FILE.read_text(encoding="utf-8")
        expected = f"Code-v{new_version}.exe"
        if expected not in vi:
            die(f"file_version_info.txt 中未找到 {expected}")
        ok(f"file_version_info.txt 包含 {expected}")

        readme = README_FILE.read_text(encoding="utf-8")
        if f"Code-v{new_version}.exe" not in readme:
            die(f"README.md 中未找到 Code-v{new_version}.exe")
        ok(f"README.md 包含 Code-v{new_version}.exe")

        new_spec = ROOT / f"Code-v{new_version}.spec"
        if not new_spec.exists():
            die(f"找不到新 spec 文件: {new_spec.name}")
        ok(f"spec 文件已创建: {new_spec.name}")

        print("  版本号一致性校验通过")


# ═══════════════════════════════════════════════════════════════
# Step 4: 全量测试 + 语法检查
# ═══════════════════════════════════════════════════════════════

def run_tests():
    print("\n-- 全量测试 --")
    rc, stdout, stderr = run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        description="pytest tests -q",
        timeout=180,
    )
    if rc != 0:
        lines = (stdout + stderr).splitlines()
        for line in lines[-20:]:
            print(f"  {line}")
        die("全量测试未通过，请修复后重试")
    ok("全量测试通过")


def run_syntax_checks():
    print("\n-- 语法检查 --")
    checks = [
        (["node", "--check", "app.js"], "node --check app.js"),
        (["node", "--check", "agent-runtime.js"], "node --check agent-runtime.js"),
        ([sys.executable, "-m", "py_compile", "server.py"], "py_compile server.py"),
        ([sys.executable, "-m", "py_compile", "launcher.py"], "py_compile launcher.py"),
        ([sys.executable, "-m", "py_compile", "build_exe.py"], "py_compile build_exe.py"),
    ]
    for cmd, desc in checks:
        rc, stdout, stderr = run(cmd, description=desc)
        if rc != 0:
            die(f"语法检查失败: {desc}\n{stdout}{stderr}")
        ok(desc)
    ok("所有语法检查通过")


def run_git_diff_check():
    rc, stdout, stderr = run(
        ["git", "diff", "--check"],
        description="git diff --check",
    )
    if rc != 0:
        die(f"git diff --check 失败:\n{stdout}{stderr}")
    ok("git diff --check 通过")


# ═══════════════════════════════════════════════════════════════
# Step 5: 构建 EXE
# ═══════════════════════════════════════════════════════════════

def build_exe(new_version):
    print("\n-- 构建 EXE --")
    print("  这可能需要几分钟...")

    start = time.time()
    rc, stdout, stderr = run(
        [sys.executable, str(BUILD_SCRIPT)],
        description="python build_exe.py",
        timeout=600,
    )

    elapsed = time.time() - start
    exe_path = ROOT / "dist" / f"Code-v{new_version}.exe"

    if rc != 0:
        die(f"PyInstaller 构建失败（耗时 {elapsed:.0f}s）")

    if not exe_path.exists():
        die(f"构建完成但找不到产物: {exe_path}")

    size_bytes = exe_path.stat().st_size
    size_mib = size_bytes / (1024 * 1024)
    print(f"  构建耗时: {elapsed:.0f}s")
    print(f"  产物大小: {size_bytes:,} bytes ({size_mib:.2f} MiB)")
    ok(f"EXE 构建成功: {exe_path.name}")


# ═══════════════════════════════════════════════════════════════
# Step 6: EXE 元数据 & SHA-256
# ═══════════════════════════════════════════════════════════════

def verify_exe_metadata(new_version):
    print("\n-- EXE 元数据校验 --")
    exe_path = ROOT / "dist" / f"Code-v{new_version}.exe"

    ps_script = f"""
$f = Get-Item -LiteralPath '{exe_path}'
$v = $f.VersionInfo
"ProductVersion=$($v.ProductVersion)"
"FileVersion=$($v.FileVersion)"
"OriginalFilename=$($v.OriginalFilename)"
""".strip()

    rc, stdout, stderr = run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        description="读取 EXE 版本元数据",
        timeout=30,
    )

    if rc != 0:
        warn(f"无法读取 EXE 元数据（非致命）:\n{stderr}")
        return

    checks = {
        "ProductVersion": new_version,
        "FileVersion": new_version,
        "OriginalFilename": f"Code-v{new_version}.exe",
    }

    for field, expected in checks.items():
        if f"{field}={expected}" in stdout:
            ok(f"{field} = {expected}")
        else:
            warn(f"{field} 不匹配！期望 {expected}")


def compute_sha256(new_version):
    exe_path = ROOT / "dist" / f"Code-v{new_version}.exe"
    sha = hashlib.sha256()
    size = exe_path.stat().st_size
    read = 0
    with open(exe_path, "rb") as f:
        while True:
            chunk = f.read(8 * 1024 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            read += len(chunk)
            pct = read * 100 // size
            print(f"\r  计算 SHA-256: {pct}%", end="", flush=True)
    print()
    hex_digest = sha.hexdigest().upper()
    ok(f"SHA-256: {hex_digest}")
    return hex_digest


# ═══════════════════════════════════════════════════════════════
# Step 7: 生成发布说明
# ═══════════════════════════════════════════════════════════════

def _extract_release_notes_body(content):
    """Extract the hand-written body from current or legacy release notes."""
    text = str(content or "").replace("\r\n", "\n")

    start = text.find(RELEASE_NOTES_BODY_START)
    end = text.find(RELEASE_NOTES_BODY_END)
    if start >= 0 and end > start:
        return text[start + len(RELEASE_NOTES_BODY_START):end].strip()

    generated_at = len(text)
    for heading in _RELEASE_NOTES_GENERATED_HEADINGS:
        index = text.find(heading)
        if index >= 0:
            generated_at = min(generated_at, index)
    text = text[:generated_at]

    text = re.sub(
        r"\A# Code v\d+\.\d+\.\d+ Release Notes\s*\n+"
        r"(?:(?:Date|日期):[^\n]*\n+)?",
        "",
        text,
        count=1,
    )
    return text.strip()


def _render_release_notes(new_version, body, sha256, exe_size, date_str):
    size_mib = exe_size / (1024 * 1024)
    return f"""# Code v{new_version} Release Notes

日期：{date_str}

{RELEASE_NOTES_BODY_START}
{body.strip()}
{RELEASE_NOTES_BODY_END}

## 打包信息

- 版本已更新至 `{new_version}`。
- `VERSION`、`file_version_info.txt`、`README.md` 与 PyInstaller spec 已同步。
- 构建命令：

```bash
python build_exe.py
```

## 下载与校验

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `Code-v{new_version}.exe` | `{exe_size:,} bytes` (`{size_mib:.2f} MiB`) | `{sha256}` |

请确认应用内显示的版本号为 `{new_version}`。

## 相关记录

- 具体实现时间线与文件级改动见 `CHANGELOG.md`。
"""


def generate_release_notes(new_version, sha256, exe_size):
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    release_file = RELEASES_DIR / f"v{new_version}.md"

    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")

    body = RELEASE_NOTES_PLACEHOLDER
    if release_file.exists():
        existing_body = _extract_release_notes_body(
            release_file.read_text(encoding="utf-8"),
        )
        if existing_body:
            body = existing_body
            ok(f"保留已有发布说明正文: {release_file.name}")

    content = _render_release_notes(
        new_version,
        body,
        sha256,
        exe_size,
        date_str,
    )
    release_file.write_text(content, encoding="utf-8")
    ok(f"发布说明: {release_file.name}")
    return release_file


def validate_release_notes(release_file, new_version):
    """Return blocking release-note validation errors."""
    release_file = Path(release_file)
    if not release_file.exists():
        return [f"发布说明不存在: {release_file}"]

    content = release_file.read_text(encoding="utf-8")
    body = _extract_release_notes_body(content)
    errors = []

    meaningful_lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.lstrip().startswith("<!--")
    ]
    if not meaningful_lines:
        errors.append("发布说明正文为空")

    for pattern, message in _RELEASE_NOTES_PLACEHOLDER_PATTERNS:
        if pattern.search(content):
            errors.append(message)

    expected_header = f"# Code v{new_version} Release Notes"
    expected_asset = f"Code-v{new_version}.exe"
    if expected_header not in content:
        errors.append(f"缺少正确标题: {expected_header}")
    if expected_asset not in content:
        errors.append(f"缺少正确发布文件名: {expected_asset}")

    return errors


def require_release_notes_ready(release_file, new_version):
    """Block commit/tag/release when notes are empty or contain placeholders."""
    errors = validate_release_notes(release_file, new_version)
    if errors:
        print("\n  发布说明校验失败:")
        for error in errors:
            print(f"    - {error}")
        die("发布说明未完成，禁止提交、打标签或创建 GitHub Release")
    ok("发布说明正文与占位检查通过")


# ═══════════════════════════════════════════════════════════════
# Step 8: Git 提交 & 打标签
# ═══════════════════════════════════════════════════════════════

def git_commit_and_tag(new_version, dry_run=False):
    print("\n-- Git 提交 & 标签 --")

    files_to_add = [
        "VERSION",
        "file_version_info.txt",
        "README.md",
        f"Code-v{new_version}.spec",
        f"docs/releases/v{new_version}.md",
    ]

    if dry_run:
        print(f"  [DRY RUN] 将暂存: {', '.join(files_to_add)}")
        print(f"  [DRY RUN] 将提交: chore: prepare v{new_version} release metadata")
        print(f"  [DRY RUN] 将打标签: v{new_version}")
        return

    for f in files_to_add:
        filepath = ROOT / f
        if filepath.exists():
            rc, _, stderr = run(["git", "add", str(filepath)], description=f"git add {f}")
            if rc != 0:
                die(f"git add 失败: {f}\n{stderr}")
    ok("文件已暂存")

    msg = f"chore: prepare v{new_version} release metadata"
    rc, stdout, stderr = run(["git", "commit", "-m", msg], description="git commit")
    if rc != 0:
        if "nothing to commit" in (stdout + stderr):
            ok("没有需要提交的变更（可能已提交）")
        else:
            die(f"git commit 失败:\n{stdout}{stderr}")
    else:
        ok("提交成功")

    tag = f"v{new_version}"
    rc, stdout, stderr = run(["git", "tag", tag], description=f"git tag {tag}")
    if rc != 0:
        if "already exists" in stderr:
            if not ask(f"标签 {tag} 已存在，是否删除并重新创建？"):
                die(f"用户取消: 标签 {tag} 已存在")
            run(["git", "tag", "-d", tag], description=f"git tag -d {tag}")
            run(["git", "tag", tag], description=f"git tag {tag}")
    ok(f"标签 {tag} 已创建")


# ═══════════════════════════════════════════════════════════════
# Step 9: 推送到 GitHub
# ═══════════════════════════════════════════════════════════════

def push_to_github(new_version, dry_run=False):
    print("\n-- 推送代码 & 标签 --")

    tag = f"v{new_version}"

    if dry_run:
        print(f"  [DRY RUN] git push origin {DEFAULT_BRANCH}")
        print(f"  [DRY RUN] git push origin {tag}")
        return

    # 先获取远程
    rc, _, stderr = run(["git", "fetch", "origin"], description="git fetch origin")
    if rc != 0:
        warn(f"git fetch 失败，将尝试直接推送:\n{stderr}")

    # 推送分支
    rc, stdout, stderr = run(
        ["git", "push", "origin", DEFAULT_BRANCH],
        description=f"git push origin {DEFAULT_BRANCH}",
        timeout=60,
    )
    if rc != 0:
        print(f"\n  {'='*50}")
        print(f"  X 推送分支失败！")
        print(f"  {'='*50}")
        print(f"  可能原因：网络问题 / 权限不足 / 远程有新提交")
        print(f"\n  请手动处理：")
        print(f"    git push origin {DEFAULT_BRANCH}")
        print(f"\n  STDERR:\n{stderr[-500:]}")
        die("推送分支失败，请人工处理")

    ok(f"分支 {DEFAULT_BRANCH} 推送成功")

    # 推送标签
    rc, stdout, stderr = run(
        ["git", "push", "origin", tag],
        description=f"git push origin {tag}",
        timeout=60,
    )
    if rc != 0:
        print(f"\n  {'='*50}")
        print(f"  X 推送标签失败！")
        print(f"  {'='*50}")
        print(f"  分支已推送成功，但标签 {tag} 推送失败。")
        print(f"\n  请手动处理：")
        print(f"    git push origin {tag}")
        print(f"\n  STDERR:\n{stderr[-500:]}")
        die("推送标签失败，请人工处理")

    ok(f"标签 {tag} 推送成功")


# ═══════════════════════════════════════════════════════════════
# Step 10: 创建 GitHub Release
# ═══════════════════════════════════════════════════════════════

def create_github_release(new_version, sha256, dry_run=False):
    print("\n-- 创建 GitHub Release --")

    tag = f"v{new_version}"
    exe_path = ROOT / "dist" / f"Code-v{new_version}.exe"
    release_notes = ROOT / "docs" / "releases" / f"v{new_version}.md"

    # 检查 gh 是否可用
    if shutil.which("gh") is None:
        print(f"\n  {'='*50}")
        print(f"  X 未找到 GitHub CLI (gh)")
        print(f"  {'='*50}")
        print(f"  安装: winget install GitHub.cli")
        print(f"  登录: gh auth login")
        print(f"\n  代码和标签已推送。请手动创建 Release:")
        print(f"    https://github.com/fhy-A/Code/releases/new?tag={tag}")
        return

    # 检查 gh 登录状态
    rc, stdout, _ = run(["gh", "auth", "status"], description="gh auth status")
    if rc != 0:
        print(f"\n  {'='*50}")
        print(f"  X GitHub CLI 未登录")
        print(f"  {'='*50}")
        print(f"  请运行: gh auth login")
        print(f"\n  代码和标签已推送。请手动创建 Release:")
        print(f"    https://github.com/fhy-A/Code/releases/new?tag={tag}")
        return

    if dry_run:
        print(f"  [DRY RUN] gh release create {tag} {exe_path.name} --notes-file {release_notes.name}")
        return

    cmd = [
        "gh", "release", "create", tag,
        str(exe_path),
        "--title", f"Code v{new_version}",
        "--notes-file", str(release_notes),
    ]

    rc, stdout, stderr = run(cmd, description="gh release create", timeout=120)

    if rc != 0:
        print(f"\n  {'='*50}")
        print(f"  X 创建 GitHub Release 失败！")
        print(f"  {'='*50}")
        print(f"  代码和标签已推送成功。")
        print(f"\n  请手动创建 Release:")
        print(f"    https://github.com/fhy-A/Code/releases/new?tag={tag}")
        print(f"\n  需要上传的文件: {exe_path}")
        print(f"\n  gh 输出:\n{stdout}\n{stderr[-500:]}")
        die("GitHub Release 创建失败，请人工处理")

    ok(f"GitHub Release {tag} 创建成功")
    print(f"  {stdout.strip()}")


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Code 自动发版脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python release.py 0.5.8              发版 0.5.8
  python release.py 0.5.8 --dry-run    预演模式：只检查不修改
  python release.py 0.5.8 --skip-tests 跳过测试（仅当刚跑过）
        """,
    )
    parser.add_argument("version", help="新版本号，如 0.5.8")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试步骤")
    parser.add_argument("--dry-run", action="store_true", help="预演模式：只检查不修改任何文件")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过所有交互确认（供 AI Agent 使用）")
    parser.add_argument("--proxy", default=None,
                        help="HTTPS 代理地址，如 127.0.0.1:18081（默认自动检测 Windows 系统代理）")
    parser.add_argument("--no-proxy", action="store_true", help="禁用代理（跳过自动检测）")
    args = parser.parse_args()

    global _proxy_url

    if args.no_proxy:
        _proxy_url = None
    elif args.proxy:
        _proxy_url = args.proxy
    else:
        detected = detect_windows_proxy()
        if detected:
            _proxy_url = detected

    new_version = args.version
    version_tuple = parse_version(new_version)
    old_version = get_current_version()

    # --yes 模式下跳过所有交互确认
    if args.yes:
        global ask
        def ask(prompt):
            print(f"  ?  {prompt} [y/N]  (--yes: auto y)")
            return True

    # ── 预检 ──
    print("=" * 60)
    print(f"  Code 发版脚本")
    print(f"  旧版本: {old_version}")
    print(f"  新版本: {new_version}")
    print(f"  模式: {'预演 (dry-run)' if args.dry_run else '正式发版'}")
    print(f"  代理: {_proxy_url or '无（直连）'}")
    print("=" * 60)

    if not args.dry_run:
        # 检查工作区
        rc, stdout, _ = run(["git", "status", "--short"], description="git status")
        if stdout.strip():
            print(f"\n  未跟踪/未提交的文件:\n{stdout}")
            if not ask("工作区不干净，是否继续？"):
                die("用户取消")

        if not ask(f"确认从 v{old_version} 发版到 v{new_version}？"):
            print("  已取消")
            return

    # ── Phase 1: 版本号同步 ──
    print("\n" + "=" * 60)
    print("  Phase 1: 版本号同步")
    print("=" * 60)

    if not args.dry_run:
        update_version_file(new_version)
        update_version_info(new_version, version_tuple)
        update_readme(new_version)
        create_spec_file(new_version, old_version)

    verify_version_consistency(new_version, old_version, dry_run=args.dry_run)

    # ── Phase 2: 代码质量检查 ──
    if not args.skip_tests:
        print("\n" + "=" * 60)
        print("  Phase 2: 代码质量检查")
        print("=" * 60)

        if not args.dry_run:
            run_tests()
            run_git_diff_check()
        run_syntax_checks()
    else:
        warn("跳过测试（--skip-tests）")
        run_syntax_checks()

    # ── Phase 3: 构建 EXE ──
    print("\n" + "=" * 60)
    print("  Phase 3: 构建 EXE")
    print("=" * 60)

    if not args.dry_run:
        build_exe(new_version)
    else:
        print("  [DRY RUN] 跳过构建")

    # ── Phase 4: EXE 验证 ──
    print("\n" + "=" * 60)
    print("  Phase 4: EXE 验证")
    print("=" * 60)

    if not args.dry_run:
        verify_exe_metadata(new_version)
        sha256 = compute_sha256(new_version)
        exe_size = (ROOT / "dist" / f"Code-v{new_version}.exe").stat().st_size
    else:
        sha256 = "DRY_RUN_SHA256"
        exe_size = 0
        print("  [DRY RUN] 跳过 EXE 验证")

    # ── Phase 5: 生成发布说明 ──
    print("\n" + "=" * 60)
    print("  Phase 5: 生成发布说明")
    print("=" * 60)

    if not args.dry_run:
        release_file = generate_release_notes(new_version, sha256, exe_size)
        initial_errors = validate_release_notes(release_file, new_version)

        if initial_errors and args.yes:
            print(f"\n  请先编辑发布说明后重新运行本脚本:")
            print(f"    docs/releases/v{new_version}.md")
        elif not args.yes and not ask("发布说明是否已编辑好？"):
            print(f"\n  请编辑发布说明后重新运行本脚本，或手动完成后续步骤。")
            print(f"  发布说明位置: docs/releases/v{new_version}.md")
            print(f"\n  后续手动步骤:")
            print(f"    git add -A && git commit -m 'chore: prepare v{new_version} release metadata'")
            print(f"    git tag v{new_version}")
            print(f"    git push origin {DEFAULT_BRANCH} && git push origin v{new_version}")
            print(f"    gh release create v{new_version} dist/Code-v{new_version}.exe --notes-file docs/releases/v{new_version}.md")
            die("用户暂停以编辑发布说明")

        require_release_notes_ready(release_file, new_version)
    else:
        print("  [DRY RUN] 跳过发布说明生成")

    # ── Phase 6: Git 提交 & 标签 ──
    print("\n" + "=" * 60)
    print("  Phase 6: Git 提交 & 标签")
    print("=" * 60)
    git_commit_and_tag(new_version, dry_run=args.dry_run)

    # ── Phase 7: 推送 & GitHub Release ──
    print("\n" + "=" * 60)
    print("  Phase 7: 推送 & GitHub Release")
    print("=" * 60)
    push_to_github(new_version, dry_run=args.dry_run)
    create_github_release(new_version, sha256, dry_run=args.dry_run)

    # ── 完成 ──
    print("\n" + "=" * 60)
    print(f"  Code v{new_version} 发版完成!")
    print("=" * 60)

    if args.dry_run:
        print("\n  [预演模式 -- 未做任何实际修改]")


if __name__ == "__main__":
    main()
