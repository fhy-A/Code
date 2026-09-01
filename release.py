"""
Code 自动发版脚本

保留项目已有一次性发版流程，并提供可验证的两阶段发布：
  1. 版本号同步（VERSION / file_version_info.txt / README.md）
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
  python release.py 0.5.8 --prepare      完整验证并准备本地候选
  python release.py 0.5.8 --publish-prepared  发布精确匹配的候选
  python release.py 0.5.8 --resume       审计并续接已开始的发布
  python release.py prepare 0.5.8        prepare 的兼容别名
  python release.py 0.5.8 --skip-tests   prepared-only 兼容入口
  python release.py 0.5.8 --dry-run      预演模式
  python release.py 0.5.8 --proxy 127.0.0.1:18081  指定代理
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from devtools.release_state import (
    CredentialError,
    SCHEMA as RELEASE_CREDENTIAL_SCHEMA,
    invalidate_credential,
    load_credential,
    record_files,
    resolve_credential_path,
    save_credential,
    sha256_bytes,
    sha256_file,
    validate_recorded_files,
)
from devtools.verification import (
    CHECKS,
    SYNTAX_CHECK_IDS,
    get_release_check_ids,
    get_release_definition_fingerprint,
)

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "VERSION"
VERSION_INFO_FILE = ROOT / "file_version_info.txt"
README_FILE = ROOT / "README.md"
RELEASES_DIR = ROOT / "docs" / "releases"
BUILD_SCRIPT = ROOT / "build_exe.py"
FRONTEND_BUILD_SCRIPT = ROOT / "scripts" / "build-frontend.mjs"
FRONTEND_BUNDLE = ROOT / "dist" / "frontend" / "code.bundle.js"
DEFAULT_BRANCH = "master"
RELEASE_ACTIONS = ("prepare", "publish-prepared", "resume")
GH_COMMAND = ("gh",)
RELEASE_NOTES_PLACEHOLDER = "[发布说明待补充 -- 请在此描述本版本的主要改动]"
RELEASE_NOTES_BODY_START = "<!-- code-release-notes:body:start -->"
RELEASE_NOTES_BODY_END = "<!-- code-release-notes:body:end -->"
README_VERSION_BADGE_PATTERN = re.compile(
    r'(?P<prefix><img src="https://img\.shields\.io/badge/version-)'
    r'(?P<url_version>\d+\.\d+\.\d+)'
    r'(?P<middle>-2563EB" alt="Version )'
    r'(?P<alt_version>\d+\.\d+\.\d+)'
    r'(?P<suffix>">)'
)
README_VERSIONED_EXE_PATTERN = re.compile(r"Code-v(?P<version>\d+\.\d+\.\d+)\.exe")

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

def _console_safe(value):
    """Return text that can always be written to the active console."""
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return text.encode(encoding, errors="backslashreplace").decode(encoding)


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
            print(_console_safe(f"  STDERR:\n{result.stderr[-500:]}"))
        if result.stdout:
            print(_console_safe(f"  STDOUT:\n{result.stdout[-500:]}"))
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


def _utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _quiet_env():
    env = os.environ.copy()
    if _proxy_url:
        env.update(_build_proxy_env(_proxy_url))
    return env


def run_quiet(cmd, *, cwd=None, timeout=120):
    """Run a metadata/preflight command without echoing possibly sensitive output."""
    return subprocess.run(
        list(cmd),
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=_quiet_env(),
    )


def _required_quiet(cmd, description, *, timeout=120):
    try:
        result = run_quiet(cmd, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        die(f"{description}无法执行: {type(exc).__name__}")
    if result.returncode != 0:
        die(f"{description}失败")
    return result.stdout.strip()


def _gh_cmd(*args):
    return [*GH_COMMAND, *args]


def _gh_is_available():
    executable = GH_COMMAND[0]
    return shutil.which(executable) is not None or Path(executable).is_file()


def _release_paths(version):
    return (
        "VERSION",
        "file_version_info.txt",
        "README.md",
        f"docs/releases/v{version}.md",
    )


def _credential_path(version):
    try:
        return resolve_credential_path(ROOT, version)
    except CredentialError as exc:
        die(str(exc))


def _git_head():
    return _required_quiet(["git", "rev-parse", "HEAD"], "读取 HEAD ")


def _git_branch():
    return _required_quiet(
        ["git", "branch", "--show-current"],
        "读取当前分支 ",
    )


def _git_index_tree():
    return _required_quiet(["git", "write-tree"], "读取 Git index ")


def _git_name_lines(*args):
    output = _required_quiet(["git", *args], "读取 Git 文件列表 ")
    return tuple(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())


def _git_blob_hash(path, *, revision=None):
    if revision is None:
        result = run_quiet(["git", "hash-object", f"--path={path}", "--", path])
    else:
        result = run_quiet(["git", "rev-parse", f"{revision}:{path}"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _changed_release_paths(base_head, release_paths):
    changed = []
    for path in release_paths:
        current = _git_blob_hash(path)
        if current is None:
            die(f"发布白名单文件无法哈希: {path}")
        if current != _git_blob_hash(path, revision=base_head):
            changed.append(path)
    return tuple(changed)


def _tracked_state_digest(reference, excluded_paths):
    cmd = ["git", "diff", "--binary", reference, "--", "."]
    cmd.extend(f":(exclude){path}" for path in excluded_paths)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            timeout=120,
            check=False,
            env=_quiet_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        die(f"无法生成候选 tracked 状态摘要: {type(exc).__name__}")
    if result.returncode != 0:
        die("无法生成候选 tracked 状态摘要")
    return sha256_bytes(result.stdout)


def _snapshot_release_files(relative_paths):
    snapshot = {}
    for relative in relative_paths:
        path = ROOT / relative
        snapshot[relative] = path.read_bytes() if path.exists() else None
    return snapshot


def _restore_release_files(snapshot):
    for relative, content in snapshot.items():
        path = ROOT / relative
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)


def _ensure_cached_empty():
    cached = _git_name_lines("diff", "--cached", "--name-only")
    if cached:
        die("暂存区不为空，禁止启动两阶段发布")


def _read_remote_tag(tag):
    result = run_quiet(
        ["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
    )
    if result.returncode != 0:
        die("无法读取远端标签状态")
    hashes = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    return hashes[-1] if hashes else None


def _read_remote_branch():
    result = run_quiet(
        ["git", "ls-remote", "--heads", "origin", f"refs/heads/{DEFAULT_BRANCH}"],
    )
    if result.returncode != 0:
        die("origin 不可达或无法读取远端基线")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        die(f"远端分支 {DEFAULT_BRANCH} 不存在或状态不唯一")
    return lines[0].split()[0]


def _read_remote_release(tag, repository):
    result = run_quiet(
        _gh_cmd(
            "release",
            "view",
            tag,
            "--repo",
            repository,
            "--json",
            "tagName,name,body,targetCommitish,assets",
        ),
    )
    if result.returncode != 0:
        detail = (result.stdout + "\n" + result.stderr).lower()
        if "not found" in detail or "release not found" in detail or "http 404" in detail:
            return None
        die("无法读取 GitHub Release 状态")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError:
        die("GitHub Release 状态不是有效 JSON")
    if not isinstance(value, dict):
        die("GitHub Release 状态格式无效")
    return value


def remote_read_only_preflight(version, base_head):
    """Verify remote readiness before touching release metadata."""
    if not _gh_is_available():
        die("未找到 GitHub CLI (gh)，prepare 未修改发布元数据")
    auth = run_quiet(_gh_cmd("auth", "status"))
    if auth.returncode != 0:
        die("GitHub CLI 未登录，prepare 未修改发布元数据")
    repository = _required_quiet(
        _gh_cmd("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"),
        "读取 GitHub 仓库身份 ",
    )
    remote_head = _read_remote_branch()
    ancestor = run_quiet(["git", "merge-base", "--is-ancestor", remote_head, base_head])
    if ancestor.returncode != 0:
        die("远端 master 不是当前候选 HEAD 的祖先，禁止 prepare")
    tag = f"v{version}"
    local_tag = run_quiet(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}"])
    if local_tag.returncode == 0:
        die(f"本地标签 {tag} 已存在，禁止覆盖或重建")
    if _read_remote_tag(tag) is not None:
        die(f"远端标签 {tag} 已存在，禁止覆盖")
    if _read_remote_release(tag, repository) is not None:
        die(f"GitHub Release {tag} 已存在，禁止覆盖")
    return {
        "repository": repository,
        "originHead": remote_head,
    }


def _environment_fingerprint(repository):
    git_version = _required_quiet(["git", "--version"], "读取 Git 版本 ").splitlines()[0]
    gh_version = _required_quiet(_gh_cmd("--version"), "读取 gh 版本 ").splitlines()[0]
    return {
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "git": git_version,
        "gh": gh_version,
        "repository": repository,
        "branch": DEFAULT_BRANCH,
    }


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


def _readme_version_metadata(content):
    badge_matches = list(README_VERSION_BADGE_PATTERN.finditer(content))
    if len(badge_matches) != 1:
        die(
            "README.md 必须恰好包含一个 canonical 版本徽章"
            f"（实际 {len(badge_matches)} 个）",
        )
    exe_versions = [
        match.group("version")
        for match in README_VERSIONED_EXE_PATTERN.finditer(content)
    ]
    if not exe_versions:
        die("README.md 中未找到版本化 EXE 下载名 Code-vX.Y.Z.exe")
    return badge_matches[0], exe_versions


def _verify_readme_version_metadata(content, expected_version):
    badge, exe_versions = _readme_version_metadata(content)
    url_version = badge.group("url_version")
    alt_version = badge.group("alt_version")
    if url_version != expected_version:
        die(
            "README.md 版本徽章 URL 不一致: "
            f"{url_version} != {expected_version}",
        )
    if alt_version != expected_version:
        die(
            "README.md 版本徽章 alt 不一致: "
            f"{alt_version} != {expected_version}",
        )
    mismatched_exe_versions = sorted(
        {version for version in exe_versions if version != expected_version},
    )
    if mismatched_exe_versions:
        die(
            "README.md 版本化 EXE 下载名不一致: "
            + ", ".join(mismatched_exe_versions)
            + f" != {expected_version}",
        )
    ok(
        "README.md 版本徽章 URL / alt 与 EXE 下载名均为 "
        f"{expected_version}",
    )


def update_readme(new_version):
    original = README_FILE.read_text(encoding="utf-8")
    content = original
    badge, _ = _readme_version_metadata(content)
    replacement = (
        badge.group("prefix")
        + new_version
        + badge.group("middle")
        + new_version
        + badge.group("suffix")
    )
    content = content[:badge.start()] + replacement + content[badge.end():]
    content = README_VERSIONED_EXE_PATTERN.sub(
        f"Code-v{new_version}.exe",
        content,
    )
    _verify_readme_version_metadata(content, new_version)
    if content != original:
        README_FILE.write_text(content, encoding="utf-8")
    ok(f"README.md -> {new_version}")


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
        _verify_readme_version_metadata(readme, old_version)

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
        _verify_readme_version_metadata(readme, new_version)

        print("  版本号一致性校验通过")


# ═══════════════════════════════════════════════════════════════
# Step 4: 全量测试 + 语法检查
# ═══════════════════════════════════════════════════════════════

def run_tests():
    print("\n-- 全量测试 --")
    spec = CHECKS["pytest_full"]
    rc, stdout, stderr = run(
        list(spec.command),
        description="pytest tests -q",
        timeout=spec.timeout,
    )
    if rc != 0:
        lines = (stdout + stderr).splitlines()
        for line in lines[-20:]:
            print(f"  {line}")
        die("全量测试未通过，请修复后重试")
    ok("全量测试通过")


def run_harness_replay_gate():
    """Run the published single-run replay command as a release gate."""
    print("\n-- Harness replay 门禁 --")
    spec = CHECKS["harness_replay"]

    def bounded_diagnostic(*values):
        parts = []
        for value in values:
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            text = str(value or "").strip()
            if text:
                parts.extend(text.splitlines())
        detail = "\n".join(parts[-20:])
        if len(detail) > 2000:
            detail = detail[-2000:]
        return f"\n{detail}" if detail else ""

    try:
        rc, stdout, stderr = run(
            list(spec.command),
            description="npm run verify:harness-replay",
            timeout=spec.timeout,
        )
    except subprocess.TimeoutExpired as exc:
        die(
            "Harness replay 门禁超时（30 秒）"
            + bounded_diagnostic(exc.stdout, exc.stderr),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        die(
            "Harness replay 门禁无法启动"
            + bounded_diagnostic(type(exc).__name__, exc),
        )

    if rc != 0:
        die(
            f"Harness replay 门禁失败（退出码 {rc}）"
            + bounded_diagnostic(stdout, stderr),
        )
    ok("Harness replay 门禁通过")


def run_syntax_checks():
    print("\n-- 语法检查 --")
    for check_id in SYNTAX_CHECK_IDS:
        spec = CHECKS[check_id]
        rc, stdout, stderr = run(
            list(spec.command),
            description=spec.label,
            timeout=spec.timeout,
        )
        if rc != 0:
            die(f"语法检查失败: {spec.label}\n{stdout}{stderr}")
        ok(spec.label)
    ok("所有语法检查通过")


def run_git_diff_check():
    spec = CHECKS["git_diff_check"]
    rc, stdout, stderr = run(
        list(spec.command),
        description="git diff --check",
        timeout=spec.timeout,
    )
    if rc != 0:
        die(f"git diff --check 失败:\n{stdout}{stderr}")
    ok("git diff --check 通过")


def prepare_frontend_assets(build=True):
    """Build when allowed, then require fresh and syntactically valid assets."""
    print("\n-- 前端构建门禁 --")
    check_ids = []
    if build:
        check_ids.append("frontend_build")
    check_ids.extend(("frontend_freshness", "frontend_bundle_syntax"))

    for check_id in check_ids:
        spec = CHECKS[check_id]
        rc, stdout, stderr = run(
            list(spec.command),
            description=spec.label,
            timeout=spec.timeout,
        )
        if rc != 0:
            die(f"前端构建门禁失败: {spec.label}\n{stdout}{stderr}")
        ok(spec.label)


def run_release_quality_checks(*, dry_run, skip_tests):
    """Run the shared release definition once in its canonical order.

    Non-dry-run CLI trust skipping is guarded before this function and routes
    through a sealed prepared credential.  The subset remains here so dry-run
    behavior and direct compatibility tests keep the historical definition.
    """
    check_ids = get_release_check_ids(dry_run=dry_run, skip_tests=skip_tests)
    consumed = []

    frontend_ids = tuple(
        check_id
        for check_id in check_ids
        if check_id in {
            "frontend_build",
            "frontend_freshness",
            "frontend_bundle_syntax",
        }
    )
    if frontend_ids:
        prepare_frontend_assets(build="frontend_build" in frontend_ids)
        consumed.extend(frontend_ids)

    if "pytest_full" in check_ids:
        run_tests()
        consumed.append("pytest_full")
    if "harness_replay" in check_ids:
        run_harness_replay_gate()
        consumed.append("harness_replay")
    if "git_diff_check" in check_ids:
        run_git_diff_check()
        consumed.append("git_diff_check")

    if skip_tests:
        warn("跳过测试（--skip-tests）")

    syntax_ids = tuple(check_id for check_id in check_ids if check_id in SYNTAX_CHECK_IDS)
    if syntax_ids:
        run_syntax_checks()
        consumed.extend(syntax_ids)

    if tuple(consumed) != check_ids:
        die("共享 release 验证定义包含未被执行的检查项")


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
        die(f"EXE 构建流程失败（耗时 {elapsed:.0f}s）")

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

def collect_exe_metadata(new_version):
    exe_path = ROOT / "dist" / f"Code-v{new_version}.exe"
    if not exe_path.is_file():
        return None, f"EXE 不存在: {exe_path.name}"

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
        return None, f"无法读取 EXE 元数据: {stderr.strip()}"

    metadata = {}
    for line in stdout.splitlines():
        if "=" in line:
            field, value = line.split("=", 1)
            metadata[field.strip()] = value.strip()
    return metadata, None


def _expected_exe_metadata(new_version):
    return {
        "ProductVersion": new_version,
        "FileVersion": new_version,
        "OriginalFilename": f"Code-v{new_version}.exe",
    }


def verify_exe_metadata(new_version):
    """Preserve the legacy one-shot warning behavior for PE metadata."""
    print("\n-- EXE 元数据校验 --")
    metadata, error = collect_exe_metadata(new_version)
    if error:
        warn(f"{error}（非致命）")
        return None

    for field, expected in _expected_exe_metadata(new_version).items():
        if metadata.get(field) == expected:
            ok(f"{field} = {expected}")
        else:
            warn(f"{field} 不匹配！期望 {expected}")
    return metadata


def require_exe_metadata(new_version):
    """Fail closed for prepared credentials and return exact PE metadata."""
    print("\n-- EXE 元数据严格校验 --")
    metadata, error = collect_exe_metadata(new_version)
    if error:
        die(error)
    mismatches = [
        f"{field}: {metadata.get(field)!r} != {expected!r}"
        for field, expected in _expected_exe_metadata(new_version).items()
        if metadata.get(field) != expected
    ]
    if mismatches:
        die("EXE 元数据不匹配: " + "; ".join(mismatches))
    for field, expected in _expected_exe_metadata(new_version).items():
        ok(f"{field} = {expected}")
    return {field: metadata[field] for field in _expected_exe_metadata(new_version)}


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
- `VERSION`、`file_version_info.txt` 与 `README.md` 已同步。
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

- 具体实现时间线与文件级改动见 `docs/development-log/README.md` 索引及其日期文件。
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
# 两阶段发布：prepare 凭证与可恢复 publish
# ═══════════════════════════════════════════════════════════════

def _load_prepared_credential(version):
    path = _credential_path(version)
    try:
        credential = load_credential(path)
    except CredentialError as exc:
        die(str(exc))
    if credential.get("version") != version or credential.get("tag") != f"v{version}":
        die("prepared 凭证与目标版本不匹配")
    return path, credential


def _validate_static_credential(credential, version):
    recorded_paths = tuple(record.get("path") for record in credential["releaseFiles"])
    if recorded_paths != _release_paths(version):
        die("prepared 凭证的发布白名单不完整或顺序异常")
    if any(not record.get("gitBlob") for record in credential["releaseFiles"]):
        die("prepared 凭证缺少发布文件 Git blob 绑定")
    errors = validate_recorded_files(ROOT, credential["releaseFiles"])
    if errors:
        die("prepared 凭证失效: " + "; ".join(errors))

    verification = credential["verification"]
    expected_checks = list(get_release_check_ids(dry_run=False, skip_tests=False))
    if verification.get("checkIds") != expected_checks:
        die("prepared 凭证中的 release 门禁顺序不匹配")
    if verification.get("definitionSha256") != get_release_definition_fingerprint():
        die("release 验证定义已漂移，请重新 prepare")
    if "h4" in verification.get("checkIds", []):
        die("prepared 凭证错误地包含 H4，禁止发布")

    repository = credential["environment"].get("repository")
    if not repository:
        die("prepared 凭证缺少仓库身份")
    if credential["environment"] != _environment_fingerprint(repository):
        die("发布环境指纹已漂移，请重新 prepare")

    artifact = credential["artifact"]
    artifact_relative = str(artifact.get("path", ""))
    if artifact_relative != f"dist/Code-v{version}.exe":
        die("prepared 凭证中的 EXE 路径不受支持")
    artifact_path = ROOT / artifact_relative
    if not artifact_path.is_file():
        die("prepared EXE 缺失，请重新 prepare")
    if artifact_path.stat().st_size != artifact.get("size"):
        die("prepared EXE 大小变化，请重新 prepare")
    if sha256_file(artifact_path) != artifact.get("sha256"):
        die("prepared EXE 哈希变化，请重新 prepare")
    pe_metadata = require_exe_metadata(version)
    if pe_metadata != artifact.get("peMetadata"):
        die("prepared EXE PE 元数据变化，请重新 prepare")

    release_file = ROOT / f"docs/releases/v{version}.md"
    require_release_notes_ready(release_file, version)
    if get_current_version() != version:
        die("当前 VERSION 与 prepared 凭证不匹配")


def _validate_prepared_candidate(credential, version):
    if credential.get("state") != "prepared":
        die("凭证不处于 prepared 状态；已开始的流程只能使用 resume")
    baseline = credential["baseline"]
    release_paths = tuple(record["path"] for record in credential["releaseFiles"])
    _ensure_cached_empty()
    if _git_branch() != DEFAULT_BRANCH:
        die(f"当前分支不是 {DEFAULT_BRANCH}")
    if _git_head() != baseline.get("head"):
        die("候选基线 HEAD 已漂移，请重新 prepare")
    if _git_index_tree() != baseline.get("indexTree"):
        die("候选 index 状态已漂移，请重新 prepare")
    if _tracked_state_digest(baseline["head"], release_paths) != baseline.get("outsideTrackedSha256"):
        die("发布白名单外 tracked 状态已漂移，请重新 prepare")
    changed = _changed_release_paths(baseline["head"], release_paths)
    if list(changed) != credential.get("changedReleaseFiles"):
        die("候选发布文件集合已漂移，请重新 prepare")
    _validate_static_credential(credential, version)
    remote = remote_read_only_preflight(version, baseline["head"])
    if remote.get("originHead") != baseline.get("originHead"):
        die("远端 master 已漂移，请重新 prepare")
    if remote.get("repository") != credential["environment"].get("repository"):
        die("GitHub 仓库身份已漂移，请重新 prepare")


def prepare_release(version):
    """Create a fully verified local candidate and sealed credential."""
    version_tuple = parse_version(version)
    old_version = get_current_version()
    if version_tuple <= parse_version(old_version):
        die(f"prepare 目标版本必须高于当前版本 {old_version}")
    if _git_branch() != DEFAULT_BRANCH:
        die(f"prepare 必须在 {DEFAULT_BRANCH} 分支运行")
    _ensure_cached_empty()

    base_head = _git_head()
    credential_path = _credential_path(version)
    try:
        remote = remote_read_only_preflight(version, base_head)
    except BaseException:
        invalidate_credential(credential_path)
        raise

    invalidate_credential(credential_path)
    release_paths = _release_paths(version)
    snapshot = _snapshot_release_files(release_paths)
    index_tree = _git_index_tree()
    outside_before = _tracked_state_digest(base_head, release_paths)

    try:
        update_version_file(version)
        update_version_info(version, version_tuple)
        update_readme(version)
        verify_version_consistency(version, old_version, dry_run=False)

        run_release_quality_checks(dry_run=False, skip_tests=False)
        build_exe(version)
        pe_metadata = require_exe_metadata(version)
        exe_path = ROOT / "dist" / f"Code-v{version}.exe"
        exe_sha = compute_sha256(version)
        release_file = generate_release_notes(version, exe_sha, exe_path.stat().st_size)
        require_release_notes_ready(release_file, version)

        if _git_head() != base_head or _git_index_tree() != index_tree:
            die("prepare 期间 HEAD 或 index 被修改")
        outside_after = _tracked_state_digest(base_head, release_paths)
        if outside_after != outside_before:
            die("prepare 产生了发布白名单外 tracked 差量")

        release_records = record_files(ROOT, release_paths)
        for record in release_records:
            record["gitBlob"] = _git_blob_hash(record["path"])
        changed_release_files = list(_changed_release_paths(base_head, release_paths))
        if not changed_release_files:
            die("prepare 未产生任何发布元数据差量")

        credential = {
            "schema": RELEASE_CREDENTIAL_SCHEMA,
            "version": version,
            "tag": f"v{version}",
            "state": "prepared",
            "createdAt": _utc_now(),
            "baseline": {
                "head": base_head,
                "branch": DEFAULT_BRANCH,
                "originHead": remote["originHead"],
                "indexTree": index_tree,
                "outsideTrackedSha256": outside_before,
                "oldVersion": old_version,
            },
            "releaseFiles": release_records,
            "changedReleaseFiles": changed_release_files,
            "verification": {
                "definitionSha256": get_release_definition_fingerprint(),
                "checkIds": list(get_release_check_ids(dry_run=False, skip_tests=False)),
                "completedAt": _utc_now(),
            },
            "artifact": {
                "path": f"dist/Code-v{version}.exe",
                "size": exe_path.stat().st_size,
                "sha256": sha256_file(exe_path),
                "peMetadata": pe_metadata,
            },
            "environment": _environment_fingerprint(remote["repository"]),
            "publication": {
                "startedAt": None,
                "commit": None,
                "lastCompleted": "prepared",
                "completedAt": None,
            },
        }
        save_credential(credential_path, credential)
        ok(f"prepared 凭证已写入 Git 内部路径: code-release/v{version}.json")
        print(f"  下一步: python release.py {version} --publish-prepared")
    except BaseException:
        _restore_release_files(snapshot)
        invalidate_credential(credential_path)
        raise


def _verify_release_commit(credential, commit):
    baseline = credential["baseline"]["head"]
    parent = run_quiet(["git", "rev-parse", f"{commit}^"])
    if parent.returncode != 0 or parent.stdout.strip() != baseline:
        die("本地发布提交父节点与 prepared 基线不一致")
    subject = _required_quiet(["git", "show", "-s", "--format=%s", commit], "读取发布提交 ")
    expected_subject = f"chore: prepare v{credential['version']} release metadata"
    if subject != expected_subject:
        die("本地发布提交主题与凭证不一致")
    changed = _git_name_lines("diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    if sorted(changed) != sorted(credential["changedReleaseFiles"]):
        die("本地发布提交文件集合与凭证不一致")
    records = {record["path"]: record for record in credential["releaseFiles"]}
    for path in credential["changedReleaseFiles"]:
        blob = _git_blob_hash(path, revision=commit)
        if blob is None or blob != records[path].get("gitBlob"):
            die(f"本地发布提交内容与凭证不一致: {path}")


def _save_publication_progress(path, credential, step, *, commit=None, completed=False):
    if commit is not None:
        credential["publication"]["commit"] = commit
    credential["publication"]["lastCompleted"] = step
    if completed:
        credential["state"] = "published"
        credential["publication"]["completedAt"] = _utc_now()
    return save_credential(path, credential)


def _ensure_release_commit(path, credential):
    baseline = credential["baseline"]["head"]
    current = _git_head()
    recorded = credential["publication"].get("commit")
    if recorded:
        if current != recorded:
            die("master HEAD 与凭证记录的发布提交不一致")
        _verify_release_commit(credential, recorded)
        _ensure_cached_empty()
        return recorded, credential

    if current == baseline:
        changed = credential["changedReleaseFiles"]
        cached = _git_name_lines("diff", "--cached", "--name-only")
        if not cached:
            rc, _, _ = run(["git", "add", "--", *changed], description="暂存发布白名单")
            if rc != 0:
                die("暂存发布白名单失败")
            cached = _git_name_lines("diff", "--cached", "--name-only")
        if sorted(cached) != sorted(changed):
            die("暂存区不只包含 prepared 发布白名单")
        records = {record["path"]: record for record in credential["releaseFiles"]}
        for release_path in changed:
            staged_blob = _required_quiet(
                ["git", "rev-parse", f":{release_path}"],
                "读取暂存发布文件 ",
            )
            if staged_blob != records[release_path].get("gitBlob"):
                die(f"暂存发布文件与 prepared 凭证不一致: {release_path}")
        message = f"chore: prepare v{credential['version']} release metadata"
        rc, _, _ = run(
            ["git", "commit", "-m", message, "--only", "--", *changed],
            description="创建 prepared 发布提交",
        )
        if rc != 0:
            die("创建 prepared 发布提交失败")
        current = _git_head()
    _verify_release_commit(credential, current)
    _ensure_cached_empty()
    credential = _save_publication_progress(path, credential, "commit", commit=current)
    return current, credential


def _local_tag_commit(tag):
    result = run_quiet(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}"])
    return result.stdout.strip() if result.returncode == 0 else None


def _ensure_local_tag(path, credential, commit):
    tag = credential["tag"]
    existing = _local_tag_commit(tag)
    if existing is None:
        rc, _, _ = run(["git", "tag", tag, commit], description=f"git tag {tag}")
        if rc != 0:
            die(f"创建本地标签 {tag} 失败")
    elif existing != commit:
        die(f"本地标签 {tag} 指向不同提交，禁止删除或重建")
    credential = _save_publication_progress(path, credential, "local-tag")
    return credential


def _ensure_remote_branch(path, credential, commit):
    remote = _read_remote_branch()
    if remote == commit:
        pass
    elif remote == credential["baseline"]["originHead"]:
        rc, _, _ = run(
            ["git", "push", "origin", f"{commit}:refs/heads/{DEFAULT_BRANCH}"],
            description=f"git push origin {DEFAULT_BRANCH}",
            timeout=60,
        )
        if rc != 0 or _read_remote_branch() != commit:
            die("推送 master 失败或远端结果无法确认")
    else:
        die("远端 master 与 prepared 基线/发布提交均不一致，禁止覆盖")
    return _save_publication_progress(path, credential, "remote-branch")


def _ensure_remote_tag(path, credential, commit):
    tag = credential["tag"]
    remote = _read_remote_tag(tag)
    if remote is None:
        rc, _, _ = run(
            ["git", "push", "origin", f"refs/tags/{tag}:refs/tags/{tag}"],
            description=f"git push origin {tag}",
            timeout=60,
        )
        if rc != 0 or _read_remote_tag(tag) != commit:
            die(f"推送标签 {tag} 失败或远端结果无法确认")
    elif remote != commit:
        die(f"远端标签 {tag} 指向不同提交，禁止覆盖")
    return _save_publication_progress(path, credential, "remote-tag")


def _audit_release_metadata(info, credential):
    version = credential["version"]
    expected_body = (ROOT / f"docs/releases/v{version}.md").read_text(encoding="utf-8")
    if info.get("tagName") != credential["tag"]:
        die("GitHub Release tag 与凭证不一致")
    if info.get("name") != f"Code v{version}":
        die("GitHub Release 标题与凭证不一致")
    if str(info.get("body", "")).replace("\r\n", "\n") != expected_body.replace("\r\n", "\n"):
        die("GitHub Release 正文与凭证不一致")


def _ensure_github_release(path, credential):
    repository = credential["environment"]["repository"]
    tag = credential["tag"]
    info = _read_remote_release(tag, repository)
    if info is None:
        notes = ROOT / f"docs/releases/v{credential['version']}.md"
        result = run_quiet(
            _gh_cmd(
                "release", "create", tag,
                "--repo", repository,
                "--title", f"Code v{credential['version']}",
                "--notes-file", str(notes),
            ),
            timeout=120,
        )
        if result.returncode != 0:
            die("创建 GitHub Release 失败")
        info = _read_remote_release(tag, repository)
        if info is None:
            die("GitHub Release 创建后无法确认")
    _audit_release_metadata(info, credential)
    return _save_publication_progress(path, credential, "release"), info


def _asset_digest_from_download(credential):
    repository = credential["environment"]["repository"]
    artifact = credential["artifact"]
    name = Path(artifact["path"]).name
    with tempfile.TemporaryDirectory() as directory:
        destination = Path(directory) / name
        result = run_quiet(
            _gh_cmd(
                "release", "download", credential["tag"],
                "--repo", repository,
                "--pattern", name,
                "--output", str(destination),
            ),
            timeout=300,
        )
        if result.returncode != 0 or not destination.is_file():
            die("无法下载既有 Release 资产进行哈希审计")
        return sha256_file(destination)


def _audit_release_asset(info, credential):
    artifact = credential["artifact"]
    name = Path(artifact["path"]).name
    assets = info.get("assets") or []
    if not isinstance(assets, list):
        die("GitHub Release 资产状态格式无效")
    unexpected = [asset.get("name") for asset in assets if asset.get("name") != name]
    if unexpected:
        die("GitHub Release 存在凭证外资产，禁止继续")
    matches = [asset for asset in assets if asset.get("name") == name]
    if len(matches) != 1:
        die("GitHub Release 资产数量与凭证不一致")
    asset = matches[0]
    if asset.get("size") != artifact["size"]:
        die("GitHub Release 资产大小与凭证不一致")
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        remote_sha = digest.split(":", 1)[1].lower()
    else:
        remote_sha = _asset_digest_from_download(credential)
    if remote_sha != artifact["sha256"]:
        die("GitHub Release 资产 SHA-256 与凭证不一致")


def _ensure_release_asset(path, credential, info):
    artifact = credential["artifact"]
    name = Path(artifact["path"]).name
    assets = info.get("assets") or []
    matching = [asset for asset in assets if asset.get("name") == name]
    if not matching:
        if assets:
            die("GitHub Release 存在不同资产，禁止上传或覆盖")
        result = run_quiet(
            _gh_cmd(
                "release", "upload", credential["tag"],
                str(ROOT / artifact["path"]),
                "--repo", credential["environment"]["repository"],
            ),
            timeout=300,
        )
        if result.returncode != 0:
            die("上传 GitHub Release 资产失败")
        info = _read_remote_release(
            credential["tag"],
            credential["environment"]["repository"],
        )
        if info is None:
            die("上传资产后 Release 状态丢失")
    _audit_release_metadata(info, credential)
    _audit_release_asset(info, credential)
    return _save_publication_progress(path, credential, "asset", completed=True)


def _continue_publication(path, credential):
    if credential.get("state") not in {"publishing", "published"}:
        die("resume 只接受已经开始 publish 的同一凭证")
    _validate_static_credential(credential, credential["version"])
    if _git_branch() != DEFAULT_BRANCH:
        die(f"当前分支不是 {DEFAULT_BRANCH}")

    commit, credential = _ensure_release_commit(path, credential)
    if _tracked_state_digest(commit, tuple(record["path"] for record in credential["releaseFiles"])) != credential["baseline"]["outsideTrackedSha256"]:
        die("发布白名单外 tracked 状态与 prepared 凭证不一致")
    credential = _ensure_local_tag(path, credential, commit)
    credential = _ensure_remote_branch(path, credential, commit)
    credential = _ensure_remote_tag(path, credential, commit)
    credential, info = _ensure_github_release(path, credential)
    credential = _ensure_release_asset(path, credential, info)
    ok(f"Code v{credential['version']} 两阶段发布完成")
    return credential


def publish_prepared(version, *, auto_yes=False):
    path, credential = _load_prepared_credential(version)
    _validate_prepared_candidate(credential, version)
    if not auto_yes and not ask(f"确认发布 prepared 候选 v{version}？"):
        print("  已取消")
        return
    credential["state"] = "publishing"
    credential["publication"]["startedAt"] = _utc_now()
    credential = save_credential(path, credential)
    _continue_publication(path, credential)


def resume_release(version, *, auto_yes=False):
    path, credential = _load_prepared_credential(version)
    if credential.get("state") not in {"publishing", "published"}:
        die("resume 只能继续已经由 publish-prepared 启动的凭证")
    if not auto_yes and not ask(f"确认审计并续接 v{version} 发布？"):
        print("  已取消")
        return
    _continue_publication(path, credential)


# ═══════════════════════════════════════════════════════════════
# Step 8: Git 提交 & 打标签
# ═══════════════════════════════════════════════════════════════

def git_commit_and_tag(new_version, dry_run=False):
    print("\n-- Git 提交 & 标签 --")

    files_to_add = [
        "VERSION",
        "file_version_info.txt",
        "README.md",
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
  python release.py 0.5.8 --prepare    验证并生成本地 prepared 凭证
  python release.py 0.5.8 --publish-prepared  发布精确匹配的 prepared 候选
  python release.py 0.5.8 --resume     审计并续接已开始的发布
  python release.py prepare 0.5.8      兼容别名（其他两阶段动作同理）
  python release.py 0.5.8 --skip-tests 兼容入口：必须存在有效 prepared 凭证
        """,
    )
    parser.add_argument(
        "command_or_version",
        help="版本号，或兼容别名 prepare / publish-prepared / resume",
    )
    parser.add_argument("command_version", nargs="?", help="兼容别名使用的新版本号")
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--prepare",
        dest="release_action",
        action="store_const",
        const="prepare",
        help="完整验证并生成本地 prepared 候选，不执行外部发布",
    )
    action_group.add_argument(
        "--publish-prepared",
        dest="release_action",
        action="store_const",
        const="publish-prepared",
        help="发布与当前候选精确绑定的 prepared 凭证",
    )
    action_group.add_argument(
        "--resume",
        dest="release_action",
        action="store_const",
        const="resume",
        help="审计并续接同一凭证已经开始的外部发布",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="兼容入口：仅使用与当前候选精确绑定的 prepared 凭证",
    )
    parser.add_argument("--dry-run", action="store_true", help="预演模式：只检查不修改任何文件")
    parser.add_argument("--yes", "-y", action="store_true", help="跳过所有交互确认（供 AI Agent 使用）")
    parser.add_argument("--proxy", default=None,
                        help="HTTPS 代理地址，如 127.0.0.1:18081（默认自动检测 Windows 系统代理）")
    parser.add_argument("--no-proxy", action="store_true", help="禁用代理（跳过自动检测）")
    args = parser.parse_args()

    if args.command_or_version in RELEASE_ACTIONS:
        if args.release_action is not None:
            parser.error("动作 flag 不能与兼容动作子命令组合")
        action = args.command_or_version
        if not args.command_version:
            parser.error(f"{action} 需要版本号")
        new_version = args.command_version
    else:
        action = args.release_action or "full"
        new_version = args.command_or_version
        if args.command_version is not None:
            parser.error("版本优先入口只接受一个版本号")

    if action != "full" and args.dry_run:
        parser.error("--dry-run 仅适用于原有一次性入口")
    if action != "full" and args.skip_tests:
        parser.error("显式两阶段路径不接受 --skip-tests")

    global _proxy_url

    if args.no_proxy:
        _proxy_url = None
    elif args.proxy:
        _proxy_url = args.proxy
    else:
        detected = detect_windows_proxy()
        if detected:
            _proxy_url = detected

    parse_version(new_version)

    # --yes 模式下跳过所有交互确认
    if args.yes:
        global ask
        def ask(prompt):
            print(f"  ?  {prompt} [y/N]  (--yes: auto y)")
            return True

    if action == "prepare":
        prepare_release(new_version)
        return
    if action == "publish-prepared":
        publish_prepared(new_version, auto_yes=args.yes)
        return
    if action == "resume":
        resume_release(new_version, auto_yes=args.yes)
        return
    if args.skip_tests and not args.dry_run:
        warn(
            "--skip-tests 不再接受无依据跳过；正在按兼容模式验证 prepared 凭证，"
            f"后续请改用 python release.py {new_version} --publish-prepared",
        )
        publish_prepared(new_version, auto_yes=args.yes)
        return

    version_tuple = parse_version(new_version)
    old_version = get_current_version()

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
    verify_version_consistency(new_version, old_version, dry_run=args.dry_run)

    # ── Phase 2: 代码质量检查 ──
    print("\n" + "=" * 60)
    print("  Phase 2: 代码质量检查")
    print("=" * 60)
    run_release_quality_checks(
        dry_run=args.dry_run,
        skip_tests=args.skip_tests,
    )

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
