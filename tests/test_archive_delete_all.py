"""Run destructive all-archive cases only in a disposable child data root."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_all_archive_delete_in_isolated_process():
    with tempfile.TemporaryDirectory(prefix='code108-all-cases-') as directory:
        root = Path(directory).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', 'pytest',
            'tests/archive_delete_all_cases.py', '-q', '--tb=short', '-p', 'no:cacheprovider'],
            cwd=ROOT, env=dict(os.environ, CODE_DATA_DIR=str(root/'data')),
            capture_output=True, text=True, encoding='utf-8', timeout=180)
        print(result.stdout)
        assert result.returncode == 0, result.stdout + result.stderr
