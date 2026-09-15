"""Collect normally; import the project archive service only in an isolated child."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_project_archive_in_isolated_process():
    with tempfile.TemporaryDirectory(prefix="code072-cases-") as directory:
        root = Path(directory).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        environment = dict(os.environ, CODE_DATA_DIR=str(root / "data"))
        result = subprocess.run([
            sys.executable, "-X", "utf8", "-B", "-m", "pytest",
            "tests/project_archive_cases.py", "-q", "--tb=short", "-p", "no:cacheprovider",
        ], cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)
