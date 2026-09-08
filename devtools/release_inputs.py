"""Small content bindings for one release candidate, not a build cache."""
import importlib.metadata
import json
import os
from pathlib import Path
import stat
import subprocess

from devtools.release_state import CredentialError, canonical_json, sha256_bytes, sha256_file


PACKAGE_TREES = ("src", "assets", "code_runtime", "data/skills", "data/memory")


def regular(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise CredentialError("发布输入包含链接或重解析点")
    return info


def source_digest(root, excluded, *, require_committed=True):
    root = Path(root)
    def git_names(arguments):
        result = subprocess.run(["git", "ls-files", *arguments, "-z"], cwd=root,
                                capture_output=True, check=True, timeout=120)
        return set(result.stdout.decode("utf-8").split("\0")) - {""}
    tracked = git_names(["--cached"])
    others = git_names(["--others", "--exclude-standard"])
    protected = lambda name: name.startswith(("data/generated-assets/", "data/skill-store-v1/")) or name == "data/image-route-registry.json"
    if any(protected(name) for name in tracked):
        raise CredentialError("运行数据不能成为发布候选输入")
    names = tracked | {name for name in others if not protected(name)}
    names = {name for name in names if not name.startswith(("dist/", "build/"))}
    names.update(path.name for path in root.glob("*.py"))
    for tree in PACKAGE_TREES:
        base = root / tree
        try:
            info = regular(base)
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            raise CredentialError("打包输入树不是目录")
        def unavailable(error):
            raise error
        for directory, dirs, files in os.walk(base, followlinks=False, onerror=unavailable):
            for name in dirs + files:
                regular(Path(directory) / name)
            dirs[:] = [name for name in dirs if name != "__pycache__"]
            names.update((Path(directory) / name).relative_to(root).as_posix()
                         for name in files if not name.endswith(".pyc"))
    if require_committed and names - set(excluded) - tracked:
        raise CredentialError("存在未跟踪的发布输入；先提交产品/测试/打包输入")
    records = []
    for name in sorted(names - set(excluded)):
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise CredentialError("发布输入路径越界")
        path = root / name
        if not stat.S_ISREG(regular(path).st_mode):
            raise CredentialError("发布输入不是普通文件")
        records.append((name, sha256_file(path)))
    return sha256_bytes(canonical_json(records))


def build_environment(root):
    def version(command):
        return subprocess.run(command, cwd=root, capture_output=True, text=True,
                              check=True, timeout=30).stdout.strip()
    esbuild = json.loads(version(["node", "-e", r"""
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const sha=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const entry=require.resolve('esbuild');
const binary=process.env.ESBUILD_BINARY_PATH || require.resolve(
  '@esbuild/'+process.platform+'-'+process.arch+'/'+(process.platform==='win32'?'esbuild.exe':'bin/esbuild'));
console.log(JSON.stringify({version:require('esbuild').version,entrySha256:sha(entry),binarySha256:sha(binary)}));
"""]))
    return {
        "esbuild": esbuild,
        "node": version(["node", "--version"]),
        "npm": version(["npm.cmd" if os.name == "nt" else "npm", "--version"]),
        "pythonDistributionsSha256": sha256_bytes(canonical_json(sorted(
            (dist.metadata.get("Name", ""), dist.version) for dist in importlib.metadata.distributions()))),
        "packages": {name: importlib.metadata.version(name)
                     for name in ("pyinstaller", "Pillow", "pystray")},
    }


def frontend_proof(root):
    root = Path(root)
    state_path = root / "dist/frontend/code.bundle.state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    paths = [*state["inputs"], *("dist/frontend/" + name for name in state["outputs"])]
    records = []
    for name in sorted(set(paths + ["dist/frontend/code.bundle.state.json"])):
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise CredentialError("前端证明路径越界")
        regular(root / name)
        records.append((name, sha256_file(root / name)))
    return {"filesSha256": sha256_bytes(canonical_json(records)),
            "environment": build_environment(root)}


def verify_frontend(root, expected):
    root = Path(root)
    if frontend_proof(root) != expected:
        raise CredentialError("前端输入/输出/工具链与本次发布证明不一致")
    for command in (["node", str(root / "scripts/build-frontend.mjs"), "--check"],
                    ["node", "--check", str(root / "dist/frontend/code.bundle.js")]):
        subprocess.run(command, cwd=root, check=True, timeout=120)
    if frontend_proof(root) != expected:
        raise CredentialError("前端在核验期间变化")
