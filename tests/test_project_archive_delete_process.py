"""Real A-exit/B-start recovery, including original-core ownership counterexamples."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT/'tests'/'project_archive_delete_process_worker.py'
CASES = ['partial','facts_deleted','effect','prepared','core_restored'] + [
    f'{phase}_{change}_{field}' for phase in ('prepared','core_restored')
    for change in ('changed','rebuild') for field in ('session','messages')] + [
    'cleanup_bundle','cleanup_journal','cleanup_replaced','cleanup_journal_unlinked']


@pytest.mark.parametrize('case',CASES)
def test_archive_delete_real_process_recovery(case):
    run_delete_process_case(case)


def run_delete_process_case(case, *, all_scope=False):
    parent_service = sys.modules.get('server')
    processes = []
    with tempfile.TemporaryDirectory(prefix='code072-delete-process-') as directory:
        root = Path(directory).resolve()
        assert root.parent == Path(tempfile.gettempdir()).resolve()
        env = dict(os.environ,CODE_DATA_DIR=str(root/'data'),CODE108_ALL_SCOPE='1' if all_scope else '0')
        def run(phase,expected):
            child = subprocess.Popen([sys.executable,'-X','utf8','-B',str(WORKER),phase,case],cwd=ROOT,env=env,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
            processes.append(child)
            try:out,err = child.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill();out,err=child.communicate(timeout=10)
                raise AssertionError(f'{case}/{phase} timed out: {out}\n{err}')
            assert child.returncode == expected,f'{case}/{phase}: {out}\n{err}'
            return child.pid
        try:
            pid_a = run('seed',73)
            assert all(p.poll() is not None for p in processes)
            pid_b = run('recover',0)
            result = json.loads((root/'result.json').read_text(encoding='utf-8'))
            assert result['processA'] == pid_a and result['processB'] == pid_b and pid_a != pid_b
            assert result['passed'] and result['freshRegistriesA'] and result['freshRegistriesB']
            assert sys.modules.get('server') is parent_service
            print(json.dumps(result,ensure_ascii=False))
        finally:
            for process in processes:
                if process.poll() is None:process.kill();process.communicate(timeout=10)
            assert all(p.poll() is not None for p in processes)
    assert not root.exists()
    print(json.dumps({'case':case,'childrenExited':True,'rootRemoved':True,'portsOpened':0}))
