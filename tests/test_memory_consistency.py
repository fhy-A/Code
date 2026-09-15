"""Collect normally; import the memory service only in an isolated child."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_memory_consistency_in_isolated_process():
    with tempfile.TemporaryDirectory(prefix="code084-cases-") as directory:
        root = Path(directory).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        environment = dict(os.environ, CODE_DATA_DIR=str(root / "data"))
        result = subprocess.run([
            sys.executable, "-X", "utf8", "-B", "-m", "pytest",
            "tests/memory_consistency_cases.py", "-q", "--tb=short", "-p", "no:cacheprovider",
        ], cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        print(result.stdout)


def test_memory_module_collects_without_code_data_dir():
    environment = dict(os.environ)
    environment.pop("CODE_DATA_DIR", None)
    # Collection must not even import server or open the application's data.
    program = r"""
import os, pathlib, sys, pytest
protected = (pathlib.Path.cwd() / 'data').resolve()
def guard(event, args):
    if event in {'open', 'os.listdir', 'os.scandir'} and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = pathlib.Path(os.fsdecode(args[0])).absolute()
        if path == protected or protected in path.parents:
            raise AssertionError('Collection accessed real product data')
sys.addaudithook(guard)
code = pytest.main(['tests/test_memory_consistency.py', '--collect-only', '-q', '-p', 'no:cacheprovider'])
assert 'server' not in sys.modules
raise SystemExit(code)
"""
    result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c", program], cwd=ROOT,
        env=environment, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_full_collection_without_code_data_dir(tmp_path):
    environment = dict(os.environ)
    environment.pop('CODE_DATA_DIR', None)
    program = r'''
import importlib.util, os, pathlib, sys
root = pathlib.Path.cwd()
protected = (root / 'data').resolve()
def guard(event, args):
    if event in {'open','os.listdir','os.scandir'} and args and isinstance(args[0], (str,bytes,os.PathLike)):
        path = pathlib.Path(os.fsdecode(args[0])).absolute()
        if path == protected or protected in path.parents:
            raise AssertionError('Normal collection accessed real product data')
sys.addaudithook(guard)
# Existing suites import server during collection. Give that source module a
# disposable application root, with CODE_DATA_DIR genuinely absent throughout.
source = root / 'server.py'
spec = importlib.util.spec_from_file_location('server', source)
server = importlib.util.module_from_spec(spec)
server.__file__ = str(pathlib.Path(sys.argv[1]) / 'server.py')
sys.modules['server'] = server
exec(compile(source.read_text(encoding='utf-8'), str(source), 'exec'), server.__dict__)
assert 'CODE_DATA_DIR' not in os.environ
assert server.DATA_DIR == pathlib.Path(sys.argv[1]) / 'data'
import pytest
raise SystemExit(pytest.main(['tests','--collect-only','-q','-p','no:cacheprovider']))
'''
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', program, str(tmp_path)],
        cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=90)
    assert result.returncode == 0, (result.stdout + result.stderr)[-12000:]
