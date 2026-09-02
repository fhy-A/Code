"""
Build code into a standalone .exe with PyInstaller.
Run: python build_exe.py
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FRONTEND_BUILD_SCRIPT = APP_DIR / "scripts" / "build-frontend.mjs"
FRONTEND_OUTPUT_DIR = APP_DIR / "dist" / "frontend"
FRONTEND_BUNDLE = FRONTEND_OUTPUT_DIR / "code.bundle.js"
FRONTEND_CLASSIC_FALLBACK = FRONTEND_OUTPUT_DIR / "index.classic.html"
BUNDLED_SKILLS_DIR = APP_DIR / 'data' / 'skills'
SKILL_PACKAGE_STAGE_DIR = APP_DIR / "build" / "skill-package-stage"


def _is_link_or_reparse(path):
    try:
        metadata = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or 0x400)
    return bool(attributes & reparse_flag)


def _validate_bundled_skill_tree(root):
    """Reject links while walking only the Code-owned source bundle."""
    root = Path(root)
    if _is_link_or_reparse(root) or not root.is_dir():
        raise RuntimeError("bundled Skill source is not a regular directory")
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        if _is_link_or_reparse(current_path):
            raise RuntimeError("bundled Skill source contains a reparse directory")
        for name in [*directories, *files]:
            if _is_link_or_reparse(current_path / name):
                raise RuntimeError("bundled Skill source contains a reparse entry")


def prepare_bundled_skills_for_packaging():
    """Stage a clean data/skills tree without interpreter bytecode artifacts."""
    _validate_bundled_skill_tree(BUNDLED_SKILLS_DIR)
    stage_parent = SKILL_PACKAGE_STAGE_DIR.parent
    if _is_link_or_reparse(stage_parent):
        raise RuntimeError("Skill package staging parent is unsafe")
    stage_parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(SKILL_PACKAGE_STAGE_DIR):
        if _is_link_or_reparse(SKILL_PACKAGE_STAGE_DIR):
            raise RuntimeError("Skill package staging directory is unsafe")
        shutil.rmtree(SKILL_PACKAGE_STAGE_DIR)
    shutil.copytree(
        BUNDLED_SKILLS_DIR,
        SKILL_PACKAGE_STAGE_DIR,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return SKILL_PACKAGE_STAGE_DIR


def build_frontend_assets():
    """Build and verify the exact frontend assets embedded in the EXE."""
    commands = (
        ["node", str(FRONTEND_BUILD_SCRIPT)],
        ["node", str(FRONTEND_BUILD_SCRIPT), "--check"],
        ["node", "--check", str(FRONTEND_BUNDLE)],
    )
    print("Building and verifying frontend assets...")
    for command in commands:
        subprocess.run(command, cwd=str(APP_DIR), check=True)


build_frontend_assets()
PACKAGED_SKILLS_DIR = prepare_bundled_skills_for_packaging()

# Ensure data subdirs exist
for d in ["data", "data/sessions", "data/memory", "data/skills", "data/attachments", "data/file-backups"]:
    (APP_DIR / d).mkdir(exist_ok=True)

version = (APP_DIR / "VERSION").read_text().strip()
name = f"Code-v{version}"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--name", name,
    "--specpath", str(APP_DIR / "build"),
    "--icon", str(APP_DIR / "code-icon.ico"),
    "--version-file", str(APP_DIR / "file_version_info.txt"),
    "--add-data", f"{APP_DIR / 'VERSION'}{';'}.",
    "--add-data", f"{APP_DIR / 'app.js'}{';'}.",
    "--add-data", f"{APP_DIR / 'agent-runtime.js'}{';'}.",
    "--add-data", f"{APP_DIR / 'src'}{';'}src",
    "--add-data", f"{APP_DIR / 'index.html'}{';'}.",
    "--add-data", f"{FRONTEND_BUNDLE}{';'}dist/frontend",
    "--add-data", f"{FRONTEND_CLASSIC_FALLBACK}{';'}dist/frontend",
    "--add-data", f"{APP_DIR / 'styles.css'}{';'}.",
    "--add-data", f"{APP_DIR / 'code-icon.ico'}{';'}.",
    "--add-data", f"{APP_DIR / 'code-icon.png'}{';'}.",
    "--add-data", f"{APP_DIR / 'assets'}{';'}assets",
    "--add-data", f"{PACKAGED_SKILLS_DIR}{';'}data/skills",
    "--add-data", f"{APP_DIR / 'data' / 'memory'}{';'}data/memory",
    "--hidden-import", "json",
    "--hidden-import", "mimetypes",
    "--hidden-import", "pystray",
    "--hidden-import", "PIL.Image",
    "--hidden-import", "PIL.BmpImagePlugin",
    "--hidden-import", "PIL.IcoImagePlugin",
    "--hidden-import", "PIL.PngImagePlugin",
    "--exclude-module", "PIL.ImageQt",
    "--exclude-module", "PIL.ImageDraw2",
    "--exclude-module", "PIL.ImageFont",
    "--exclude-module", "PIL.ImageFilter",
    "--exclude-module", "PIL.ImageEnhance",
    "--exclude-module", "PIL.ImageMath",
    "--exclude-module", "PIL.ImageMorph",
    "--exclude-module", "PIL.ImageOps",
    "--exclude-module", "PIL.ImagePath",
    "--exclude-module", "PIL.ImageStat",
    "--exclude-module", "PIL.ImageTransform",
    "--exclude-module", "PIL.ImageWin",
    "--exclude-module", "PIL.ImImagePlugin",
    "--exclude-module", "PIL.BlpImagePlugin",
    "--exclude-module", "PIL.BufrStubImagePlugin",
    "--exclude-module", "PIL.CurImagePlugin",
    "--exclude-module", "PIL.DcxImagePlugin",
    "--exclude-module", "PIL.DdsImagePlugin",
    "--exclude-module", "PIL.EpsImagePlugin",
    "--exclude-module", "PIL.FitsImagePlugin",
    "--exclude-module", "PIL.FliImagePlugin",
    "--exclude-module", "PIL.FpxImagePlugin",
    "--exclude-module", "PIL.FtexImagePlugin",
    "--exclude-module", "PIL.GbrImagePlugin",
    "--exclude-module", "PIL.GdImageFile",
    "--exclude-module", "PIL.GifImagePlugin",
    "--exclude-module", "PIL.GribStubImagePlugin",
    "--exclude-module", "PIL.Hdf5StubImagePlugin",
    "--exclude-module", "PIL.IcnsImagePlugin",
    "--exclude-module", "PIL.ImImagePlugin",
    "--exclude-module", "PIL.ImtImagePlugin",
    "--exclude-module", "PIL.IptcImagePlugin",
    "--exclude-module", "PIL.Jpeg2KImagePlugin",
    "--exclude-module", "PIL.JpegImagePlugin",
    "--exclude-module", "PIL.McIdasImagePlugin",
    "--exclude-module", "PIL.MicImagePlugin",
    "--exclude-module", "PIL.MpegImagePlugin",
    "--exclude-module", "PIL.MpoImagePlugin",
    "--exclude-module", "PIL.MspImagePlugin",
    "--exclude-module", "PIL.PalmImagePlugin",
    "--exclude-module", "PIL.PcdImagePlugin",
    "--exclude-module", "PIL.PcxImagePlugin",
    "--exclude-module", "PIL.PdfImagePlugin",
    "--exclude-module", "PIL.PixarImagePlugin",
    "--exclude-module", "PIL.PpmImagePlugin",
    "--exclude-module", "PIL.PsdImagePlugin",
    "--exclude-module", "PIL.SgiImagePlugin",
    "--exclude-module", "PIL.SpiderImagePlugin",
    "--exclude-module", "PIL.SunImagePlugin",
    "--exclude-module", "PIL.TgaImagePlugin",
    "--exclude-module", "PIL.TiffImagePlugin",
    "--exclude-module", "PIL.WebPImagePlugin",
    "--exclude-module", "PIL.WmfImagePlugin",
    "--exclude-module", "PIL.XbmImagePlugin",
    "--exclude-module", "PIL.XpmImagePlugin",
    "--exclude-module", "PIL.XVThumbImagePlugin",
    "--clean",
    "--noconsole",
    str(APP_DIR / "launcher.py"),
]

output_path = APP_DIR / "dist" / f"{name}.exe"
print(f"Building {name}.exe...")
subprocess.run(cmd, cwd=str(APP_DIR), check=True)
print(f"\nDone! Output: {output_path}")
